"""WeatherFlow Reporting & Analytics Export Module.

Step 5 of the ETL Pipeline:
- Executes analytical SQL queries against the star schema.
- Exports Gold Layer datasets to data/gold/ formatted for Power BI.
- Generates a human-readable Markdown and console execution summary report.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import text, Engine


def export_gold_datasets(engine: Engine, gold_dir: Optional[Path] = None) -> Dict[str, Path]:
    """Execute analytical SQL queries and export clean Gold datasets for Power BI.
    
    Data Engineering Concept:
    The Gold Layer represents aggregated, business-ready models optimized
    for reporting and BI tools (Power BI, Tableau, Looker) without exposing
    complex joins or raw dirty records to business users.
    """
    if gold_dir is None:
        from src.ingestion import get_project_root
        gold_dir = get_project_root() / "data" / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)

    exports = {}

    with engine.connect() as conn:
        # 1. Monthly Weather Summary
        q1 = """
            SELECT 
                d.year,
                d.month,
                d.month_name,
                l.station_name,
                l.state,
                ROUND(AVG(w.temp_avg_c), 2) AS avg_temperature_c,
                ROUND(MIN(w.temp_min_c), 2) AS min_temperature_c,
                ROUND(MAX(w.temp_max_c), 2) AS max_temperature_c,
                ROUND(SUM(w.precipitation_mm), 2) AS total_precipitation_mm,
                ROUND(AVG(w.wind_speed_kmh), 2) AS avg_wind_speed_kmh,
                COUNT(w.observation_id) AS observation_days
            FROM weather_observations w
            JOIN dim_date d ON w.date_key = d.date_key
            JOIN dim_location l ON w.station_id = l.station_id
            GROUP BY d.year, d.month, d.month_name, l.station_name, l.state
            ORDER BY d.year, d.month, l.station_name
        """
        df_monthly = pd.read_sql_query(text(q1), conn)
        p1 = gold_dir / "monthly_weather_summary.csv"
        df_monthly.to_csv(p1, index=False)
        exports["monthly_summary"] = p1

        # 2. Station Performance & Quality Metrics
        q2 = """
            SELECT 
                l.station_id,
                l.station_name,
                l.latitude,
                l.longitude,
                l.elevation,
                l.state,
                COUNT(w.observation_id) AS total_observations,
                ROUND(AVG(w.temp_avg_c), 2) AS overall_avg_temp_c,
                ROUND(SUM(w.precipitation_mm), 2) AS total_recorded_rain_mm,
                ROUND(AVG(CASE WHEN w.temp_avg_c IS NOT NULL THEN 1.0 ELSE 0.0 END) * 100, 1) AS temp_completeness_pct
            FROM dim_location l
            LEFT JOIN weather_observations w ON l.station_id = w.station_id
            GROUP BY l.station_id, l.station_name, l.latitude, l.longitude, l.elevation, l.state
            ORDER BY total_observations DESC
        """
        df_station = pd.read_sql_query(text(q2), conn)
        p2 = gold_dir / "station_performance_metrics.csv"
        df_station.to_csv(p2, index=False)
        exports["station_metrics"] = p2

        # 3. Seasonal Weather Profile Analysis
        q3 = """
            SELECT 
                d.season,
                ROUND(AVG(w.temp_avg_c), 2) AS avg_temperature_c,
                ROUND(MIN(w.temp_min_c), 2) AS min_temperature_c,
                ROUND(MAX(w.temp_max_c), 2) AS max_temperature_c,
                ROUND(SUM(w.precipitation_mm), 2) AS total_precipitation_mm,
                ROUND(AVG(w.wind_speed_kmh), 2) AS avg_wind_speed_kmh,
                COUNT(w.observation_id) AS total_records
            FROM weather_observations w
            JOIN dim_date d ON w.date_key = d.date_key
            GROUP BY d.season
            ORDER BY 
                CASE d.season 
                    WHEN 'Winter' THEN 1 
                    WHEN 'Spring' THEN 2 
                    WHEN 'Summer' THEN 3 
                    WHEN 'Fall'   THEN 4 
                    ELSE 5 
                END
        """
        df_seasonal = pd.read_sql_query(text(q3), conn)
        p3 = gold_dir / "seasonal_analysis.csv"
        df_seasonal.to_csv(p3, index=False)
        exports["seasonal_analysis"] = p3

        # 4. Denormalized Power BI Star Model View (ready for drag-and-drop dashboards)
        q4 = """
            SELECT 
                w.observation_id,
                w.observation_date,
                d.year,
                d.month,
                d.month_name,
                d.quarter,
                d.season,
                d.day_of_week,
                d.is_weekend,
                l.station_id,
                l.station_name,
                l.latitude,
                l.longitude,
                l.elevation,
                l.state,
                w.temp_avg_c,
                w.temp_max_c,
                w.temp_min_c,
                w.temp_range_c,
                w.precipitation_mm,
                w.precip_category,
                w.wind_speed_kmh,
                w.humidity_pct,
                w.weather_condition
            FROM weather_observations w
            JOIN dim_date d ON w.date_key = d.date_key
            JOIN dim_location l ON w.station_id = l.station_id
            ORDER BY w.observation_date, l.station_name
        """
        df_powerbi = pd.read_sql_query(text(q4), conn)
        p4 = gold_dir / "powerbi_weather_model.csv"
        df_powerbi.to_csv(p4, index=False)
        exports["powerbi_model"] = p4

    print(f"[REPORTING] Successfully exported 4 Power BI-ready Gold datasets to: {gold_dir}")
    return exports


def generate_pipeline_report(
    run_id: str,
    pipeline_name: str,
    duration_seconds: float,
    records_read: int,
    records_clean: int,
    records_rejected: int,
    records_loaded: int,
    report_checks: List[Any],
    gold_exports: Dict[str, Path],
    output_dir: Optional[Path] = None,
) -> str:
    """Generate and write a comprehensive execution report in Markdown."""
    if output_dir is None:
        from src.ingestion import get_project_root
        output_dir = get_project_root() / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Format quality check rows
    check_rows = []
    for c in report_checks:
        status_badge = "[PASS]" if c.status == "PASS" else f"[{c.status}]"
        check_rows.append(
            f"| `{c.check_name}` | `{c.table_name}` | `{c.column_name}` | **{status_badge}** | {c.records_failed} / {c.records_evaluated} ({c.failure_rate_pct}%) | {c.details} |"
        )
    checks_table = "\n".join(check_rows)

    report_content = f"""# WeatherFlow — Pipeline Execution Report

