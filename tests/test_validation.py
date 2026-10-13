"""Unit tests for src/validation.py."""

import pandas as pd
import pytest

from src.validation import (
    validate_schema,
    validate_and_filter_weather_data,
    REQUIRED_COLUMNS,
)


@pytest.fixture
def base_valid_data():
    """Provides a valid base record dictionary."""
    return {
        "station_id": ["STATION_A", "STATION_B"],
        "station_name": ["Station Alpha", "Station Beta"],
        "latitude": ["40.7128", "37.7749"],
        "longitude": ["-74.0060", "-122.4194"],
        "elevation": ["10.0", "15.0"],
        "observation_date": ["2023-01-01", "2023-01-02"],
        "temp_avg_c": ["15.0", "18.5"],
        "temp_max_c": ["20.0", "22.0"],
        "temp_min_c": ["10.0", "14.0"],
        "precipitation_mm": ["0.0", "5.2"],
        "wind_speed_kmh": ["12.0", "15.0"],
        "humidity_pct": ["60.0", "75.0"],
        "weather_condition": ["Clear", "Rain"],
    }


def test_schema_validation_success(base_valid_data):
    """Verify that schema validation passes when all required columns are present."""
    df = pd.DataFrame(base_valid_data)
    is_valid, missing = validate_schema(df)
    assert is_valid is True
    assert missing == []


def test_schema_validation_failure(base_valid_data):
    """Verify that schema validation detects missing required columns."""
    df = pd.DataFrame(base_valid_data).drop(columns=["temp_avg_c"])
    is_valid, missing = validate_schema(df)
    assert is_valid is False
    assert "temp_avg_c" in missing


def test_quarantine_impossible_temperature(base_valid_data):
    """Verify that temperatures outside [-60C, +60C] are quarantined."""
    data = base_valid_data.copy()
    data["temp_avg_c"] = ["999.0", "15.0"]  # Row 0 has corrupted sensor reading
    df = pd.DataFrame(data)

    clean_df, rejected_df, report = validate_and_filter_weather_data(df)
    assert len(clean_df) == 1
    assert len(rejected_df) == 1
    assert "Temperature out of realistic bounds" in rejected_df.iloc[0]["rejection_reason"]


def test_quarantine_inconsistent_temperatures(base_valid_data):
    """Verify that min_temp > max_temp is quarantined."""
    data = base_valid_data.copy()
    data["temp_min_c"] = ["25.0", "10.0"]  # Row 0 min (25) > max (20)
    df = pd.DataFrame(data)

    clean_df, rejected_df, report = validate_and_filter_weather_data(df)
    assert len(clean_df) == 1
    assert len(rejected_df) == 1
    assert "min_temp > max_temp" in rejected_df.iloc[0]["rejection_reason"]


def test_quarantine_negative_precipitation(base_valid_data):
    """Verify that negative precipitation readings are quarantined."""
    data = base_valid_data.copy()
    data["precipitation_mm"] = ["-10.0", "5.0"]
    df = pd.DataFrame(data)

    clean_df, rejected_df, report = validate_and_filter_weather_data(df)
    assert len(clean_df) == 1
    assert len(rejected_df) == 1
    assert "Precipitation out of bounds" in rejected_df.iloc[0]["rejection_reason"]


def test_quarantine_missing_station_id(base_valid_data):
    """Verify that records with missing station_id are quarantined."""
    data = base_valid_data.copy()
    data["station_id"] = ["", "STATION_B"]
    df = pd.DataFrame(data)

    clean_df, rejected_df, report = validate_and_filter_weather_data(df)
    assert len(clean_df) == 1
    assert len(rejected_df) == 1
    assert "Missing or blank station_id" in rejected_df.iloc[0]["rejection_reason"]


def test_duplicate_observations_flagged(base_valid_data):
    """Verify that duplicate station + date pairs are flagged and quarantined."""
    data = base_valid_data.copy()
    # Duplicate row 0 with same station and date
    data["station_id"] = ["STATION_A", "STATION_A"]
    data["observation_date"] = ["2023-01-01", "2023-01-01"]
    df = pd.DataFrame(data)

    clean_df, rejected_df, report = validate_and_filter_weather_data(df)
    assert len(clean_df) == 1
    assert len(rejected_df) == 1
    assert report.duplicate_count == 1
    assert "Duplicate observation" in rejected_df.iloc[0]["rejection_reason"]
