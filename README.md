# WeatherFlow — Weather Data Engineering Pipeline

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/database-PostgreSQL%20%7C%20SQLite-336791.svg)](https://www.postgresql.org/)
[![Testing](https://img.shields.io/badge/pytest-24%20passed-brightgreen.svg)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Table of Contents
- [1. Business Problem & Motivation](#1-business-problem--motivation)
- [2. System Architecture](#2-system-architecture)
- [3. Technology Stack & Why Each Tool Was Chosen](#3-technology-stack--why-each-tool-was-chosen)
- [4. Project Structure](#4-project-structure)
- [5. The 10-Step ETL Pipeline](#5-the-10-step-etl-pipeline)
- [6. Database & Dimensional Modeling (Star Schema)](#6-database--dimensional-modeling-star-schema)
- [7. Analytical SQL Queries](#7-analytical-sql-queries)
- [8. Installation & Setup Instructions](#8-installation--setup-instructions)
- [9. How to Run the Pipeline](#9-how-to-run-the-pipeline)
- [10. Running the Automated Tests](#10-running-the-automated-tests)
- [11. Inspecting Processed Data & Reports](#11-inspecting-processed-data--reports)
- [12. How to Upload This Project to GitHub](#12-how-to-upload-this-project-to-github)
- [13. Common Errors & Troubleshooting](#13-common-errors--troubleshooting)
- [14. Future Enhancements Roadmap (Stages 2–5)](#14-future-enhancements-roadmap-stages-25)

---

## 1. Business Problem & Motivation

Weather sensors across meteorological stations collect millions of observations daily. However, real-world sensor telemetry suffers from severe data quality issues:
- **Corrupted Readings**: Hardware malfunctions transmitting impossible temperatures (e.g., $999.0^\circ\text{C}$).
- **Negative Rainfall**: Sensor drift recording negative precipitation (e.g., $-10\text{ mm}$).
- **Duplicate Observations**: Unstable network connections triggering retried uploads for the same station and timestamp.
- **Inconsistent Formats**: Mixed date notations (`2023-01-05`, `01/06/2023`, `2023.01.07`).

If fed directly into reporting dashboards or machine learning models, bad data produces false averages and broken downstream metrics.

**WeatherFlow** solves this problem by providing an automated, resilient **Medallion ETL pipeline** that validates incoming data contracts, isolates and documents anomalies in a quarantine layer, loads clean observations into an idempotent Star Schema, and generates analytical extracts ready for business intelligence tools.

---

## 2. System Architecture

The pipeline follows the industry-standard **Medallion Architecture**:

```mermaid
flowchart TD
    subgraph S["Source Layer"]
        A1["NOAA CDO REST API"]
        A2["Sample Weather CSV"]
    end

    subgraph B["Bronze Layer (Raw Archive)"]
        B1["data/raw/<br>raw_weather_TIMESTAMP.csv<br><i>(Immutable Audit Trail)</i>"]
    end

    subgraph DQ["Data Quality & Quarantine"]
        V1{"Validation Engine<br><i>(Schema, Bounds, Dates)</i>"}
        Q1["data/processed/<br>quarantined_rejected_records.csv"]
    end

    subgraph S2["Silver Layer (Cleaned & Modeled)"]
        T1["Feature Engineering<br><i>(Seasons, Categories, Imputation)</i>"]
        P1["data/processed/<br>weather_cleaned.parquet<br>weather_cleaned.csv"]
    end

    subgraph D["Database (Star Schema)"]
        DB[("PostgreSQL / SQLite")]
        D1["dim_date"]
        D2["dim_location"]
        F1["weather_observations (Fact)"]
        M1["pipeline_runs (Audit)"]
        M2["data_quality_results (Audit)"]
    end

    subgraph G["Gold Layer (Serving / BI)"]
        G1["data/gold/<br>monthly_weather_summary.csv<br>station_performance_metrics.csv<br>seasonal_analysis.csv<br>powerbi_weather_model.csv"]
        BI["Microsoft Power BI / Tableau"]
    end

    A1 -->|Extract| B1
    A2 -->|Extract| B1
    B1 --> V1
    V1 -->|Fails Bounds / Corrupt| Q1
    V1 -->|Passes Checks| T1
    T1 --> P1
    T1 -->|Idempotent UPSERT| DB
    DB --- D1
    DB --- D2
    DB --- F1
    DB --- M1
    DB --- M2
    DB -->|Analytical Queries| G1
    G1 --> BI
```

---

## 3. Technology Stack & Why Each Tool Was Chosen

| Technology | Role | Why It Was Chosen |
| :--- | :--- | :--- |
| **Python 3.10+** | Core Pipeline Language | Ubiquitous standard in Data Engineering with robust ecosystem and clear syntax. |
| **Pandas** | Transformation & Data Wrangling | Fast, expressive data manipulation for tabular structured data. |
| **PyArrow** | Columnar Storage | High-performance read/write engine for **Apache Parquet** files. |
| **SQL (ANSI & Postgres)** | Analytical Modeling & Querying | The foundational lingua franca for querying dimensional warehouses and defining schema constraints. |
| **SQLAlchemy** | Database Abstraction & Pooling | Unified connection engine supporting both PostgreSQL and SQLite with automatic connection pooling and atomic transactions. |
| **PostgreSQL & SQLite** | Relational Database / Storage | **Dual-Engine design**: runs out-of-the-box locally on SQLite without requiring local daemon installations, and connects directly to production PostgreSQL via `.env`. |
| **Pytest** | Automated Testing | Industry-standard testing framework ensuring pipeline reliability and zero regressions. |
| **Power BI Exports** | Business Intelligence Serving | Curated Gold layer CSV exports designed for instant visualization and KPI tracking. |

---

## 4. Project Structure

```text
weatherflow/
├── data/
│   ├── sample/
│   │   └── weather_sample_raw.csv        # Realistic raw CSV with deliberate real-world anomalies
│   ├── raw/                              # Bronze Layer: timestamped immutable raw archives
│   ├── processed/                        # Silver Layer: cleaned Parquet, CSV, & quarantined records
│   │   ├── weather_cleaned.parquet
│   │   ├── weather_cleaned.csv
│   │   └── quarantined_rejected_records.csv
│   ├── gold/                             # Gold Layer: aggregated Power BI extracts
│   │   ├── monthly_weather_summary.csv
│   │   ├── station_performance_metrics.csv
│   │   ├── seasonal_analysis.csv
│   │   └── powerbi_weather_model.csv
│   └── weatherflow.db                   # Local SQLite database (when SQLite engine is active)
├── docs/
│   ├── INTERVIEW_PREPARATION.md          # 15 in-depth interview questions & answers
│   ├── RESUME_BULLETS.md                 # Metric-backed resume bullets
│   └── POWERBI_DASHBOARD_GUIDE.md        # Step-by-step Power BI dashboard guide with DAX formulas
├── reports/                              # Auto-generated pipeline execution markdown reports
├── sql/
│   ├── schema.sql                        # Star Schema DDL, foreign keys, and indexes
│   └── analytics.sql                     # 7 core analytical and data quality queries
├── src/
│   ├── __init__.py
│   ├── ingestion.py                      # Data extraction from CSV/API & Bronze archival
│   ├── validation.py                     # Schema enforcement, boundary checking, and quarantining
│   ├── transformation.py                 # Feature engineering, season mapping, Parquet export
│   ├── database.py                       # SQLAlchemy pooling, DDL init, idempotent UPSERT loading
│   ├── reporting.py                      # Gold aggregation queries & Markdown report generation
│   └── pipeline.py                       # Master orchestrator CLI with structured logging
├── tests/
│   ├── __init__.py
│   ├── test_ingestion.py                 # Tests for CSV reading and archival
│   ├── test_validation.py                # Tests for boundary checks and corrupted data rejection
│   ├── test_transformation.py            # Tests for season derivation and feature engineering
│   ├── test_database.py                  # Tests for schema initialization and idempotent load
│   └── test_pipeline.py                  # End-to-end integration tests
├── .env.example                          # Environment variable template
├── .gitignore                            # Ignoring venv, caches, and raw generated files
├── requirements.txt                      # Project Python dependencies
└── README.md                             # Comprehensive project documentation
```

---

## 5. The 10-Step ETL Pipeline

1. **Extract**: Reads source weather data from the local sample CSV or the NOAA CDO v2 API.
2. **Raw Ingestion (Bronze)**: Archives an exact, unaltered copy to `data/raw/raw_weather_TIMESTAMP.csv` for data provenance and replayability.
3. **Validate Schema**: Checks that all 9 required schema columns exist and formats are expected.
4. **Clean & Quarantine**: Flags out-of-bounds temperatures (outside $[-60^\circ\text{C}, +60^\circ\text{C}]$), negative precipitation, impossible humidity ($>100\%$), unparseable dates, and duplicates into `quarantined_rejected_records.csv`.
5. **Transform Formats**: Normalizes dates to ISO `YYYY-MM-DD` and casts sensor metrics into numerical types.
6. **Feature Engineering**: Derives `season` (Winter, Spring, Summer, Fall), `precip_category` (None, Light, Moderate, Heavy), and `temp_range_c`.
7. **Model Star Schema**: Extracts conformed `dim_date` and `dim_location` tables, generating deterministic MD5 observation IDs.
8. **Idempotent Load**: Loads facts and dimensions using SQL `ON CONFLICT DO UPDATE` (UPSERT). Re-running the pipeline never creates duplicates.
9. **Export Gold Aggregates**: Executes analytical SQL queries and saves 4 Power BI-ready datasets to `data/gold/`.
10. **Report**: Generates an execution audit report in console and as Markdown in `reports/`, logging metadata to `pipeline_runs` and `data_quality_results`.

---

## 6. Database & Dimensional Modeling (Star Schema)

WeatherFlow uses a classic **Kimball Star Schema**:

```mermaid
erDiagram
    dim_location ||--o{ weather_observations : "records for"
    dim_date ||--o{ weather_observations : "occurred on"
    pipeline_runs ||--o{ data_quality_results : "evaluated by"

    dim_location {
        VARCHAR station_id PK
        VARCHAR station_name
        NUMERIC latitude
        NUMERIC longitude
        NUMERIC elevation
        VARCHAR country
        VARCHAR state
    }

    dim_date {
        INTEGER date_key PK
        DATE full_date
        INTEGER year
        INTEGER month
        VARCHAR month_name
        INTEGER quarter
        INTEGER day_of_month
        VARCHAR day_of_week
        BOOLEAN is_weekend
        VARCHAR season
    }

    weather_observations {
        VARCHAR observation_id PK
        VARCHAR station_id FK
        INTEGER date_key FK
        DATE observation_date
        NUMERIC temp_avg_c
        NUMERIC temp_max_c
        NUMERIC temp_min_c
        NUMERIC temp_range_c
        NUMERIC precipitation_mm
        VARCHAR precip_category
        NUMERIC wind_speed_kmh
        NUMERIC humidity_pct
        VARCHAR weather_condition
    }

    pipeline_runs {
        VARCHAR run_id PK
        VARCHAR pipeline_name
        TIMESTAMP started_at
        TIMESTAMP completed_at
        VARCHAR status
        INTEGER records_read
        INTEGER records_clean
        INTEGER records_rejected
        INTEGER records_loaded
        TEXT error_message
    }

    data_quality_results {
        VARCHAR check_id PK
        VARCHAR run_id FK
        VARCHAR check_name
        VARCHAR table_name
        VARCHAR column_name
        VARCHAR status
        INTEGER records_evaluated
        INTEGER records_failed
        NUMERIC failure_rate_pct
        TEXT details
        TIMESTAMP checked_at
    }
```

---

## 7. Analytical SQL Queries

All queries are defined in `sql/analytics.sql` and run seamlessly on PostgreSQL and SQLite:

1. **Monthly Average Temperature**: Aggregates monthly average, minimum, and maximum temperatures per station.
2. **Monthly Total Precipitation**: Calculates cumulative rainfall and counts days with measurable rain (`precipitation_mm > 0`).
3. **Annual Weather Trends**: Year-over-year summary comparing stations on average temperature and annual rainfall.
4. **Extreme Weather Events**: Top 5 hottest and top 5 coldest recorded observations with associated conditions.
5. **Station-Level Data Quality**: Audits observation date span and sensor completeness percentages ($100.0\%$).
6. **Missing-Data Percentages**: Fact-table health check calculating null percentages across every sensor reading.
7. **Seasonal Comparisons**: Evaluates meteorological season profiles (e.g., Summer avg $26.95^\circ\text{C}$ vs Winter avg $3.60^\circ\text{C}$).

---

## 8. Installation & Setup Instructions

### Prerequisites
- Python 3.10, 3.11, 3.12, or 3.13 installed on your machine.
- Git installed.

### Step 1: Clone or Navigate to the Repository
```bash
cd weatherflow
```

### Step 2: Create and Activate a Virtual Environment
**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Required Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
# On Windows PowerShell:
Copy-Item .env.example .env

# On Linux/macOS:
cp .env.example .env
```

**By default, `.env` uses SQLite (`DATABASE_URL=sqlite:///data/weatherflow.db`)**, allowing you to run immediately without installing PostgreSQL.

If you have PostgreSQL running, open `.env` and set:
```env
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/weatherflow
```

*(Optional)* To query live NOAA data, request a free token at [NOAA CDO Token Request](https://www.ncdc.noaa.gov/cdo-web/token) and paste it into `.env`:
```env
NOAA_TOKEN=your_token_here
```

---

## 9. How to Run the Pipeline

### Standard Run (Using Sample Dataset)
```bash
python -m src.pipeline
```

### Specifying a Custom CSV File
```bash
python -m src.pipeline --source path/to/your_weather_file.csv
```

### Running with NOAA API (When NOAA_TOKEN is set)
```bash
python -m src.pipeline --use-noaa --station GHCND:USW00094728 --start-date 2023-01-01 --end-date 2023-12-31
```

### Overriding Database Connection via CLI
```bash
python -m src.pipeline --db-url sqlite:///data/weatherflow.db
```

---

## 10. Running the Automated Tests

WeatherFlow comes with a complete **24-test Pytest suite** validating ingestion, boundary enforcement, transformation logic, schema creation, and database idempotency.

Run all tests:
```bash
python -m pytest tests/ -v
```

Expected output:
```text
tests/test_database.py::test_schema_initialization PASSED                [  4%]
tests/test_database.py::test_idempotent_loading PASSED                   [  8%]
tests/test_database.py::test_pipeline_run_audit_logging PASSED           [ 12%]
tests/test_database.py::test_data_quality_results_logging PASSED         [ 16%]
tests/test_ingestion.py::test_read_csv_success PASSED                    [ 20%]
tests/test_ingestion.py::test_read_csv_file_not_found PASSED             [ 25%]
tests/test_ingestion.py::test_read_csv_empty_file PASSED                 [ 29%]
tests/test_ingestion.py::test_archive_raw_file PASSED                    [ 33%]
tests/test_ingestion.py::test_ingest_weather_data_fallback PASSED        [ 37%]
tests/test_pipeline.py::test_full_pipeline_execution PASSED              [ 41%]
tests/test_pipeline.py::test_pipeline_rerun_idempotence PASSED           [ 45%]
tests/test_transformation.py::test_meteorological_season PASSED          [ 50%]
tests/test_transformation.py::test_categorize_precipitation PASSED       [ 54%]
tests/test_transformation.py::test_deterministic_observation_id PASSED   [ 58%]
tests/test_transformation.py::test_impute_missing_temperatures PASSED    [ 62%]
tests/test_transformation.py::test_extract_dim_date PASSED               [ 66%]
tests/test_transformation.py::test_transform_weather_data_end_to_end PASSED [ 70%]
tests/test_validation.py::test_schema_validation_success PASSED          [ 75%]
tests/test_validation.py::test_schema_validation_failure PASSED          [ 79%]
tests/test_validation.py::test_quarantine_impossible_temperature PASSED  [ 83%]
tests/test_validation.py::test_quarantine_inconsistent_temperatures PASSED [ 87%]
tests/test_validation.py::test_quarantine_negative_precipitation PASSED  [ 91%]
tests/test_validation.py::test_quarantine_missing_station_id PASSED      [ 95%]
tests/test_validation.py::test_duplicate_observations_flagged PASSED     [100%]

============================= 24 passed in 3.47s ==============================
```

---

## 11. Inspecting Processed Data & Reports

After running the pipeline, inspect the generated artifacts:
1. **Gold Layer Exports (for Power BI)**: Located in `data/gold/`.
   - `powerbi_weather_model.csv`
   - `monthly_weather_summary.csv`
   - `station_performance_metrics.csv`
   - `seasonal_analysis.csv`
2. **Silver Parquet & Clean CSV**: Located in `data/processed/weather_cleaned.parquet`.
3. **Quarantined Records**: Located in `data/processed/quarantined_rejected_records.csv`.
4. **Execution Audit Reports**: Located in `reports/pipeline_run_<run_id>.md`.

---

## 12. How to Upload This Project to GitHub

Follow these steps to publish WeatherFlow to your personal GitHub account:

### Step 1: Initialize Git Repository
```bash
git init
```

### Step 2: Stage and Commit the Files
```bash
git add .
git commit -m "feat: initial release of WeatherFlow data engineering pipeline"
```

### Step 3: Create a New GitHub Repository
1. Go to [GitHub.com](https://github.com) and click **New Repository**.
2. Name it `weatherflow-data-pipeline`.
3. Set visibility to **Public**.
4. Leave "Add a README" **unchecked** (we already created one).

### Step 4: Link and Push to GitHub
```bash
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/weatherflow-data-pipeline.git
git push -u origin main
```

---

## 13. Common Errors & Troubleshooting

| Error | Root Cause | Solution |
| :--- | :--- | :--- |
| `FileNotFoundError: Source file not found` | Pipeline cannot locate the input CSV file. | Run from project root or verify path passed to `--source`. |
| `ValueError: Schema validation failed` | Input CSV is missing required column names. | Ensure columns match `station_id`, `observation_date`, `temp_avg_c`, etc. |
| `psycopg2.OperationalError: could not connect to server` | PostgreSQL is not running or credentials in `.env` are invalid. | Default to SQLite in `.env` (`DATABASE_URL=sqlite:///data/weatherflow.db`) until PostgreSQL is active. |
| `NOAA API error 400/403` | Invalid NOAA token or exceeded rate limit (5 req/sec). | Verify token at [NOAA CDO](https://www.ncdc.noaa.gov/cdo-web/token) or omit `--use-noaa` to use sample CSV. |
| `PermissionError: [Errno 13] Access denied` | A file (e.g. `weatherflow.db` or CSV) is open in Excel or another program. | Close the file in Excel/DB Browser and re-run. |

---

## 14. Future Enhancements Roadmap (Stages 2–5)

To evolve WeatherFlow into an enterprise-scale distributed system, the following stages can be implemented sequentially:

### Stage 2: Containerization & PySpark Transformations
- **Docker**: Package the pipeline into a lightweight multi-stage Docker container (`Dockerfile` & `docker-compose.yml`) bundling PostgreSQL and Python.
- **PySpark**: Transition transformations from Pandas to PySpark DataFrame operations (`spark.read.parquet`), enabling distributed transformations across massive historical climate archives.

### Stage 3: Apache Airflow Orchestration
- Build an Airflow DAG (`weatherflow_dag.py`) scheduled to trigger daily.
- Separate extraction, quality checks, transformations, and gold exports into independent Airflow Tasks with automatic retry policies and Slack alerts.

### Stage 4: Azure Cloud Integration
- **Azure Blob Storage (ADLS Gen2)**: Replace local directories with Azure Data Lake Storage containers (`bronze/`, `silver/`, `gold/`).
- **Azure Key Vault**: Securely inject database credentials and API secrets into the pipeline runtime.

### Stage 5: Power BI Interactive Dashboard
- Follow [docs/POWERBI_DASHBOARD_GUIDE.md](docs/POWERBI_DASHBOARD_GUIDE.md) to build an interactive multi-page dashboard featuring slicers, KPI cards, geographic maps, and weather trend line charts.
