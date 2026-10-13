# WeatherFlow — Deployment & Scheduling Guide

In modern Data Engineering, **deploying an ETL pipeline** differs from deploying a web app. Rather than running an HTTP server, deploying a batch pipeline involves:
1. **Automated Scheduling**: Running the ETL job on a scheduled cadence (e.g. daily at 06:00 UTC).
2. **Database Provisioning**: Storing facts and dimensions in a persistent cloud or containerized PostgreSQL database.
3. **Artifact Archiving**: Storing Gold analytical outputs and pipeline execution logs for downstream BI tools (Power BI, Tableau).

Here are the **three recommended deployment strategies**, starting from the simplest (100% free cloud deployment via GitHub Actions).

---

## Method 1: Cloud Deployment via GitHub Actions (Recommended & 100% Free)

This is already configured in `.github/workflows/pipeline.yml`. It runs directly on GitHub's cloud infrastructure without requiring you to install or run any software locally!

### How It Works:
1. Every time you push code, or **automatically every morning at 06:00 UTC**, GitHub spins up an Ubuntu cloud virtual machine.
2. It launches an ephemeral live PostgreSQL service.
3. It installs all Python dependencies, runs the **24 Pytest tests**, and executes the **WeatherFlow ETL pipeline**.
4. It packages the resulting Gold CSVs (`data/gold/*.csv`) and execution reports into a downloadable GitHub build artifact.

### How to Trigger It Manually Right Now:
1. Go to your repository on GitHub: `https://github.com/harshvardhan-hvr/weatherflow-data-pipeline`.
2. Click the **Actions** tab at the top.
3. Click on the **"WeatherFlow CI/CD & Scheduled ETL Pipeline"** workflow in the left sidebar.
4. Click the **Run workflow** button on the right $\rightarrow$ select branch `main` $\rightarrow$ click **Run workflow**.
5. Watch the steps execute with live green checkmarks!

### (Optional) Adding NOAA API Token as a GitHub Secret:
If you want the cloud runner to query live NOAA data:
1. In your GitHub repository, click **Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**.
2. Click **New repository secret**.
3. Name: `NOAA_TOKEN`
4. Value: *Paste your token* $\rightarrow$ Click **Add secret**.

---

## Method 2: Free Serverless Cloud PostgreSQL (Neon.tech or Supabase)

If you want a permanent, production cloud PostgreSQL database that you can connect directly to Power BI Desktop:

### Step 1: Create Free Database on Neon.tech (Takes 60 seconds)
1. Go to [neon.tech](https://neon.tech) and sign up with your GitHub account.
2. Click **Create Project** $\rightarrow$ name it `weatherflow`.
3. Neon will display your connection string, looking like:
   ```text
   postgresql://weatherflow_owner:AbCd123@ep-cool-fog-123456.us-east-2.aws.neon.tech/weatherflow?sslmode=require
   ```

### Step 2: Configure Your Local `.env`
Open your `.env` file and replace the `DATABASE_URL`:
```env
DATABASE_URL=postgresql://weatherflow_owner:AbCd123@ep-cool-fog-123456.us-east-2.aws.neon.tech/weatherflow?sslmode=require
```

### Step 3: Run the Pipeline to Populate Cloud Postgres
```powershell
python -m src.pipeline
```
Your pipeline will create the Star Schema tables and insert all 83 weather observations directly into the cloud database!

### Step 4: Connect Power BI to Cloud Postgres
1. Open Power BI Desktop $\rightarrow$ **Get Data** $\rightarrow$ **PostgreSQL Database**.
2. Enter the server hostname and database name provided by Neon.
3. Your dashboard will now read live from cloud PostgreSQL!

---

## Method 3: Containerized Deployment via Docker & Docker Compose

When you install **Docker Desktop** on Windows or deploy to a Linux cloud VM (AWS EC2 / Azure VM):

### Run Database + Pipeline in 1 Command:
```bash
docker compose up --build
```

### What Docker Compose Does:
1. Starts a dedicated `weatherflow-postgres` container on port 5432.
2. Waits until PostgreSQL passes internal healthchecks (`pg_isready`).
3. Builds the Python 3.12 container (`weatherflow-pipeline`), mounts local folders (`data/gold`, `reports`), and executes the pipeline.
4. Data persists in a named Docker volume (`postgres_data`).
