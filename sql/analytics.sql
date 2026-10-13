-- ==============================================================================
-- WeatherFlow Analytical & Data Quality SQL Queries
-- ==============================================================================
-- Designed for star schema: weather_observations, dim_date, dim_location
-- Fully compatible with PostgreSQL and SQLite standard SQL
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Query 1: Monthly Average Temperature by Station and Overall
-- Purpose: Monitor warming/cooling trends throughout the year across locations
-- ------------------------------------------------------------------------------
SELECT 
    d.year,
    d.month,
    d.month_name,
    l.station_name,
    ROUND(AVG(w.temp_avg_c), 2) AS avg_temperature_c,
    ROUND(MIN(w.temp_min_c), 2) AS min_temperature_c,
    ROUND(MAX(w.temp_max_c), 2) AS max_temperature_c,
    COUNT(w.observation_id)     AS observation_days
FROM weather_observations w
JOIN dim_date d ON w.date_key = d.date_key
JOIN dim_location l ON w.station_id = l.station_id
GROUP BY d.year, d.month, d.month_name, l.station_name
ORDER BY d.year, d.month, l.station_name;


-- ------------------------------------------------------------------------------
-- Query 2: Monthly Total Precipitation and Rainy Days
-- Purpose: Quantify seasonal rainfall and identify high precipitation months
-- ------------------------------------------------------------------------------
SELECT 
    d.year,
    d.month,
    d.month_name,
    l.station_name,
    ROUND(SUM(w.precipitation_mm), 2) AS total_precipitation_mm,
    ROUND(AVG(w.precipitation_mm), 2) AS avg_daily_precipitation_mm,
    ROUND(MAX(w.precipitation_mm), 2) AS max_single_day_rain_mm,
    SUM(CASE WHEN w.precipitation_mm > 0.0 THEN 1 ELSE 0 END) AS rainy_days_count
FROM weather_observations w
JOIN dim_date d ON w.date_key = d.date_key
JOIN dim_location l ON w.station_id = l.station_id
GROUP BY d.year, d.month, d.month_name, l.station_name
ORDER BY total_precipitation_mm DESC;


-- ------------------------------------------------------------------------------
-- Query 3: Annual Weather Trends (Year-over-Year Summary)
-- Purpose: High-level annual climate profile across all operating stations
-- ------------------------------------------------------------------------------
SELECT 
    d.year,
    l.station_name,
    ROUND(AVG(w.temp_avg_c), 2)       AS annual_avg_temp_c,
    ROUND(MIN(w.temp_min_c), 2)       AS annual_record_low_c,
    ROUND(MAX(w.temp_max_c), 2)       AS annual_record_high_c,
    ROUND(SUM(w.precipitation_mm), 2) AS annual_total_precip_mm,
    ROUND(AVG(w.wind_speed_kmh), 2)   AS annual_avg_wind_kmh,
    COUNT(w.observation_id)           AS total_observations
FROM weather_observations w
JOIN dim_date d ON w.date_key = d.date_key
JOIN dim_location l ON w.station_id = l.station_id
GROUP BY d.year, l.station_name
ORDER BY d.year, annual_avg_temp_c DESC;


-- ------------------------------------------------------------------------------
-- Query 4: Extreme Weather Events (Top 5 Hottest and Coldest Observations)
-- Purpose: Identify severe meteorological peaks for risk and climate analysis
-- ------------------------------------------------------------------------------
-- Hottest 5 Observations
SELECT 
    'Hottest' AS extreme_type,
    w.observation_date,
    l.station_name,
    w.temp_max_c AS recorded_temp_c,
    w.weather_condition,
    w.humidity_pct
FROM weather_observations w
JOIN dim_location l ON w.station_id = l.station_id
WHERE w.temp_max_c IS NOT NULL
ORDER BY w.temp_max_c DESC
LIMIT 5;

-- Coldest 5 Observations
SELECT 
    'Coldest' AS extreme_type,
    w.observation_date,
    l.station_name,
    w.temp_min_c AS recorded_temp_c,
    w.weather_condition,
    w.wind_speed_kmh
FROM weather_observations w
JOIN dim_location l ON w.station_id = l.station_id
WHERE w.temp_min_c IS NOT NULL
ORDER BY w.temp_min_c ASC
LIMIT 5;


-- ------------------------------------------------------------------------------
-- Query 5: Station-Level Data Quality & Reporting Continuity
-- Purpose: Audit station reliability and observation date coverage
-- ------------------------------------------------------------------------------
SELECT 
    l.station_id,
    l.station_name,
    COUNT(w.observation_id)      AS total_records_received,
    MIN(w.observation_date)      AS first_observation_date,
    MAX(w.observation_date)      AS last_observation_date,
    ROUND(AVG(CASE WHEN w.temp_avg_c IS NOT NULL THEN 1.0 ELSE 0.0 END) * 100, 1) AS temp_completeness_pct,
    ROUND(AVG(CASE WHEN w.precipitation_mm IS NOT NULL THEN 1.0 ELSE 0.0 END) * 100, 1) AS precip_completeness_pct,
    ROUND(AVG(CASE WHEN w.wind_speed_kmh IS NOT NULL THEN 1.0 ELSE 0.0 END) * 100, 1) AS wind_completeness_pct
FROM dim_location l
LEFT JOIN weather_observations w ON l.station_id = w.station_id
GROUP BY l.station_id, l.station_name
ORDER BY total_records_received DESC;


-- ------------------------------------------------------------------------------
-- Query 6: Sensor Missing-Data Percentages (Overall Health Check)
-- Purpose: Measure sensor telemetry quality across the entire fact table
-- ------------------------------------------------------------------------------
SELECT 
    COUNT(*) AS total_observations_evaluated,
    ROUND(100.0 * SUM(CASE WHEN temp_avg_c IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS missing_temp_avg_pct,
    ROUND(100.0 * SUM(CASE WHEN temp_max_c IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS missing_temp_max_pct,
    ROUND(100.0 * SUM(CASE WHEN temp_min_c IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS missing_temp_min_pct,
    ROUND(100.0 * SUM(CASE WHEN precipitation_mm IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS missing_precip_pct,
    ROUND(100.0 * SUM(CASE WHEN wind_speed_kmh IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS missing_wind_pct,
    ROUND(100.0 * SUM(CASE WHEN humidity_pct IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS missing_humidity_pct
FROM weather_observations;


-- ------------------------------------------------------------------------------
-- Query 7: Seasonal Weather Profile Comparisons
-- Purpose: Compare climate characteristics across astronomical/meteorological seasons
-- ------------------------------------------------------------------------------
SELECT 
    d.season,
    ROUND(AVG(w.temp_avg_c), 2)       AS avg_season_temp_c,
    ROUND(MIN(w.temp_min_c), 2)       AS lowest_season_temp_c,
    ROUND(MAX(w.temp_max_c), 2)       AS highest_season_temp_c,
    ROUND(SUM(w.precipitation_mm), 2) AS total_season_precip_mm,
    ROUND(AVG(w.precipitation_mm), 2) AS avg_daily_precip_mm,
    ROUND(AVG(w.wind_speed_kmh), 2)   AS avg_season_wind_kmh,
    COUNT(w.observation_id)           AS total_observations
FROM weather_observations w
JOIN dim_date d ON w.date_key = d.date_key
GROUP BY d.season
ORDER BY 
    CASE d.season 
        WHEN 'Winter' THEN 1 
        WHEN 'Spring' THEN 2 
        WHEN 'Summer' THEN 3 
        WHEN 'Fall'   THEN 4 
        ELSE 5 
    END;
