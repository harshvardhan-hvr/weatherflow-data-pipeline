"""Unit tests for src/transformation.py."""

import numpy as np
import pandas as pd
import pytest

from src.transformation import (
    get_meteorological_season,
    categorize_precipitation,
    generate_observation_id,
    impute_missing_temperatures,
    extract_dim_date,
    extract_dim_location,
    transform_weather_data,
)


def test_meteorological_season():
    """Verify standard meteorological season classification."""
    assert get_meteorological_season(1) == "Winter"
    assert get_meteorological_season(2) == "Winter"
    assert get_meteorological_season(12) == "Winter"
    assert get_meteorological_season(3) == "Spring"
    assert get_meteorological_season(7) == "Summer"
    assert get_meteorological_season(10) == "Fall"


def test_categorize_precipitation():
    """Verify precipitation intensity bins."""
    assert categorize_precipitation(0.0) == "None"
    assert categorize_precipitation(1.5) == "Light"
    assert categorize_precipitation(5.0) == "Moderate"
    assert categorize_precipitation(25.0) == "Heavy"
    assert categorize_precipitation(None) == "Missing"


def test_deterministic_observation_id():
    """Verify that observation_id generation is pure and deterministic."""
    id1 = generate_observation_id("USW00094728", "2023-01-01")
    id2 = generate_observation_id("USW00094728", "2023-01-01")
    id3 = generate_observation_id("USW00094728", "2023-01-02")

    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 32  # MD5 hex length


def test_impute_missing_temperatures():
    """Verify that missing average temp is calculated from min and max."""
    df = pd.DataFrame({
        "temp_avg_c": [np.nan, 20.0],
        "temp_min_c": [10.0, 15.0],
        "temp_max_c": [20.0, 25.0],
    })
    imputed = impute_missing_temperatures(df)
    assert imputed.loc[0, "temp_avg_c"] == 15.0
    assert imputed.loc[1, "temp_avg_c"] == 20.0


def test_extract_dim_date():
    """Verify dim_date generation with calendar attributes."""
    dates = pd.Series(["2023-01-01", "2023-07-04"])
    dim_date = extract_dim_date(dates)

    assert len(dim_date) == 2
    assert "date_key" in dim_date.columns
    assert "season" in dim_date.columns
    assert dim_date.loc[dim_date["full_date"] == "2023-01-01", "season"].values[0] == "Winter"
    assert dim_date.loc[dim_date["full_date"] == "2023-07-04", "season"].values[0] == "Summer"


def test_transform_weather_data_end_to_end(tmp_path):
    """Verify complete transformation pipeline produces facts and dimensions."""
    clean_records = pd.DataFrame({
        "station_id": ["STATION_TEST"],
        "station_name": ["TEST STATION NY US"],
        "latitude": [40.7],
        "longitude": [-73.9],
        "elevation": [40.0],
        "observation_date": ["2023-05-10"],
        "temp_avg_c": [18.0],
        "temp_max_c": [22.0],
        "temp_min_c": [14.0],
        "precipitation_mm": [3.5],
        "wind_speed_kmh": [15.0],
        "humidity_pct": [65.0],
        "weather_condition": ["Rain"],
    })

    df_facts, df_dim_loc, df_dim_date = transform_weather_data(
        clean_records, output_dir=tmp_path
    )

    assert len(df_facts) == 1
    assert len(df_dim_loc) == 1
    assert len(df_dim_date) == 1
    assert df_facts.iloc[0]["temp_range_c"] == 8.0
    assert df_facts.iloc[0]["precip_category"] == "Moderate"

    # Verify Parquet & CSV file persistence
    parquet_file = tmp_path / "weather_cleaned.parquet"
    csv_file = tmp_path / "weather_cleaned.csv"
    assert parquet_file.exists()
    assert csv_file.exists()
