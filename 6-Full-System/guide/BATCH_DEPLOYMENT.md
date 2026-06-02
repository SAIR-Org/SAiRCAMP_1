# Batch Deployment — Mental Model, Concepts & Reference

---

## Part 1 — What Is Batch Deployment? (The Mental Model)

### Start with a bank

A bank has two systems that do the same thing — process transactions:

**The ATM** — online, real-time:
- One customer at a time
- Response in seconds
- Always running, always ready
- Customer is waiting

**The monthly statement** — offline, batch:
- Every account at once
- Runs overnight, takes hours
- Nobody is waiting
- Output stored for later use

Both do "process transactions." The difference is *who is waiting* and *how many at once*.

**ML has the same split.** The question is never "which is better" — it's "which fits the use case."

---

### Online vs Offline — when to use which

```
Online (Module 4)                 Offline / Batch (Module 5)
─────────────────                 ──────────────────────────
User is waiting                   Nobody waiting
One prediction at a time          Millions at once
Milliseconds matter               Minutes or hours are fine
Real-time decision                Historical analysis
Cannot pre-compute                Can pre-compute

Example: "How long will           Example: "Score every January 2020
my trip take right now?"          trip — was our model good that month?"
```

**This course has both:**
- Module 4: online API — user asks, model answers instantly
- Module 5: batch scorer — score entire months, store results for analysis

Same model. Same preprocessing. Same MLflow registry. Completely different execution pattern.

---

### Why batch for analytics?

Imagine you want to answer:
- "Which pickup zones had the worst predictions last month?"
- "Did our model degrade after COVID?"
- "How does accuracy vary by trip distance?"

You cannot answer these from the online API — it only answers one trip at a time and stores nothing.

You need to:
1. Download all trips for a period
2. Run the model on every trip
3. Store actual vs predicted for each trip
4. Query the results

That's batch deployment. The output is a dataset you can analyze, not a prediction you consume immediately.

---

## Part 2 — The Two-Output Design

This is the key architectural decision in Module 5.

Every batch run produces **two artifacts** from one model pass:

```
Input: TLC parquet for one month (e.g., April 2020, 204k rows)
         ↓
   Model scores all trips
         ↓
         ├── predictions/2020_04.parquet    ← batch deployment artifact
         └── batch_results.db (one row)    ← drift monitoring artifact
```

**Why two outputs from one pass?**

Because scoring is expensive (download + preprocess + predict). Do it once. Use the results for both purposes.

---

### Output 1 — predictions/YYYY_MM.parquet (analytics)

```
pickup_datetime  PULocationID  DOLocationID  trip_distance
actual_duration_minutes  predicted_duration_minutes  error_minutes  model_version
```

Every trip. Every prediction. Stored permanently.

**What you can do with this:**

```python
import pandas as pd

df = pd.read_parquet("predictions/2020_04.parquet")

# Which routes did the model struggle most with?
worst_routes = (
    df.groupby(["PULocationID", "DOLocationID"])["error_minutes"]
    .apply(lambda x: abs(x).mean())
    .sort_values(ascending=False)
    .head(10)
)

# How does accuracy vary by trip distance?
df["distance_bucket"] = pd.cut(df["trip_distance"], bins=[0, 2, 5, 10, 50])
df.groupby("distance_bucket")["error_minutes"].abs().mean()

# What percentage of predictions were within 2 minutes?
(abs(df["error_minutes"]) <= 2).mean()
```

This is the "analytics" in batch deployment. The model becomes a tool for retrospective analysis, not just real-time prediction.

---

### Output 2 — batch_results.db (drift monitoring)

```sql
year, month, total_rows, mae, mae_ratio, target_mean, dist_mean, alert
```

One row per period. Lightweight. Monitoring reads this.

```python
import sqlite3, pandas as pd

df = pd.read_sql("SELECT * FROM batch_results ORDER BY year, month",
                 sqlite3.connect("batch_results.db"))

# The drift story in two lines
print(df[["period", "mae", "mae_ratio", "alert"]])
```

---

## Part 3 — The Async API Pattern

The batch scorer is wrapped in a FastAPI — but it works differently from the online API.

**Online API (Module 4):**
```
POST /predict  →  model runs (~5ms)  →  returns prediction
```
Synchronous. Client waits. Response arrives in milliseconds.

**Batch API (Module 5):**
```
POST /score?year=2020&month=4  →  returns immediately  →  job runs in background (~2 min)
```
Asynchronous. Client does not wait. Job runs in the background.

