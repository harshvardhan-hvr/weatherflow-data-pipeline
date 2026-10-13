# WeatherFlow — Data Engineering Interview Preparation Guide

This guide contains **15 real-world interview questions and answers** tailored specifically for Graduate and Entry-Level Data Engineer roles. Every answer references concrete implementations from the **WeatherFlow** codebase, allowing you to speak authentically about architecture, challenges, trade-offs, and design decisions.

---

### Question 1: Can you walk me through the architecture of your WeatherFlow project?
**Model Answer:**
"WeatherFlow is an end-to-end weather ETL pipeline designed using the **Medallion Architecture** pattern:
1. **Bronze (Raw) Layer**: Ingestion reads raw data from local CSVs or NOAA's CDO REST API and immediately archives an immutable copy with a UTC timestamp in `data/raw/`. This guarantees data lineage and allows us to replay historical ingestion batches.
2. **Silver (Processed) Layer**: An automated validation layer validates schema contracts and physical domain boundaries (e.g. temperatures between -60°C and +60°C, non-negative precipitation). Corrupted records are quarantined with documented failure reasons, and clean records undergo feature engineering (season computation, precipitation classification, temp range) before being persisted to Parquet and CSV in `data/processed/`.
3. **Gold (Analytical / Serving) Layer**: Clean records are loaded idempotently into a PostgreSQL/SQLite dimensional star schema (`weather_observations`, `dim_date`, `dim_location`, `pipeline_runs`, `data_quality_results`). The reporting module runs analytical queries to export curated aggregations to `data/gold/` for downstream Power BI consumption."

---

### Question 2: What is 'idempotency' in data engineering, and how did you implement it in WeatherFlow?
**Model Answer:**
"An idempotent pipeline is one that produces the exact same state regardless of how many times it is executed with the same input. If an orchestrator triggers a retry due to a transient network timeout, a non-idempotent pipeline might insert duplicate rows, corrupting aggregations.

In WeatherFlow, I achieved idempotency through two mechanisms:
1. **Deterministic Primary Keys**: In `transformation.py`, I created surrogate keys for observations by taking the MD5 hash of natural business keys (`station_id` + `observation_date`).
2. **SQL UPSERT (`ON CONFLICT`)**: In `database.py`, the ingestion query uses `ON CONFLICT (station_id, observation_date) DO UPDATE SET ...` for facts, and `ON CONFLICT (date_key) DO NOTHING` for dimensions. 

When tested in `test_pipeline_rerun_idempotence`, running the pipeline twice against the database resulted in the exact same record count (83 rows) without primary key collisions or duplicated facts."

---

### Question 3: How did you design the dimensional model for this project, and why a Star Schema?
**Model Answer:**
"I designed a **Star Schema** with:
- **Fact Table**: `weather_observations` containing daily numerical measurements (`temp_avg_c`, `precipitation_mm`, `wind_speed_kmh`) and foreign keys to dimensions.
- **Dimension Tables**: `dim_date` (containing calendar attributes such as `year`, `month`, `quarter`, `day_of_week`, `is_weekend`, `season`) and `dim_location` (station name, coordinates, elevation, state).
- **Metadata Tables**: `pipeline_runs` and `data_quality_results`.

I chose a Star Schema because:
1. It separates numerical facts from slowly changing descriptive context.
2. It optimizes OLAP analytical queries: queries joining a central fact table to conformed dimensions require simple, predictable joins (`dim_date` on `date_key`).
3. It maps directly into BI tools like Power BI without requiring data modeling recalculations during dashboard rendering."

---

### Question 4: What types of data quality checks did you implement, and how do you handle bad data?
**Model Answer:**
"In `src/validation.py`, I implemented three tiers of checks:
1. **Schema Contracts**: Verifying required columns exist before processing.
2. **Completeness & Nulls**: Ensuring critical identifiers like `station_id` and dates are non-empty.
3. **Domain Boundary Checks**:
   - Physical temperature limits ($-60^\circ\text{C} \le T \le +60^\circ\text{C}$) to catch faulty sensor output like $999.0^\circ\text{C}$.
   - Logical consistency checks: verifying $T_{\min} \le T_{\max}$.
   - Non-negativity constraints: ensuring precipitation $\ge 0\text{ mm}$ and wind speed $\ge 0\text{ km/h}$.
   - Humidity bounded between $0\%$ and $100\%$.

