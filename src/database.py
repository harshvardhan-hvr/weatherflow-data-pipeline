"""WeatherFlow Database Management & Idempotent Ingestion Module.

Step 4 of the ETL Pipeline:
- Connects to PostgreSQL or SQLite via SQLAlchemy engine pooling.
- Creates Star Schema tables, foreign keys, and performance indexes.
- Implements Idempotent UPSERT loading: safely rerunning never produces duplicate rows.
- Records pipeline execution audit logs (pipeline_runs) and quality checks (data_quality_results).
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import create_engine, text, Engine
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_default_db_url() -> str:
    """Return the configured DATABASE_URL from .env, defaulting to local SQLite."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        from src.ingestion import get_project_root
        db_path = get_project_root() / "data" / "weatherflow.db"
        return f"sqlite:///{db_path}"
    return db_url


def get_db_engine(database_url: Optional[str] = None) -> Engine:
    """Instantiate and return a SQLAlchemy Engine with connection pooling.
    
    Data Engineering Concept:
    SQLAlchemy's create_engine manages connection pools and translates queries
    across database dialects (PostgreSQL, SQLite, MySQL, Snowflake).
    """
    url = database_url or get_default_db_url()

    # For SQLite, ensure parent directory exists
    if url.startswith("sqlite:///"):
        raw_path = url.replace("sqlite:///", "")
        db_file = Path(raw_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, echo=False, pool_pre_ping=True)
    return engine


def init_database(engine: Engine, schema_path: Optional[Path] = None) -> None:
    """Initialize database tables from sql/schema.sql DDL."""
    if schema_path is None:
        from src.ingestion import get_project_root
        schema_path = get_project_root() / "sql" / "schema.sql"

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found at: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        ddl_script = f.read()

    # Execute individual DDL statements
    statements = [stmt.strip() for stmt in ddl_script.split(";") if stmt.strip()]

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))

    print(f"[DATABASE] Schema successfully initialized on engine: {engine.url.drivername}")


def load_dim_date(conn, df_dim_date: pd.DataFrame) -> int:
    """Idempotently load dim_date using ON CONFLICT DO NOTHING."""
    records = df_dim_date.to_dict(orient="records")
    if not records:
        return 0

    sql = text("""
        INSERT INTO dim_date (
            date_key, full_date, year, month, month_name,
            quarter, day_of_month, day_of_week, is_weekend, season
        ) VALUES (
            :date_key, :full_date, :year, :month, :month_name,
            :quarter, :day_of_month, :day_of_week, :is_weekend, :season
        )
        ON CONFLICT (date_key) DO NOTHING
    """)

    conn.execute(sql, records)
    return len(records)


def load_dim_location(conn, df_dim_loc: pd.DataFrame) -> int:
    """Idempotently load dim_location using UPSERT (ON CONFLICT DO UPDATE)."""
    records = df_dim_loc.to_dict(orient="records")
    if not records:
        return 0

    sql = text("""
        INSERT INTO dim_location (
            station_id, station_name, latitude, longitude, elevation, country, state
        ) VALUES (
            :station_id, :station_name, :latitude, :longitude, :elevation, :country, :state
        )
        ON CONFLICT (station_id) DO UPDATE SET
            station_name = excluded.station_name,
            latitude     = excluded.latitude,
            longitude    = excluded.longitude,
            elevation    = excluded.elevation,
            country      = excluded.country,
            state        = excluded.state
    """)

    conn.execute(sql, records)
    return len(records)


