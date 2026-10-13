"""WeatherFlow Ingestion Module.

Step 1 of the ETL Pipeline:
- Extracts weather records from local CSV files or the official NOAA CDO API.
- Stores an immutable, timestamped copy in the raw data lake layer (data/raw/).
- Adheres to the Data Engineering 'Bronze Layer' pattern: never modify data at ingestion.
"""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd
import requests


# Default NOAA CDO v2 Web Service URL
NOAA_BASE_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2"


def get_project_root() -> Path:
    """Return the absolute path to the project root directory."""
    return Path(__file__).resolve().parent.parent


def archive_raw_file(source_path: Path, raw_dir: Optional[Path] = None) -> Path:
    """Create an immutable, timestamped backup of the ingested file in data/raw/.
    
    Data Engineering Concept:
    Raw ingestion layers (Bronze layer in Medallion architecture) should be
    immutable. If a pipeline bug is discovered later, you can replay the exact
    unprocessed input data without needing to re-fetch from the source.
    """
    if raw_dir is None:
        raw_dir = get_project_root() / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest_filename = f"raw_weather_{timestamp}_{source_path.name}"
    dest_path = raw_dir / dest_filename
    shutil.copy2(source_path, dest_path)
    return dest_path


def read_csv_data(file_path: Path) -> pd.DataFrame:
    """Read weather data from a local CSV file.
    
    Args:
        file_path: Path to the target CSV file.
        
    Returns:
        pd.DataFrame containing the raw ingested rows.
        
    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty or unreadable.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Source file not found at: {file_path}")

    # Read CSV without type coercion so raw fidelity is preserved for validation
    df = pd.read_csv(file_path, dtype=str, keep_default_na=False)

    if df.empty:
        raise ValueError(f"Source CSV file is empty: {file_path}")

    return df


def fetch_noaa_data(
    station_id: str,
    start_date: str,
    end_date: str,
    token: Optional[str] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    """Fetch daily weather observations from NOAA's Climate Data Online API.
    
    Args:
        station_id: NOAA station identifier (e.g. 'GHCND:USW00094728').
        start_date: ISO date string 'YYYY-MM-DD'.
        end_date: ISO date string 'YYYY-MM-DD'.
        token: NOAA API user token.
        limit: Max records per request (max 1000).
        
    Returns:
        pd.DataFrame containing API response records.
    """
    token = token or os.getenv("NOAA_TOKEN")
    if not token:
        raise ValueError(
            "NOAA API token not found! Set the NOAA_TOKEN environment variable "
            "or register for a free token at https://www.ncdc.noaa.gov/cdo-web/token"
        )

    headers = {"token": token}
    params = {
        "datasetid": "GHCND",
        "stationid": station_id,
        "startdate": start_date,
        "enddate": end_date,
        "limit": limit,
        "units": "metric",
    }

    response = requests.get(
        f"{NOAA_BASE_URL}/data",
        headers=headers,
        params=params,
        timeout=15,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"NOAA API error {response.status_code}: {response.text}"
        )

    payload = response.json()
    results = payload.get("results", [])
    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results)


def ingest_weather_data(
    source_path: Optional[Path] = None,
    use_noaa_api: bool = False,
    noaa_station_id: str = "GHCND:USW00094728",
    start_date: str = "2023-01-01",
    end_date: str = "2023-12-31",
) -> Tuple[pd.DataFrame, Path]:
    """Master ingestion entrypoint.
    
    Extracts raw weather data, archives a raw snapshot, and returns the DataFrame
    and the archived raw file path.
    """
    root = get_project_root()
    raw_dir = root / "data" / "raw"

    if use_noaa_api:
        api_token = os.getenv("NOAA_TOKEN")
        if not api_token:
            print("[INGESTION] NOAA_TOKEN not configured. Falling back to local CSV sample.")
            return ingest_weather_data(source_path=None, use_noaa_api=False)

        try:
            print(f"[INGESTION] Querying NOAA API for station {noaa_station_id}...")
            df_api = fetch_noaa_data(
                station_id=noaa_station_id,
                start_date=start_date,
                end_date=end_date,
                token=api_token,
            )
            if df_api.empty:
                print("[INGESTION] NOAA returned no records. Falling back to local sample CSV.")
                return ingest_weather_data(source_path=None, use_noaa_api=False)

            # Archive API payload as raw CSV
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            raw_dir.mkdir(parents=True, exist_ok=True)
            archived_path = raw_dir / f"raw_noaa_{timestamp}.csv"
            df_api.to_csv(archived_path, index=False)
            return df_api, archived_path
        except Exception as exc:
            print(f"[INGESTION] NOAA API request failed ({exc}). Falling back to local sample CSV.")
            return ingest_weather_data(source_path=None, use_noaa_api=False)

    # Ingest from CSV
    if source_path is None:
        source_path = root / "data" / "sample" / "weather_sample_raw.csv"

    print(f"[INGESTION] Reading raw source data from: {source_path}")
    df_raw = read_csv_data(source_path)

    # Archive into Bronze raw folder
    archived_path = archive_raw_file(source_path, raw_dir)
    print(f"[INGESTION] Archived {len(df_raw)} raw records to: {archived_path}")

    return df_raw, archived_path


if __name__ == "__main__":
    # Test script directly
    data, archive = ingest_weather_data()
    print(f"Ingestion successful! Loaded {len(data)} rows. Archive at: {archive}")