Rather than silently dropping bad data or crashing the entire batch, I adopted a **Quarantining Pattern**: invalid rows are isolated into `quarantined_rejected_records.csv` with explicit rejection reasons, and check outcomes are logged to the `data_quality_results` database table."

---

### Question 5: Why did you save the Silver layer in Parquet instead of only CSV?
**Model Answer:**
"While CSV is human-readable, **Apache Parquet** provides significant data engineering benefits:
1. **Columnar Storage**: Analytical queries often aggregate specific columns (e.g. `AVG(temp_avg_c)`). Columnar formats read only the requested byte ranges, avoiding full row deserialization.
2. **Embedded Schema & Types**: Parquet preserves exact data types (integers, floats, dates) unlike CSV where numbers and dates must be re-inferred on each read.
3. **Compression & File Size**: Parquet incorporates dictionary encoding and snappy/gzip compression, resulting in significantly lower disk footprint and I/O overhead.

In WeatherFlow, I used `pyarrow` to write Parquet for storage efficiency while maintaining a CSV export for easy inspection."

---

### Question 6: Why did you use SQLAlchemy instead of raw `psycopg2` or `sqlite3` cursors?
**Model Answer:**
"Using SQLAlchemy provided three key advantages:
1. **Database Agnosticism**: SQLAlchemy abstracts dialect-specific mechanics. WeatherFlow supports local SQLite development (`sqlite:///data/weatherflow.db`) out-of-the-box and can switch to production PostgreSQL simply by altering the `DATABASE_URL` environment variable, without altering the core pipeline logic.
2. **Connection Pooling**: SQLAlchemy manages connection lifecycles and prevents socket exhaustion.
3. **Transaction Management**: Using `with engine.begin() as conn:` ensures atomic transactions: if the fact table loading encounters an error halfway through, the entire transaction rolls back, preventing partial or corrupt database states."

---

### Question 7: How do you handle missing values in sensor telemetry?
**Model Answer:**
"In weather observations, sensor data is frequently missing due to hardware transmission errors. In `src/transformation.py`, I applied domain-specific handling:
- **Calculated Imputation**: If `temp_avg_c` was missing but both `temp_min_c` and `temp_max_c` were present, I imputed average temperature using $(T_{\min} + T_{\max}) / 2$.
- **Categorical Defaults**: Missing weather conditions defaulted to `'Unknown'` rather than null.
- **Categorization Flags**: Precipitation classifications flag missing values explicitly as `'Missing'`.
- All imputations and data treatments are audited in the `data_quality_results` table so downstream analysts know the data provenance."

---

### Question 8: How did you test your data pipeline?
**Model Answer:**
"I built a 24-test suite using **Pytest** covering:
1. **Unit Tests for Ingestion**: Valid CSV reading, missing file exceptions (`FileNotFoundError`), empty file rejection, and Bronze raw archival copying.
2. **Unit Tests for Validation**: Boundary violations (impossible temperatures, negative precipitation, inverted min/max, unparseable dates) and duplicate detection.
3. **Unit Tests for Transformations**: Season classification pure functions, deterministic hashing, and dimension extraction.
4. **Database Tests**: Schema creation, audit logging, and **idempotency verification** (asserting that loading identical data twice yields the exact same row count).
5. **End-to-End Integration Tests**: Executing the orchestrator on an isolated temporary SQLite database and verifying Gold exports and database table counts."

---

### Question 9: What is the difference between an OLTP database and an OLAP data warehouse?
**Model Answer:**
"**OLTP (Online Transaction Processing)** systems (like application databases) are optimized for high-concurrency, low-latency row inserts, updates, and lookups, typically highly normalized (3NF) to minimize write redundancy.

**OLAP (Online Analytical Processing)** systems (like Snowflake, BigQuery, Redshift, or dimensional PostgreSQL models) are optimized for complex aggregations across millions of rows (sums, averages, grouping). They favor de-normalized or star schema structures with fewer joins, columnar storage, and pre-aggregated summary tables."

---

### Question 10: How do you ensure secrets and database credentials aren't leaked to GitHub?
**Model Answer:**
"I used the standard twelve-factor app pattern with `python-dotenv`:
1. Sensitive credentials like `DATABASE_URL` and `NOAA_TOKEN` are stored exclusively in a local `.env` file.
2. `.env` is explicitly declared in `.gitignore`.
3. A sanitized `.env.example` file is committed to version control, containing placeholder values and setup instructions so other developers know which configuration parameters are required."

---

