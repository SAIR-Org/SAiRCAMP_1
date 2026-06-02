# Module 6 — Full System

Complete, standalone MLOps system for NYC Yellow Taxi trip duration prediction.
Online serving + offline batch scoring + drift monitoring + unified dashboard.

**This module is self-contained.** Everything needed to run the full system is here.

---

## Concept Guides

| Guide | Covers |
|-------|--------|
| [MLFLOW_REGISTRY.md](MLFLOW_REGISTRY.md) | Registry vs tracking, aliases, loading by URI, preprocessor artifact |
| [DOCKER_FOR_ML.md](DOCKER_FOR_ML.md) | Images, containers, volumes, bind mounts, build context |
| [FASTAPI.md](FASTAPI.md) | Online vs batch serving, lifespan, Pydantic, async patterns |
| [BATCH_DEPLOYMENT.md](BATCH_DEPLOYMENT.md) | Two-output design, async API, three-layer architecture |
| [DRIFT_DETECTION.md](DRIFT_DETECTION.md) | MAE ratio, volume signal, why σ formula failed, COVID story |
| [SYSTEM_INTEGRATION.md](SYSTEM_INTEGRATION.md) | Docker networking, shared state, health checks, env vars |
| [MLOPS_LIFECYCLE.md](MLOPS_LIFECYCLE.md) | The full picture — where every tool fits across all modules |

---

## Architecture

```
6-Full-System/
├── shared/          Feature engineering — single source of truth
├── pipeline/        Train + register @champion (runs locally)
├── api/             FastAPI online serving (Docker, port 8000)
├── batch/           FastAPI batch scoring API (Docker, port 8001)
├── monitoring/      Drift report + chart (runs locally)
├── dashboard/       Streamlit unified UI (Docker, port 8501)
└── docker-compose.yml
```

```
                    ┌──────────────────────────────────────┐
                    │         6-Full-System Docker Network  │
                    │                                       │
User ──────────────▶│  api:8000   /predict                 │
                    │  Loads @champion from MLflow          │
                    │                                       │
Analytics ─────────▶│  batch:8001  /score /results         │
                    │  Scores all trips, detects drift      │
                    │                                       │
Dashboard ─────────▶│  dashboard:8501                      │
                    │  4 tabs: predict+batch+drift+system   │
                    └──────────────────────────────────────┘
                              │           │
                    ┌─────────┴──┐  ┌─────┴────────────────┐
                    │  pipeline/  │  │  batch/              │
                    │  MLflow DB  │  │  batch_results.db    │
                    │  mlruns/    │  │  predictions/*.parquet│
                    └─────────────┘  └──────────────────────┘
```

---

## The Drift Story

```
Train on 2019 → deploy → batch score monthly → monitor

2019:    7.7M trips   MAE 3.07 min  ← train here
2020-04:  204k trips   MAE 5.55 min  ← COVID ⚠️ ALERT
2022-01: 2.3M trips   MAE 3.00 min  ← recovery ✅
2024-01: 2.7M trips   MAE 3.18 min  ← stable ✅
```

The 2020 COVID collapse proves why monitoring exists.
Without it, the model silently serves 80% worse predictions for months.

---

## Quick Start

### Step 1 — Setup

```bash
# From repo root
uv sync && source .venv/bin/activate

cd 6-Full-System
```

### Step 2 — Train the model (local)

```bash
cd pipeline

# Quick smoke test (~5 min)
python main.py --sample-size 50000 --no-tune --promote

# Full run (~25 min, better model)
python main.py --sample-size 500000 --tune --promote
```

### Step 3 — Start the full system (Docker)

```bash
cd ..   # back to 6-Full-System/
docker compose up
```

| Service | URL |
|---------|-----|
| Online API | http://localhost:8000/docs |
| Batch API | http://localhost:8001/docs |
| Dashboard | http://localhost:8501 |

### Step 4 — Score batch periods

```bash
# Via API (background job)
curl -X POST "http://localhost:8001/score?year=2020&month=4"
curl -X POST "http://localhost:8001/score?year=2022&month=1"
curl -X POST "http://localhost:8001/score?year=2024&month=1"

# Or locally via Prefect flow
cd batch && python main.py
```

### Step 5 — Run monitoring

```bash
cd monitoring
python monitor.py
```

### Step 6 — View in dashboard

Open http://localhost:8501 — drift chart shows the story.

---

## Retrain Workflow (Manual)

When monitoring detects an alert (e.g., 2020-04 MAE ratio 1.81x):

```bash
# 1. Retrain on expanded data
cd pipeline
python main.py \
  --train-years 2019,2020 \
  --sample-size 200000 \
  --no-tune

# 2. Restart API to serve new @champion
cd ..
docker compose restart api

# 3. Dashboard shows new model version in Predict tab
```

**The champion/challenger gate:** new model evaluated on 2020-06 holdout.
Promoted only if it beats the current champion by > 0.1 min.

---

## Pipeline Run Options

```bash
cd pipeline

# Smoke test
python main.py --sample-size 50000 --no-tune --promote

# Full run
python main.py --sample-size 500000 --tune --promote

# Retrain on 2019 + 2020
python main.py --train-years 2019,2020 --sample-size 200000 --no-tune

# View MLflow
mlflow ui --backend-store-uri sqlite:///mlflow_trip_duration.db
```

---

## Project Structure

```
6-Full-System/
├── shared/
│   └── feature_engineering.py   TripFeatureEngineer, OutlierHandler, build_preprocessor
│
├── pipeline/                    Prefect flow, 9 steps, 6 models, MLflow tracking
│   ├── config/config.py         DataConfig (train_years), ModelConfig, MLflowConfig
│   ├── flow.py                  trip_duration_pipeline(train_years=, sample_size=, ...)
│   ├── main.py                  CLI entry point
│   └── src/
│       ├── data/                data_acquisition.py, data_preprocessing.py
│       ├── features/            feature_engineering.py (re-exports from shared/)
│       └── models/              model_training.py, model_registry.py
│
├── api/                         FastAPI online serving
│   ├── main.py                  /health + /predict
│   ├── model_loader.py          loads @champion + preprocessor from MLflow
│   └── schema.py                TripRequest, PredictionResponse
│
├── batch/                       Batch scoring — two entry points, one core
│   ├── core.py                  pure scoring logic
│   ├── flow.py                  Prefect wrapper (local dev)
│   ├── api.py                   FastAPI wrapper (Docker)
│   └── main.py                  CLI (runs Prefect flow)
│
├── monitoring/
│   └── monitor.py               reads batch_results.db → health report + drift chart
│
├── dashboard/
│   └── app.py                   4 tabs: predict + batch + drift + system/retrain
│
└── docker-compose.yml           api + batch + dashboard
```
