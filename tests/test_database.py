"""Unit tests for src/database.py."""

from datetime import datetime, timezone
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from src.database import (
    init_database,
    load_all_weather_data,
    record_pipeline_run,
    record_data_quality_results,
)
from src.validation import DQCheckResult


@pytest.fixture
def test_db_engine(tmp_path):
    """Provides a fresh isolated SQLite database engine for testing."""
    db_file = tmp_path / "test_weatherflow.db"
    engine = create_engine(f"sqlite:///{db_file}")
    init_database(engine)
    return engine


def test_schema_initialization(test_db_engine):
    """Verify that all 5 tables exist after running init_database."""
    expected_tables = {
        "dim_date",
        "dim_location",
        "weather_observations",
        "pipeline_runs",
        "data_quality_results",
    }

    with test_db_engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        existing_tables = {row[0] for row in result.fetchall()}

    for table in expected_tables:
        assert table in existing_tables, f"Table {table} must be present in schema"


def test_idempotent_loading(test_db_engine):
    """Verify that running the load step multiple times does NOT duplicate rows."""
    df_loc = pd.DataFrame([{
        "station_id": "ST_001",
        "station_name": "Test Station",
        "latitude": 40.0,
        "longitude": -74.0,
        "elevation": 10.0,
        "country": "US",
        "state": "NY",
    }])

    df_date = pd.DataFrame([{
        "date_key": 20230101,
        "full_date": "2023-01-01",
        "year": 2023,
        "month": 1,
        "month_name": "January",
        "quarter": 1,
        "day_of_month": 1,
        "day_of_week": "Sunday",
        "is_weekend": True,
        "season": "Winter",
    }])

    df_facts = pd.DataFrame([{
        "observation_id": "hash_123",
        "station_id": "ST_001",
        "date_key": 20230101,
        "observation_date": "2023-01-01",
        "temp_avg_c": 5.0,
        "temp_max_c": 8.0,
        "temp_min_c": 2.0,
        "temp_range_c": 6.0,
        "precipitation_mm": 0.0,
        "precip_category": "None",
        "wind_speed_kmh": 10.0,
        "humidity_pct": 60.0,
        "weather_condition": "Clear",
    }])

    # First load
    load_all_weather_data(test_db_engine, df_facts, df_loc, df_date)

    with test_db_engine.connect() as conn:
        c1 = conn.execute(text("SELECT COUNT(*) FROM weather_observations")).scalar()
        assert c1 == 1

    # Second load with identical data (testing Idempotency)
    load_all_weather_data(test_db_engine, df_facts, df_loc, df_date)

    with test_db_engine.connect() as conn:
        c2 = conn.execute(text("SELECT COUNT(*) FROM weather_observations")).scalar()
        assert c2 == 1, "Idempotent load must not duplicate records!"


def test_pipeline_run_audit_logging(test_db_engine):
    """Verify that pipeline_runs telemetry is recorded properly."""
    run_id = "test_run_001"
    now = datetime.now(timezone.utc)

    record_pipeline_run(
        engine=test_db_engine,
        run_id=run_id,
        pipeline_name="UnitTestPipeline",
        started_at=now,
        completed_at=now,
        status="SUCCESS",
        records_read=100,
        records_clean=95,
        records_rejected=5,
        records_loaded=95,
    )

    with test_db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, records_read, records_loaded FROM pipeline_runs WHERE run_id = :r"),
            {"r": run_id},
        ).fetchone()

        assert row is not None
        assert row[0] == "SUCCESS"
        assert row[1] == 100
        assert row[2] == 95


def test_data_quality_results_logging(test_db_engine):
    """Verify that data_quality_results logging records check metrics."""
    run_id = "test_run_dq_001"
    checks = [
        DQCheckResult(
            check_name="Check Temp",
            table_name="weather_observations",
            column_name="temp_avg_c",
            status="PASS",
            records_evaluated=100,
            records_failed=0,
            failure_rate_pct=0.0,
            details="All temperatures valid",
        )
    ]

    record_data_quality_results(test_db_engine, run_id, checks)

    with test_db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT check_name, status, failure_rate_pct FROM data_quality_results WHERE run_id = :r"),
            {"r": run_id},
        ).fetchone()

        assert row is not None
        assert row[0] == "Check Temp"
        assert row[1] == "PASS"
        assert row[2] == 0.0