def load_weather_observations(conn, df_facts: pd.DataFrame) -> int:
    """Idempotently load weather_observations fact table.
    
    Data Engineering Concept:
    Idempotent UPSERT prevents duplicate observations if an upstream pipeline
    batch is retried or executed multiple times for the same day.
    """
    records = df_facts.to_dict(orient="records")
    if not records:
        return 0

    sql = text("""
        INSERT INTO weather_observations (
            observation_id, station_id, date_key, observation_date,
            temp_avg_c, temp_max_c, temp_min_c, temp_range_c,
            precipitation_mm, precip_category, wind_speed_kmh,
            humidity_pct, weather_condition
        ) VALUES (
            :observation_id, :station_id, :date_key, :observation_date,
            :temp_avg_c, :temp_max_c, :temp_min_c, :temp_range_c,
            :precipitation_mm, :precip_category, :wind_speed_kmh,
            :humidity_pct, :weather_condition
        )
        ON CONFLICT (station_id, observation_date) DO UPDATE SET
            temp_avg_c        = excluded.temp_avg_c,
            temp_max_c        = excluded.temp_max_c,
            temp_min_c        = excluded.temp_min_c,
            temp_range_c      = excluded.temp_range_c,
            precipitation_mm  = excluded.precipitation_mm,
            precip_category   = excluded.precip_category,
            wind_speed_kmh    = excluded.wind_speed_kmh,
            humidity_pct      = excluded.humidity_pct,
            weather_condition = excluded.weather_condition,
            updated_at        = CURRENT_TIMESTAMP
    """)

    conn.execute(sql, records)
    return len(records)


def load_all_weather_data(
    engine: Engine,
    df_facts: pd.DataFrame,
    df_dim_loc: pd.DataFrame,
    df_dim_date: pd.DataFrame,
) -> int:
    """Execute dimensional load inside an atomic database transaction.
    
    Returns:
        Number of loaded fact records.
    """
    with engine.begin() as conn:
        load_dim_location(conn, df_dim_loc)
        load_dim_date(conn, df_dim_date)
        loaded_count = load_weather_observations(conn, df_facts)

    print(f"[DATABASE] Successfully loaded {loaded_count} fact records into weather_observations.")
    return loaded_count


def record_pipeline_run(
    engine: Engine,
    run_id: str,
    pipeline_name: str,
    started_at: datetime,
    completed_at: datetime,
    status: str,
    records_read: int,
    records_clean: int,
    records_rejected: int,
    records_loaded: int,
    error_message: Optional[str] = None,
) -> None:
    """Insert or update pipeline execution telemetry in pipeline_runs."""
    sql = text("""
        INSERT INTO pipeline_runs (
            run_id, pipeline_name, started_at, completed_at, status,
            records_read, records_clean, records_rejected, records_loaded, error_message
        ) VALUES (
            :run_id, :pipeline_name, :started_at, :completed_at, :status,
            :records_read, :records_clean, :records_rejected, :records_loaded, :error_message
        )
        ON CONFLICT (run_id) DO UPDATE SET
            completed_at     = excluded.completed_at,
            status           = excluded.status,
            records_read     = excluded.records_read,
            records_clean    = excluded.records_clean,
            records_rejected = excluded.records_rejected,
            records_loaded   = excluded.records_loaded,
            error_message    = excluded.error_message
    """)

    params = {
        "run_id": run_id,
        "pipeline_name": pipeline_name,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": status,
        "records_read": records_read,
        "records_clean": records_clean,
        "records_rejected": records_rejected,
        "records_loaded": records_loaded,
        "error_message": error_message,
    }

    with engine.begin() as conn:
        conn.execute(sql, params)


def record_data_quality_results(
    engine: Engine,
    run_id: str,
    checks: List[Any],
) -> None:
    """Save granular data quality check outcomes to data_quality_results table."""
    if not checks:
        return

    records = []
    for idx, c in enumerate(checks):
        check_id = f"{run_id}_chk_{idx + 1}"
        records.append({
            "check_id": check_id,
            "run_id": run_id,
            "check_name": c.check_name,
            "table_name": c.table_name,
            "column_name": c.column_name,
            "status": c.status,
            "records_evaluated": c.records_evaluated,
            "records_failed": c.records_failed,
            "failure_rate_pct": c.failure_rate_pct,
            "details": c.details,
            "checked_at": datetime.now(timezone.utc),
        })

    sql = text("""
        INSERT INTO data_quality_results (
            check_id, run_id, check_name, table_name, column_name,
            status, records_evaluated, records_failed, failure_rate_pct, details, checked_at
        ) VALUES (
            :check_id, :run_id, :check_name, :table_name, :column_name,
            :status, :records_evaluated, :records_failed, :failure_rate_pct, :details, :checked_at
        )
        ON CONFLICT (check_id) DO NOTHING
    """)

    with engine.begin() as conn:
        conn.execute(sql, records)