### Question 11: What would you do if your input dataset grew from 10,000 rows to 100 million rows?
**Model Answer:**
"For single-node workloads up to a few million rows, Pandas and single-node PostgreSQL are efficient. If the data scaled to 100 million daily observations:
1. **Distributed Processing**: I would transition the transformation layer from Pandas to **PySpark** or **Polars**, running partitioned transformations across a cluster.
2. **Cloud Storage**: Replace local `data/raw/` with **Azure Data Lake Storage (ADLS)** or **AWS S3** organized in partitioned prefixes (`/year=2023/month=01/`).
3. **Cloud Data Warehouse**: Load the dimensional star schema into **Snowflake** or **Google BigQuery** using bulk COPY/MERGE utilities rather than single-row or small batch inserts.
4. **Chunked Processing**: If restricted to local hardware, process the source using chunked streaming (`pd.read_csv(chunksize=50000)`)."

---

### Question 12: How would you orchestrate this pipeline in production?
**Model Answer:**
"In production, I would orchestrate WeatherFlow using **Apache Airflow**:
1. Define a DAG scheduled to run daily at 01:00 UTC (after NOAA publishes final daily sensor logs).
2. Decompose pipeline steps into discrete Airflow Tasks using the `PythonOperator` or `DockerOperator`:
   - `extract_and_archive_sensor_data`
   - `validate_data_quality` (with branching to alert if failure rate exceeds threshold)
   - `transform_silver_features`
   - `upsert_star_schema`
   - `generate_gold_exports`
3. Use Airflow's built-in retry policies, email/Slack failure alerting, and dependency management to ensure tasks only run if prerequisite validation tasks succeed."

---

### Question 13: Explain one complex SQL query you wrote in `analytics.sql`.
**Model Answer:**
"In Query 2 (Monthly Total Precipitation), I aggregated rainfall trends by month and station:
```sql
SELECT 
    d.year, d.month, d.month_name, l.station_name,
    ROUND(SUM(w.precipitation_mm), 2) AS total_precipitation_mm,
    ROUND(AVG(w.precipitation_mm), 2) AS avg_daily_precipitation_mm,
    ROUND(MAX(w.precipitation_mm), 2) AS max_single_day_rain_mm,
    SUM(CASE WHEN w.precipitation_mm > 0.0 THEN 1 ELSE 0 END) AS rainy_days_count
FROM weather_observations w
JOIN dim_date d ON w.date_key = d.date_key
JOIN dim_location l ON w.station_id = l.station_id
GROUP BY d.year, d.month, d.month_name, l.station_name
ORDER BY total_precipitation_mm DESC;
```
This query demonstrates multi-table star schema joins, SQL aggregation functions (`SUM`, `AVG`, `MAX`), conditional aggregation (`SUM(CASE WHEN ...)` to count rainy days without subqueries), and rounding for clean reporting."

---

### Question 14: What metrics do you track in `pipeline_runs` and why?
**Model Answer:**
"In `pipeline_runs`, I log:
- `run_id`: Unique run identifier.
- `pipeline_name`: To distinguish between different pipeline jobs.
- `started_at` & `completed_at`: To calculate elapsed runtime and detect pipeline performance degradation over time.
- `status`: SUCCESS, FAILED, or RUNNING.
- `records_read`, `records_clean`, `records_rejected`, `records_loaded`: To compute data retention rates and catch anomalies where input volume abruptly drops.
- `error_message`: Stack trace or failure description for fast root-cause analysis.

This table provides operational visibility and SLAs for data engineering teams."

---

### Question 15: What was the biggest technical challenge you faced while building WeatherFlow, and how did you resolve it?
**Model Answer:**
"The biggest challenge was handling dirty real-world sensor data while ensuring the pipeline remained completely **rerunnable and deterministic**:
- Real weather stations occasionally transmit corrupt spikes (e.g. 999.0°C), duplicate observations, or inverted temperatures. If allowed into the fact table, these skew monthly averages.
- Simply discarding corrupted records without auditing created a visibility gap.
- I resolved this by designing an isolated validation and quarantine stage. Instead of hard-failing the entire run, corrupt records are isolated with specific error reasons, and check metrics are committed to `data_quality_results`.
- Furthermore, by hashing natural keys into deterministic MD5 observation IDs and implementing database UPSERT queries with `ON CONFLICT DO UPDATE`, the pipeline became fully idempotent, allowing any batch to be safely re-run without manual database cleanup."
