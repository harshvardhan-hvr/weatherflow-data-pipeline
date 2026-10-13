"""Unit tests for src/ingestion.py."""

from pathlib import Path
import pytest
import pandas as pd

from src.ingestion import (
    read_csv_data,
    archive_raw_file,
    ingest_weather_data,
    get_project_root,
)


def test_read_csv_success():
    """Verify that read_csv_data successfully loads the sample CSV file."""
    sample_path = get_project_root() / "data" / "sample" / "weather_sample_raw.csv"
    assert sample_path.exists(), "Sample CSV file must exist"

    df = read_csv_data(sample_path)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "station_id" in df.columns
    assert "observation_date" in df.columns


def test_read_csv_file_not_found(tmp_path):
    """Verify that read_csv_data raises FileNotFoundError for nonexistent path."""
    non_existent = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError):
        read_csv_data(non_existent)


def test_read_csv_empty_file(tmp_path):
    """Verify that read_csv_data raises ValueError for empty CSV."""
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        read_csv_data(empty_file)


def test_archive_raw_file(tmp_path):
    """Verify that archive_raw_file creates an archived copy in the raw folder."""
    src_file = tmp_path / "test_input.csv"
    src_file.write_text("col1,col2\n1,2\n", encoding="utf-8")

    raw_dir = tmp_path / "raw"
    archived_path = archive_raw_file(src_file, raw_dir=raw_dir)

    assert archived_path.exists()
    assert archived_path.parent == raw_dir
    assert archived_path.name.startswith("raw_weather_")
    assert archived_path.read_text(encoding="utf-8") == src_file.read_text(encoding="utf-8")


def test_ingest_weather_data_fallback():
    """Verify ingest_weather_data works seamlessly with local sample fallback."""
    df, archive_path = ingest_weather_data(use_noaa_api=False)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert archive_path.exists()
