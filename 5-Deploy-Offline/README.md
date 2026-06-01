# Module 5 — Deploy Offline

Batch deployment for analytics + drift monitoring.
The same model from Module 4, used in a completely different way.

---

## The Two Deployment Patterns

```
Module 4 — Online          Module 5 — Offline
─────────────────          ──────────────────
One request at a time      Millions at once
User is waiting            No one is waiting
FastAPI + Docker           Prefect + FastAPI + Docker
Milliseconds               Minutes to hours
Real-time predictions      Historical analytics + drift detection
```

Same model. Same MLflow registry. Two completely different execution paths.

---

## Architecture

```
5-Deploy-Offline/
├── batch/       Score all trips for a period → two outputs
│   ├── core.py      Pure scoring logic (no framework)
│   ├── flow.py      Prefect wrapper (local dev)
│   ├── api.py       FastAPI wrapper (Docker)
│   └── Dockerfile
├── monitoring/  Reads batch_results.db → health report + drift chart
├── dashboard/   Streamlit UI — batch results + drift story
│   └── Dockerfile
└── docker-compose.yml   batch (8001) + dashboard (8501)
```

---

## Two Outputs Per Batch Run

Every time the batch scorer runs for a period, it produces two artifacts:

```
predictions/YYYY_MM.parquet     per-trip predictions (batch deployment)
batch_results.db                aggregate drift metrics (monitoring)
```

**`predictions/YYYY_MM.parquet`** — analytics artifact:
```
pickup_datetime, PULocationID, DOLocationID, trip_distance,
actual_duration_minutes, predicted_duration_minutes, error_minutes, model_version
```
Use for: route analysis, what-if queries, A/B testing, reporting.

**`batch_results.db`** — monitoring artifact:
```
year, month, total_rows, mae, mae_ratio, target_mean, dist_mean, alert
```
Use for: drift chart, alert system, monitoring dashboard.

---

## The Drift Story

```
Train on 2019 → deploy → batch score by period → watch what happens

2019:   7.7M trips/month   MAE 3.07 min   ← train here
2020-04:  204k trips/month   MAE 5.55 min   ← COVID hits  ⚠️ ALERT (1.81x + volume collapse)
2022-01: 2.3M trips/month   MAE 3.00 min   ← recovery     ✅ OK
2024-01: 2.7M trips/month   MAE 3.18 min   ← stable       ✅ OK
```

**Alert conditions:**
```python
mae_alert    = (batch_mae / train_mae) > 1.5   # MAE degraded 50%+
volume_alert = total_rows < 500_000             # volume collapsed
```

**The lesson:** without monitoring, the 2020 COVID crash would go unnoticed.
The model silently serves 80% worse predictions for months. Monitoring catches it.

---

## Quick Start

### Option A — Docker (recommended)

```bash
cd 5-Deploy-Offline

# Start batch API + dashboard
docker compose up

# Batch API:  http://localhost:8001/docs
# Dashboard:  http://localhost:8501
```

To trigger scoring from the dashboard: **Tab 1 → Score a new period**.

Or via API:
```bash
# Trigger scoring for a period (runs in background ~2 min)
curl -X POST "http://localhost:8001/score?year=2020&month=4"

# Poll for result
curl http://localhost:8001/results/2020/4

# List all results
curl http://localhost:8001/results
```

---

### Option B — Local

```bash
# From repo root
uv sync && source .venv/bin/activate

# Score the default drift story periods (2020-04, 2022-01, 2024-01)
cd 5-Deploy-Offline/batch
python main.py

# Score a custom period
python main.py --periods 2020-01,2020-04,2020-07

# Run monitoring report
cd ../monitoring
python monitor.py

# Start dashboard
cd ../dashboard
streamlit run app.py
```

---

## Batch API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Status + summary |
| POST | `/score?year=Y&month=M` | Trigger scoring in background |
| GET | `/results` | All scored periods |
| GET | `/results/{year}/{month}` | One period |
| GET | `/predictions` | List parquet files |
| GET | `/running` | Jobs in progress |

The key teaching point:
- **Online API** → synchronous → returns in milliseconds
- **Batch API** → async background task → fires and returns immediately, poll for result

---

## Monitoring

```bash
cd 5-Deploy-Offline/monitoring
python monitor.py
```

Reads `batch_results.db`, prints health report, saves `drift_chart.png`.

```
2020-04  ⚠️  MAE=5.55  ratio=1.81x  volume=204k   ALERT
2022-01  ✅  MAE=3.00  ratio=0.98x  volume=2.3M   OK
2024-01  ✅  MAE=3.18  ratio=1.04x  volume=2.7M   OK
```

---

## What's Next

Module 6 combines online (Module 4) + offline (Module 5):

```
Online API serves real-time predictions
Batch scores historical data → detects drift
Drift alert → triggers retrain (champion/challenger gate)
New champion → online API reloads automatically
```

The retrain component and the full integrated system live in Module 6.