- **Run ID**: `{run_id}`
- **Pipeline Name**: `{pipeline_name}`
- **Execution Timestamp**: `{timestamp}`
- **Total Duration**: `{duration_seconds:.2f} seconds`
- **Status**: **SUCCESS**

---

## 1. Ingestion & Transformation Metrics

| Metric | Record Count | Percentage of Input |
| :--- | :--- | :--- |
| **Total Ingested (Bronze)** | {records_read} | 100.0% |
| **Valid Records (Silver)** | {records_clean} | {(records_clean / max(1, records_read)) * 100:.1f}% |
| **Quarantined / Rejected** | {records_rejected} | {(records_rejected / max(1, records_read)) * 100:.1f}% |
| **Successfully Loaded (Gold Fact)** | {records_loaded} | {(records_loaded / max(1, records_read)) * 100:.1f}% |

---

## 2. Data Quality Audit Results

| Check Name | Target Table | Target Column | Status | Failed / Evaluated | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
{checks_table}

---

## 3. Power BI Gold Exports

The following datasets have been refreshed and are ready for visualization:
- `monthly_weather_summary.csv`: Aggregated monthly temperature, precipitation, and windy days.
- `station_performance_metrics.csv`: Weather station geolocation, completeness %, and cumulative readings.
- `seasonal_analysis.csv`: Seasonal temperature patterns and rainfall volumes.
- `powerbi_weather_model.csv`: Full denormalized dimensional model for interactive dashboarding.

---
*Report auto-generated by WeatherFlow pipeline reporting engine.*
"""

    report_path = output_dir / f"pipeline_run_{run_id}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"[REPORTING] Execution report saved to: {report_path}")
    return report_content
