"""WeatherFlow Data Quality & Validation Module.

Step 2 of the ETL Pipeline:
- Enforces schema contracts (required columns and data types).
- Validates physical domain boundaries (temperature, precipitation, wind, humidity).
- Identifies and quarantines corrupt, impossible, or incomplete records.
- Generates structured data quality metrics for the data_quality_results audit table.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


# Required schema columns that must exist in raw input
REQUIRED_COLUMNS = [
    "station_id",
    "station_name",
    "observation_date",
    "temp_avg_c",
    "temp_max_c",
    "temp_min_c",
    "precipitation_mm",
    "wind_speed_kmh",
    "humidity_pct",
]

# Physical sensor sanity thresholds
TEMP_MIN_BOUND_C = -60.0    # Lowest plausible terrestrial temperature
TEMP_MAX_BOUND_C = 60.0     # Highest plausible terrestrial temperature
PRECIP_MIN_BOUND_MM = 0.0   # Precipitation cannot be negative
PRECIP_MAX_BOUND_MM = 500.0 # Extreme single-day rainfall ceiling
WIND_MIN_BOUND_KMH = 0.0    # Wind speed cannot be negative
WIND_MAX_BOUND_KMH = 300.0  # Category 5 hurricane peak gusts
HUMIDITY_MIN_BOUND = 0.0    # Relative humidity % min
HUMIDITY_MAX_BOUND = 100.0  # Relative humidity % max


@dataclass
class DQCheckResult:
    """Represents the outcome of an individual data quality check."""
    check_name: str
    table_name: str
    column_name: str
    status: str             # "PASS", "WARN", "FAIL"
    records_evaluated: int
    records_failed: int
    failure_rate_pct: float
    details: str


@dataclass
class ValidationReport:
    """Aggregated validation report for pipeline auditing."""
    total_input: int = 0
    valid_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    checks: List[DQCheckResult] = field(default_factory=list)


def validate_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Verify that all required columns are present in the dataset.
    
    Data Engineering Concept:
    Schema contract validation prevents downstream pipeline tasks from failing
    with unexpected KeyErrors when external data providers change column names.
    """
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    is_valid = len(missing_cols) == 0
    return is_valid, missing_cols


def coerce_numeric(series: pd.Series) -> pd.Series:
    """Safely convert a string/object series to numeric float, coercing errors to NaN."""
    return pd.to_numeric(series.replace("", np.nan), errors="coerce")


def parse_date_safely(series: pd.Series) -> pd.Series:
    """Parse mixed date representations into datetime objects."""
    return pd.to_datetime(series, errors="coerce")


