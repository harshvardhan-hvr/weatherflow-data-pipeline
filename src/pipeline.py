"""WeatherFlow Master ETL Pipeline Orchestrator.

Main entry point for executing the end-to-end weather engineering pipeline:
1. Extract (CSV or NOAA API)
2. Archive (Raw Bronze layer)
3. Validate (Data quality contracts & boundary checks)
4. Clean & Quarantine (Isolate corrupt records)
5. Transform (Silver layer feature engineering & Parquet persistence)
6. Model (Star schema extraction)
7. Load (Idempotent database UPSERT)
8. Audit (Pipeline telemetry & data quality database logging)
9. Export (Gold layer Power BI extracts)
10. Report (Markdown & console summary)
"""

import argparse
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.ingestion import ingest_weather_data, get_project_root
from src.validation import validate_and_filter_weather_data
from src.transformation import transform_weather_data
from src.database import (
    get_db_engine,
    init_database,
    load_all_weather_data,
    record_pipeline_run,
    record_data_quality_results,
)
from src.reporting import export_gold_datasets, generate_pipeline_report


def run_pipeline(
    source_path: Optional[Path] = None,
    use_noaa_api: bool = False,
    noaa_station_id: str = "GHCND:USW00094728",
    start_date: str = "2023-01-01",
    end_date: str = "2023-12-31",
    database_url: Optional[str] = None,
) -> dict:
    """Execute the complete WeatherFlow ETL pipeline.
    
    Returns:
        dict containing execution metrics, run_id, and file paths.
    """
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    start_time = time.time()
    started_at = datetime.now(timezone.utc)

    print("=" * 78)
    print(f" WEATHERFLOW DATA ENGINEERING PIPELINE — RUN ID: {run_id}")
    print("=" * 78)

    # 1. Database Initialization
    print("\n[STEP 1/6] Connecting to Database and Ensuring Schema...")
    engine = get_db_engine(database_url)
    init_database(engine)

    # Record initial RUNNING state
    record_pipeline_run(
        engine=engine,
        run_id=run_id,
        pipeline_name="WeatherFlow-Daily-ETL",
        started_at=started_at,
        completed_at=started_at,
        status="RUNNING",
        records_read=0,
        records_clean=0,
        records_rejected=0,
        records_loaded=0,
    )

    try:
        # 2. Ingestion & Bronze Archival
        print("\n[STEP 2/6] Ingesting Weather Data (Bronze Layer)...")
        df_raw, raw_archive_path = ingest_weather_data(
            source_path=source_path,
            use_noaa_api=use_noaa_api,
            noaa_station_id=noaa_station_id,
            start_date=start_date,
            end_date=end_date,
        )
        total_extracted = len(df_raw)

        # 3. Validation & Quarantining
        print("\n[STEP 3/6] Validating Schema & Running Data Quality Checks...")
        clean_df, rejected_df, val_report = validate_and_filter_weather_data(df_raw)
        print(f"  -> Evaluated: {val_report.total_input} rows")
        print(f"  -> Valid:     {val_report.valid_count} rows")
        print(f"  -> Rejected:  {val_report.rejected_count} rows")
        print(f"  -> Duplicate: {val_report.duplicate_count} rows")

        # Save quarantined records for data governance audit
        if not rejected_df.empty:
            quarantine_path = (
                get_project_root() / "data" / "processed" / "quarantined_rejected_records.csv"
            )
            quarantine_path.parent.mkdir(parents=True, exist_ok=True)
            rejected_df.to_csv(quarantine_path, index=False)
            print(f"  -> Quarantined records saved to: {quarantine_path}")

        # 4. Transformation & Silver Layer
        print("\n[STEP 4/6] Transforming Features & Extracting Star Schema (Silver Layer)...")
        df_facts, df_dim_loc, df_dim_date = transform_weather_data(clean_df)

        # 5. Database Loading (Idempotent UPSERT)
        print("\n[STEP 5/6] Loading Star Schema into Database (Idempotent Load)...")
        loaded_count = load_all_weather_data(
            engine=engine,
            df_facts=df_facts,
            df_dim_loc=df_dim_loc,
            df_dim_date=df_dim_date,
        )

        # Log Data Quality Check Results to DB
        record_data_quality_results(engine, run_id, val_report.checks)

        # 6. Gold Exports & Reporting
        print("\n[STEP 6/6] Generating Gold Power BI Extracts & Execution Report...")
        gold_exports = export_gold_datasets(engine)

        completed_at = datetime.now(timezone.utc)
        duration = time.time() - start_time

        # Update pipeline_runs with SUCCESS
        record_pipeline_run(
            engine=engine,
            run_id=run_id,
            pipeline_name="WeatherFlow-Daily-ETL",
            started_at=started_at,
            completed_at=completed_at,
            status="SUCCESS",
            records_read=total_extracted,
            records_clean=val_report.valid_count,
            records_rejected=val_report.rejected_count,
            records_loaded=loaded_count,
            error_message=None,
        )

        # Generate report
        report_md = generate_pipeline_report(
            run_id=run_id,
            pipeline_name="WeatherFlow-Daily-ETL",
            duration_seconds=duration,
            records_read=total_extracted,
            records_clean=val_report.valid_count,
            records_rejected=val_report.rejected_count,
            records_loaded=loaded_count,
            report_checks=val_report.checks,
            gold_exports=gold_exports,
        )

        print("\n" + "=" * 78)
        print(f" PIPELINE RUN SUCCESSFUL! (Elapsed: {duration:.2f}s)")
        print(f" Records Ingested: {total_extracted} | Clean: {val_report.valid_count} | Loaded: {loaded_count}")
        print("=" * 78)

        return {
            "run_id": run_id,
            "status": "SUCCESS",
            "duration_seconds": duration,
            "records_read": total_extracted,
            "records_clean": val_report.valid_count,
            "records_rejected": val_report.rejected_count,
            "records_loaded": loaded_count,
            "archive_path": raw_archive_path,
            "gold_exports": gold_exports,
        }

    except Exception as exc:
        completed_at = datetime.now(timezone.utc)
        record_pipeline_run(
            engine=engine,
            run_id=run_id,
            pipeline_name="WeatherFlow-Daily-ETL",
            started_at=started_at,
            completed_at=completed_at,
            status="FAILED",
            records_read=0,
            records_clean=0,
            records_rejected=0,
            records_loaded=0,
            error_message=str(exc),
        )
        print(f"\n[PIPELINE ERROR] Pipeline failed: {exc}", file=sys.stderr)
        raise exc


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="WeatherFlow: Production-grade Weather Data Engineering Pipeline"
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Path to input CSV file. Defaults to data/sample/weather_sample_raw.csv",
    )
    parser.add_argument(
        "--use-noaa",
        action="store_true",
        help="Fetch data from NOAA CDO v2 API using NOAA_TOKEN in .env",
    )
    parser.add_argument(
        "--station",
        type=str,
        default="GHCND:USW00094728",
        help="NOAA Station ID (e.g. GHCND:USW00094728 for Central Park NY)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2023-01-01",
        help="Start date (YYYY-MM-DD) for NOAA API",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2023-12-31",
        help="End date (YYYY-MM-DD) for NOAA API",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Override database connection URL (e.g. sqlite:///data/weatherflow.db)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    source_p = Path(args.source) if args.source else None
    run_pipeline(
        source_path=source_p,
        use_noaa_api=args.use_noaa,
        noaa_station_id=args.station,
        start_date=args.start_date,
        end_date=args.end_date,
        database_url=args.db_url,
    )
