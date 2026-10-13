-- ==============================================================================
-- WeatherFlow Database Schema (PostgreSQL & ANSI SQL Compatible)
-- ==============================================================================
-- Dimensional Star Schema for Weather Analytics, Pipeline Tracking & Data Quality
-- ==============================================================================

-- 1. Date Dimension Table
CREATE TABLE IF NOT EXISTS dim_date (
    date_key        INTEGER PRIMARY KEY,            -- Format: YYYYMMDD (e.g. 20230115)
    full_date       DATE NOT NULL UNIQUE,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      VARCHAR(20) NOT NULL,
    quarter         INTEGER NOT NULL,
    day_of_month    INTEGER NOT NULL,
    day_of_week     VARCHAR(20) NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    season          VARCHAR(20) NOT NULL
);

-- 2. Location / Weather Station Dimension Table
CREATE TABLE IF NOT EXISTS dim_location (
    station_id      VARCHAR(32) PRIMARY KEY,
    station_name    VARCHAR(128) NOT NULL,
    latitude        NUMERIC(8, 4),
    longitude       NUMERIC(8, 4),
    elevation       NUMERIC(8, 2),
    country         VARCHAR(64) DEFAULT 'US',
    state           VARCHAR(64),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Weather Observations Fact Table
CREATE TABLE IF NOT EXISTS weather_observations (
    observation_id   VARCHAR(64) PRIMARY KEY,       -- Deterministic MD5 hash of (station_id + date)
    station_id       VARCHAR(32) NOT NULL,
    date_key         INTEGER NOT NULL,
    observation_date DATE NOT NULL,
    temp_avg_c       NUMERIC(5, 2),
    temp_max_c       NUMERIC(5, 2),
    temp_min_c       NUMERIC(5, 2),
    temp_range_c     NUMERIC(5, 2),
    precipitation_mm NUMERIC(6, 2),
    precip_category  VARCHAR(20),
    wind_speed_kmh   NUMERIC(5, 2),
    humidity_pct     NUMERIC(5, 2),
    weather_condition VARCHAR(64),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_station_observation_date UNIQUE (station_id, observation_date),
    CONSTRAINT fk_obs_station FOREIGN KEY (station_id) REFERENCES dim_location(station_id),
    CONSTRAINT fk_obs_date FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);

-- 4. Pipeline Execution Audit Table
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id           VARCHAR(64) PRIMARY KEY,
    pipeline_name    VARCHAR(64) NOT NULL,
    started_at       TIMESTAMP NOT NULL,
    completed_at     TIMESTAMP,
    status           VARCHAR(20) NOT NULL,          -- SUCCESS, FAILED, RUNNING
    records_read     INTEGER DEFAULT 0,
    records_clean    INTEGER DEFAULT 0,
    records_rejected INTEGER DEFAULT 0,
    records_loaded   INTEGER DEFAULT 0,
    error_message    TEXT
);

-- 5. Data Quality Results Table
CREATE TABLE IF NOT EXISTS data_quality_results (
    check_id         VARCHAR(64) PRIMARY KEY,
    run_id           VARCHAR(64) NOT NULL,
    check_name       VARCHAR(128) NOT NULL,
    table_name       VARCHAR(64) NOT NULL,
    column_name      VARCHAR(64),
    status           VARCHAR(16) NOT NULL,          -- PASS, FAIL, WARN
    records_evaluated INTEGER DEFAULT 0,
    records_failed   INTEGER DEFAULT 0,
    failure_rate_pct NUMERIC(5, 2) DEFAULT 0.0,
    details          TEXT,
    checked_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dq_run FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_obs_station ON weather_observations(station_id);
CREATE INDEX IF NOT EXISTS idx_obs_date ON weather_observations(observation_date);
CREATE INDEX IF NOT EXISTS idx_obs_date_key ON weather_observations(date_key);
CREATE INDEX IF NOT EXISTS idx_dim_date_year_month ON dim_date(year, month);
CREATE INDEX IF NOT EXISTS idx_dq_run_id ON data_quality_results(run_id);
