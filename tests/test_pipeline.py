"""Integration tests for src/pipeline.py."""

from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

from src.pipeline import run_pipeline


def test_full_pipeline_execution(tmp_path):
    """Verify that run_pipeline executes end-to-end successfully."""
    db_file = tmp_path / "integration_weatherflow.db"
    db_url = f"sqlite:///{db_file}"

    result = run_pipeline(database_url=db_url)

    assert result["status"] == "SUCCESS"
    assert result["records_read"] > 0
    assert result["records_clean"] > 0
    assert result["records_loaded"] > 0
    assert result["records_rejected"] > 0  # Rejects the intentional sample anomalies

    # Verify Gold exports were created
    for name, path in result["gold_exports"].items():
        assert path.exists(), f"Gold export {name} must exist"

    # Verify database contains loaded facts
    engine = create_engine(db_url)
    with engine.connect() as conn:
        obs_count = conn.execute(text("SELECT COUNT(*) FROM weather_observations")).scalar()
        assert obs_count == result["records_loaded"]


def test_pipeline_rerun_idempotence(tmp_path):
    """Verify that running the pipeline twice does NOT create duplicate records."""
    db_file = tmp_path / "idempotent_test.db"
    db_url = f"sqlite:///{db_file}"

    # Run 1
    res1 = run_pipeline(database_url=db_url)

    engine = create_engine(db_url)
    with engine.connect() as conn:
        count_run_1 = conn.execute(text("SELECT COUNT(*) FROM weather_observations")).scalar()

    # Run 2 (Rerun with same input)
    res2 = run_pipeline(database_url=db_url)

    with engine.connect() as conn:
        count_run_2 = conn.execute(text("SELECT COUNT(*) FROM weather_observations")).scalar()

    assert count_run_1 == count_run_2, (
        f"Row count must remain identical after second run ({count_run_1} vs {count_run_2})"
    )