Why? Because scoring 204,000 trips takes ~2 minutes. An HTTP connection cannot stay open that long.

**The pattern in code:**

```python
# api.py
from fastapi import BackgroundTasks

_running_jobs: set = set()

def _run_score_job(year: int, month: int):
    # This runs in the background — not blocking the HTTP response
    champion = core.load_champion()
    result   = core.score_month(year, month, champion)
    core.save_result(result, champion)
    _running_jobs.discard((year, month))

@app.post("/score")
async def trigger_score(year: int, month: int, background_tasks: BackgroundTasks):
    _running_jobs.add((year, month))
    background_tasks.add_task(_run_score_job, year, month)

    return {"status": "started", "message": f"Poll /results/{year}/{month} when ready"}
    # ← returns in milliseconds, job runs independently
```

**Client workflow:**
```bash
# 1. Trigger — returns immediately
curl -X POST "http://localhost:8001/score?year=2020&month=4"
# → {"status": "started", "message": "Poll /results/2020/4 when ready"}

# 2. Check status
curl http://localhost:8001/running
# → [{"year": 2020, "month": 4}]  ← still running

# 3. Poll until result appears (~2 min)
curl http://localhost:8001/results/2020/4
# → {"mae": 5.55, "mae_ratio": 1.81, "alert": 1, ...}
```

---

## Part 4 — The Three-Layer Architecture

The batch module has three layers to keep concerns separate:

```
core.py      pure scoring logic — no Prefect, no FastAPI
  ↓ imported by both
flow.py      Prefect wrapper — adds @task/@flow for local dev observability
api.py       FastAPI wrapper — adds HTTP interface for Docker deployment
```

**Why three layers?**

The scoring logic (download → preprocess → predict → save) is the same regardless of how you trigger it. Separating it means:

- Locally with Prefect: `python main.py` — you see every task in the Prefect output
- Via Docker API: `POST /score` — you trigger it over HTTP, it runs in background
- In a script: `import core; core.score_month(2020, 4, champion)` — direct call

Same logic. Three entry points. No code duplication.

```python
# core.py — pure logic, importable anywhere
def score_month(year, month, champion):
    ...
    return result

# flow.py — adds Prefect observability
@task(name="score-month")
def score_month_task(year, month, champion):
    result = core.score_month(year, month, champion)
    logger.info(f"MAE: {result['mae']:.2f}")
    return result

# api.py — adds HTTP interface
@app.post("/score")
async def trigger_score(year, month, background_tasks):
    background_tasks.add_task(_run_score_job, year, month)
    return {"status": "started"}
```

---

## Part 5 — Connecting Concepts to Code

### The full flow

```
1. docker compose up           → starts batch API (port 8001) + dashboard (port 8501)

2. POST /score?year=2020&month=4
   → background_tasks.add_task(_run_score_job, 2020, 4)
   → returns {"status": "started"} in milliseconds

3. _run_score_job runs in background:
   → core.load_champion()         loads model + preprocessor from MLflow
   → core.score_month(2020, 4)    downloads 204k trips, scores all, saves parquet
   → core.save_result()           writes to SQLite + logs to MLflow

4. GET /results/2020/4
   → reads from batch_results.db
   → {"mae": 5.55, "mae_ratio": 1.81, "alert": 1}

5. Dashboard reads batch_results.db
   → Tab 1: shows results table
   → Tab 2: plots drift chart (red bar for 2020-04)
```

### The data flow

```
TLC website               batch/core.py            batch/predictions/
yellow_tripdata           ─────────────            2020_04.parquet ← analytics
_2020-04.parquet    →     download +           →
                          preprocess +             batch_results.db ← monitoring
                          score all trips     →    (one row: year=2020, month=4)
```

---

## Quick Reference

```bash
# Local — Prefect flow (development)
cd 5-Deploy-Offline/batch
python main.py                              # default: 2020-04, 2022-01, 2024-01
python main.py --periods 2020-01,2020-04   # custom periods

# Docker — FastAPI (deployment)
cd 5-Deploy-Offline
docker compose up

# API calls
curl http://localhost:8001/health
curl -X POST "http://localhost:8001/score?year=2020&month=4"
curl http://localhost:8001/results
curl http://localhost:8001/results/2020/4
curl http://localhost:8001/predictions

# Query predictions
python -c "
import pandas as pd
df = pd.read_parquet('batch/predictions/2020_04.parquet')
print(df.shape, df.columns.tolist())
"
```
