"""WeatherFlow Transformation Module.

Step 3 of the ETL Pipeline:
- Converts validated strings into typed numeric and datetime representations.
- Imputes missing sensor readings where domain logic allows (e.g., avg = (min + max)/2).
- Derives analytical features: seasons, precipitation categories, temperature ranges.
- Generates dimensional tables (dim_date, dim_location) and the fact table (weather_observations).
- Persists the Silver layer to Parquet and CSV for efficient analytical querying.
"""

import hashlib
from pathlib import Path
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd


def get_meteorological_season(month: int) -> str:
    """Return meteorological season for a given calendar month (Northern Hemisphere).
    
    Data Engineering Note:
    Consistent business logic should be codified in pure functions so they can be
    tested independently in unit tests.
    """
    if month in (12, 1, 2):
        return "Winter"
    elif month in (3, 4, 5):
        return "Spring"
    elif month in (6, 7, 8):
        return "Summer"
    elif month in (9, 10, 11):
        return "Fall"
    return "Unknown"


def categorize_precipitation(precip_mm: Optional[float]) -> str:
    """Classify daily precipitation into standard meteorological intensity bins."""
    if precip_mm is None or np.isnan(precip_mm):
        return "Missing"
    if precip_mm == 0.0:
        return "None"
    elif precip_mm <= 2.5:
        return "Light"
    elif precip_mm <= 10.0:
        return "Moderate"
    else:
        return "Heavy"


def generate_observation_id(station_id: str, date_str: str) -> str:
    """Generate a deterministic surrogate key for an observation.
    
    Data Engineering Concept:
    Using a deterministic hash (e.g. MD5 of natural business keys) guarantees
    idempotency: loading the exact same station + date on any machine will always
    generate the exact same primary key without database auto-increment collisions.
    """
    key_string = f"{str(station_id).strip()}_{str(date_str).strip()}"
    return hashlib.md5(key_string.encode("utf-8")).hexdigest()


def impute_missing_temperatures(df: pd.DataFrame) -> pd.DataFrame:
    """Impute missing temp_avg_c when temp_min_c and temp_max_c are both present."""
    df = df.copy()
    avg_missing = df["temp_avg_c"].isna()
    min_present = df["temp_min_c"].notna()
    max_present = df["temp_max_c"].notna()

    imputable_mask = avg_missing & min_present & max_present
    df.loc[imputable_mask, "temp_avg_c"] = (
        (df.loc[imputable_mask, "temp_min_c"] + df.loc[imputable_mask, "temp_max_c"]) / 2.0
    ).round(2)

    return df


def extract_dim_location(df: pd.DataFrame) -> pd.DataFrame:
    """Extract and deduplicate station metadata for dim_location."""
    cols = ["station_id", "station_name", "latitude", "longitude", "elevation"]
    available_cols = [c for c in cols if c in df.columns]

    dim_loc = df[available_cols].drop_duplicates(subset=["station_id"]).copy()
    dim_loc["country"] = "US"

    # Derive state if station_name contains state abbreviation (e.g. 'NY US' -> 'NY')
    def extract_state(name: str) -> Optional[str]:
        if not isinstance(name, str):
            return None
        parts = name.strip().split()
        if len(parts) >= 2 and parts[-1] == "US":
            return parts[-2]
        return None

    dim_loc["state"] = dim_loc["station_name"].apply(extract_state)
    return dim_loc.reset_index(drop=True)


def extract_dim_date(dt_series: pd.Series) -> pd.DataFrame:
    """Generate calendar dimension attributes from a series of dates."""
    unique_dates = pd.to_datetime(dt_series.drop_duplicates()).sort_values()

    dim_date = pd.DataFrame({"full_date": unique_dates})
    dim_date["date_key"] = dim_date["full_date"].dt.strftime("%Y%m%d").astype(int)
    dim_date["year"] = dim_date["full_date"].dt.year
    dim_date["month"] = dim_date["full_date"].dt.month
    dim_date["month_name"] = dim_date["full_date"].dt.strftime("%B")
    dim_date["quarter"] = dim_date["full_date"].dt.quarter
    dim_date["day_of_month"] = dim_date["full_date"].dt.day
    dim_date["day_of_week"] = dim_date["full_date"].dt.strftime("%A")
    dim_date["is_weekend"] = dim_date["full_date"].dt.dayofweek.isin([5, 6])
    dim_date["season"] = dim_date["month"].apply(get_meteorological_season)
    dim_date["full_date"] = dim_date["full_date"].dt.strftime("%Y-%m-%d")

    return dim_date.reset_index(drop=True)


def transform_weather_data(
    clean_df: pd.DataFrame,
    output_dir: Optional[Path] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Execute transformations and feature engineering.
    
    Returns:
        Tuple of (df_facts, df_dim_location, df_dim_date)
    """
    df = clean_df.copy()

    # 1. Cast numeric columns
    numeric_cols = [
        "latitude",
        "longitude",
        "elevation",
        "temp_avg_c",
        "temp_max_c",
        "temp_min_c",
        "precipitation_mm",
        "wind_speed_kmh",
        "humidity_pct",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace("", np.nan), errors="coerce")

    # 2. Impute missing averages where min and max are available
    df = impute_missing_temperatures(df)

    # 3. Standardize dates
    df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.strftime("%Y-%m-%d")
    df["date_key"] = pd.to_datetime(df["observation_date"]).dt.strftime("%Y%m%d").astype(int)

    # 4. Feature engineering
    df["temp_range_c"] = (df["temp_max_c"] - df["temp_min_c"]).round(2)
    df["precip_category"] = df["precipitation_mm"].apply(categorize_precipitation)

    # Fill default condition if empty
    if "weather_condition" not in df.columns or df["weather_condition"].isna().all():
        df["weather_condition"] = "Unknown"
    else:
        df["weather_condition"] = df["weather_condition"].replace("", "Unknown").fillna("Unknown")

    # 5. Deterministic surrogate key
    df["observation_id"] = [
        generate_observation_id(s, d)
        for s, d in zip(df["station_id"], df["observation_date"])
    ]

    # 6. Build dimensional datasets
    df_dim_loc = extract_dim_location(df)
    df_dim_date = extract_dim_date(df["observation_date"])

    # 7. Prepare facts dataframe matching schema
    fact_cols = [
        "observation_id",
        "station_id",
        "date_key",
        "observation_date",
        "temp_avg_c",
        "temp_max_c",
        "temp_min_c",
        "temp_range_c",
        "precipitation_mm",
        "precip_category",
        "wind_speed_kmh",
        "humidity_pct",
        "weather_condition",
    ]
    df_facts = df[fact_cols].drop_duplicates(subset=["observation_id"]).copy()

    # 8. Persist Silver layer (Parquet & CSV)
    if output_dir is None:
        from src.ingestion import get_project_root
        output_dir = get_project_root() / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = output_dir / "weather_cleaned.parquet"
    csv_path = output_dir / "weather_cleaned.csv"

    # Save to Parquet using PyArrow engine
    df_facts.to_parquet(parquet_path, engine="pyarrow", index=False)
    df_facts.to_csv(csv_path, index=False)
    print(f"[TRANSFORMATION] Saved {len(df_facts)} clean fact rows to:")
    print(f"  - Parquet (efficient columnar format): {parquet_path}")
    print(f"  - CSV (human inspectable format): {csv_path}")

    return df_facts, df_dim_loc, df_dim_date