def validate_and_filter_weather_data(
    df_raw: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, ValidationReport]:
    """Execute all schema and business rule validations.
    
    Splits the raw DataFrame into:
    - clean_df: Records that passed all boundary and integrity tests.
    - rejected_df: Records quarantined due to corruption with reasons documented.
    - report: ValidationReport detailing metrics for every quality check.
    """
    report = ValidationReport(total_input=len(df_raw))

    # 1. Schema Check
    has_schema, missing_cols = validate_schema(df_raw)
    if not has_schema:
        raise ValueError(
            f"Schema validation failed! Missing required columns: {missing_cols}"
        )

    # Work on a copy
    df = df_raw.copy()

    # Track rejection reasons per row
    rejection_reasons = pd.Series([""] * len(df), index=df.index)

    def flag_rejection(mask: pd.Series, reason: str):
        """Append rejection reason to flagged rows."""
        nonlocal rejection_reasons
        flagged_idx = df.index[mask]
        for idx in flagged_idx:
            current = rejection_reasons.loc[idx]
            rejection_reasons.loc[idx] = (
                f"{current}; {reason}".strip("; ") if current else reason
            )

    # --------------------------------------------------------------------------
    # Check 1: Station ID completeness
    # --------------------------------------------------------------------------
    missing_station_mask = (
        df["station_id"].isna()
        | (df["station_id"].astype(str).str.strip() == "")
        | (df["station_id"].astype(str).str.strip().str.lower() == "nan")
    )
    fail_station = int(missing_station_mask.sum())
    flag_rejection(missing_station_mask, "Missing or blank station_id")
    report.checks.append(
        DQCheckResult(
            check_name="Completeness: Station ID",
            table_name="weather_observations",
            column_name="station_id",
            status="FAIL" if fail_station > 0 else "PASS",
            records_evaluated=len(df),
            records_failed=fail_station,
            failure_rate_pct=round((fail_station / len(df)) * 100, 2),
            details=f"Found {fail_station} records missing station_id",
        )
    )

    # --------------------------------------------------------------------------
    # Check 2: Valid Date Format
    # --------------------------------------------------------------------------
    parsed_dates = parse_date_safely(df["observation_date"])
    invalid_date_mask = parsed_dates.isna()
    fail_dates = int(invalid_date_mask.sum())
    flag_rejection(invalid_date_mask, "Unparseable observation_date")
    report.checks.append(
        DQCheckResult(
            check_name="Validity: Date Format",
            table_name="weather_observations",
            column_name="observation_date",
            status="FAIL" if fail_dates > 0 else "PASS",
            records_evaluated=len(df),
            records_failed=fail_dates,
            failure_rate_pct=round((fail_dates / len(df)) * 100, 2),
            details=f"Found {fail_dates} records with unparseable date values",
        )
    )

    # --------------------------------------------------------------------------
    # Check 3: Numeric Conversion & Boundary Checks
    # --------------------------------------------------------------------------
    temp_avg = coerce_numeric(df["temp_avg_c"])
    temp_max = coerce_numeric(df["temp_max_c"])
    temp_min = coerce_numeric(df["temp_min_c"])
    precip = coerce_numeric(df["precipitation_mm"])
    wind = coerce_numeric(df["wind_speed_kmh"])
    humidity = coerce_numeric(df["humidity_pct"])

    # Temperature out of bounds
    invalid_temp_avg = (temp_avg < TEMP_MIN_BOUND_C) | (temp_avg > TEMP_MAX_BOUND_C)
    invalid_temp_max = (temp_max < TEMP_MIN_BOUND_C) | (temp_max > TEMP_MAX_BOUND_C)
    invalid_temp_min = (temp_min < TEMP_MIN_BOUND_C) | (temp_min > TEMP_MAX_BOUND_C)
    temp_out_of_bounds = invalid_temp_avg | invalid_temp_max | invalid_temp_min
    fail_temp = int(temp_out_of_bounds.sum())
    flag_rejection(temp_out_of_bounds, "Temperature out of realistic bounds (-60C to +60C)")
    report.checks.append(
        DQCheckResult(
            check_name="Range Check: Temperature Bounds",
            table_name="weather_observations",
            column_name="temp_avg_c",
            status="FAIL" if fail_temp > 0 else "PASS",
            records_evaluated=len(df),
            records_failed=fail_temp,
            failure_rate_pct=round((fail_temp / len(df)) * 100, 2),
            details=f"Found {fail_temp} records violating temperature boundaries",
        )
    )

    # Temperature consistency: temp_min <= temp_max
    both_temps_present = temp_min.notna() & temp_max.notna()
    temp_inconsistent = both_temps_present & (temp_min > temp_max)
    fail_temp_inconsistent = int(temp_inconsistent.sum())
    flag_rejection(temp_inconsistent, "Inconsistent temperatures: min_temp > max_temp")
    report.checks.append(
        DQCheckResult(
            check_name="Consistency: Min <= Max Temp",
            table_name="weather_observations",
            column_name="temp_min_c/temp_max_c",
            status="FAIL" if fail_temp_inconsistent > 0 else "PASS",
            records_evaluated=int(both_temps_present.sum()),
            records_failed=fail_temp_inconsistent,
            failure_rate_pct=round(
                (fail_temp_inconsistent / max(1, int(both_temps_present.sum()))) * 100, 2
            ),
            details=f"Found {fail_temp_inconsistent} records where min_temp > max_temp",
        )
    )

    # Precipitation out of bounds (negative or extreme > 500mm)
    invalid_precip = (precip < PRECIP_MIN_BOUND_MM) | (precip > PRECIP_MAX_BOUND_MM)
    fail_precip = int(invalid_precip.sum())
    flag_rejection(invalid_precip, "Precipitation out of bounds (<0mm or >500mm)")
    report.checks.append(
        DQCheckResult(
            check_name="Range Check: Precipitation Bounds",
            table_name="weather_observations",
            column_name="precipitation_mm",
            status="FAIL" if fail_precip > 0 else "PASS",
            records_evaluated=len(df),
            records_failed=fail_precip,
            failure_rate_pct=round((fail_precip / len(df)) * 100, 2),
            details=f"Found {fail_precip} records with negative or extreme precipitation",
        )
    )

    # Wind speed out of bounds
    invalid_wind = (wind < WIND_MIN_BOUND_KMH) | (wind > WIND_MAX_BOUND_KMH)
    fail_wind = int(invalid_wind.sum())
    flag_rejection(invalid_wind, "Wind speed out of bounds (<0 or >300 km/h)")
    report.checks.append(
        DQCheckResult(
            check_name="Range Check: Wind Speed Bounds",
            table_name="weather_observations",
            column_name="wind_speed_kmh",
            status="FAIL" if fail_wind > 0 else "PASS",
            records_evaluated=len(df),
            records_failed=fail_wind,
            failure_rate_pct=round((fail_wind / len(df)) * 100, 2),
            details=f"Found {fail_wind} records with invalid wind speed",
        )
    )

    # Humidity out of bounds (0% to 100%)
    invalid_humidity = (humidity < HUMIDITY_MIN_BOUND) | (humidity > HUMIDITY_MAX_BOUND)
    fail_humidity = int(invalid_humidity.sum())
    flag_rejection(invalid_humidity, "Relative humidity out of bounds (0% to 100%)")
    report.checks.append(
        DQCheckResult(
            check_name="Range Check: Humidity Bounds",
            table_name="weather_observations",
            column_name="humidity_pct",
            status="FAIL" if fail_humidity > 0 else "PASS",
            records_evaluated=len(df),
            records_failed=fail_humidity,
            failure_rate_pct=round((fail_humidity / len(df)) * 100, 2),
            details=f"Found {fail_humidity} records with invalid humidity percentages",
        )
    )

    # --------------------------------------------------------------------------
    # Check 4: Duplicate Detection (station_id + parsed_date)
    # --------------------------------------------------------------------------
    clean_date_col = parsed_dates.dt.strftime("%Y-%m-%d")
    df_temp_dedup = df.copy()
    df_temp_dedup["_std_date"] = clean_date_col

    duplicate_mask = df_temp_dedup.duplicated(
        subset=["station_id", "_std_date"], keep="first"
    ) & (~missing_station_mask) & (~invalid_date_mask)
    fail_duplicates = int(duplicate_mask.sum())
    flag_rejection(duplicate_mask, "Duplicate observation for station and date")
    report.duplicate_count = fail_duplicates
    report.checks.append(
        DQCheckResult(
            check_name="Uniqueness: Station + Date",
            table_name="weather_observations",
            column_name="station_id, observation_date",
            status="WARN" if fail_duplicates > 0 else "PASS",
            records_evaluated=len(df),
            records_failed=fail_duplicates,
            failure_rate_pct=round((fail_duplicates / len(df)) * 100, 2),
            details=f"Detected {fail_duplicates} duplicate observation rows (will be deduplicated)",
        )
    )

    # --------------------------------------------------------------------------
    # Split into Valid and Quarantined datasets
    # --------------------------------------------------------------------------
    rejected_mask = rejection_reasons != ""
    rejected_df = df[rejected_mask].copy()
    rejected_df["rejection_reason"] = rejection_reasons[rejected_mask]

    clean_df = df[~rejected_mask].copy()
    # Apply normalized dates to clean records
    clean_df["observation_date"] = clean_date_col[~rejected_mask]

    report.valid_count = len(clean_df)
    report.rejected_count = len(rejected_df)

    return clean_df, rejected_df, report
