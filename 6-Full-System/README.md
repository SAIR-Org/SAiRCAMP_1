# Module 6 — Full System

Online + Offline running together. One command starts everything.

---

## What This Module Is

Modules 4 and 5 are standalone systems that share the same model registry but run independently.
Module 6 wires them into one integrated system with a unified dashboard.

```
Module 4 alone:   Online API → real-time predictions
Module 5 alone:   Batch scoring → analytics + drift monitoring
Module 6:         Both running, dashboard shows everything in one place
```

---

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         Docker Network               │
                    │                                      │
User ──────────────▶│  api (port 8000)                    │
                    │  FastAPI /predict                    │
                    │  Loads @champion from MLflow         │
                    │                                      │
Analyst ───────────▶│  batch (port 8001)                  │
                    │  FastAPI /score /results             │
                    │  Scores all trips, detects drift     │
                    │                                      │
Dashboard ─────────▶│  dashboard (port 8501)              │
                    │  4 tabs: predict + batch +           │
                    │  drift chart + system/retrain        │
                    └─────────────────────────────────────┘
                              │         │
                    ┌─────────┴──┐  ┌───┴──────────────────┐
                    │  MLflow DB  │  │  predictions/         │
                    │  (SQLite)   │  │  batch_results.db     │
                    │  @champion  │  │  (bind mounted from   │
                    │  @challenger│  │  5-Deploy-Offline/)   │
                    └─────────────┘  └──────────────────────┘
```

---

## Quick Start

```bash
cd 6-Full-System

# Start everything (api + batch + dashboard)
docker compose up

# Services:
#   Online API:  http://localhost:8000/docs
#   Batch API:   http://localhost:8001/docs
#   Dashboard:   http://localhost:8501

# Stop everything
docker compose down
```

First startup takes ~2-3 minutes — MLflow migrations + model loading.

---

## The Dashboard — 4 Tabs

### Tab 1 — Predict
Live prediction via the online API.
- Fill in trip details → click Predict
- Returns duration in milliseconds
- Shows which model version is serving

### Tab 2 — Batch Results
Scored periods with drift metrics.
- Table: period, volume, MAE, ratio, alert status
- Trigger new scoring via batch API (runs in background ~2 min)
- Refreshes automatically

### Tab 3 — Drift Chart
MAE over time visualized.
- 3 panels: MAE, ratio, volume — color-coded red/green
- Alert details with recommended actions
- The COVID shock (2020-04) visible as a red spike

### Tab 4 — System & Retrain
All services status + manual retrain instructions.
- Health check for both APIs
- Prediction file inventory with size
- Exact command to run when retrain is needed

---

## The Retrain Workflow (Manual — Option A)

Monitoring detects drift → you decide to retrain → you run the command.

**When to retrain:**
- MAE ratio > 1.5x (model 50% worse than training)
- Volume collapse detected
- Both together (as in April 2020 COVID)

**How to retrain:**

```bash
# 1. Train challenger on expanded data (2019 + 2020)
cd 4-Deploy-Online/pipeline
python main.py \
  --train-years 2019,2020 \
  --sample-size 200000 \
  --no-tune
# → trains 6 models, picks best, registers as @challenger
# → compares vs @champion on 2020-06 holdout
# → promotes if challenger wins

# 2. Restart the API to serve the new champion
cd ../../6-Full-System
docker compose restart api

# 3. Check the dashboard — Predict tab shows new model version
```

**The champion/challenger gate:**
- New model trains on 2019 + 2020 data
- Evaluated on neutral 2020-06 holdout (not in training)
- Promoted only if MAE improvement > 0.1 min
- Without this gate, auto-retraining can silently make things worse

**What happened in this course:**
```
Champion v6:   MAE 4.59 min on 2020-06 holdout (trained on 2019 only)
Challenger v12: MAE 3.22 min on 2020-06 holdout (trained on 2019 + 2020)
Improvement: 1.37 min → v12 promoted to @champion automatically
```

---

## Services Reference

### Online API (port 8000)
| Endpoint | Description |
|----------|-------------|
| GET `/health` | Model version + alias |
| POST `/predict` | Predict trip duration |
| GET `/docs` | Swagger UI |

### Batch API (port 8001)
| Endpoint | Description |
|----------|-------------|
| GET `/health` | Status + summary |
| POST `/score?year=Y&month=M` | Trigger scoring in background |
| GET `/results` | All scored periods |
| GET `/results/{year}/{month}` | One period |
| GET `/predictions` | List parquet files |
| GET `/running` | Jobs in progress |
| GET `/docs` | Swagger UI |

---

## What This Module Teaches

**The full MLOps lifecycle in one system:**

```
Train → Register → Serve online → Score offline →
Detect drift → Decide to retrain → Train challenger →
Compare → Promote → Serve new model
```

Every step is visible. Every handoff is documented. The system is observable at every layer.

**Why manual retraining (not automatic):**
Automatic retraining without human review risks:
- Training on corrupted data
- Silent degradation (challenger wins on holdout, fails in production)
- Loss of accountability (who decided to change the model?)

The monitoring catches drift automatically. The retraining decision is human. This is the right balance for most production ML systems.

---

## File Structure

```
6-Full-System/
├── docker-compose.yml   api + batch + dashboard services
├── README.md
└── dashboard/
    ├── app.py           unified 4-tab Streamlit app
    ├── Dockerfile
    └── requirements.txt
```

Reuses Dockerfiles from:
- `4-Deploy-Online/api/Dockerfile`   — online API
- `5-Deploy-Offline/batch/Dockerfile` — batch API
