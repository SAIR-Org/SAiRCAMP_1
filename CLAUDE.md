# CLAUDE.md — Session Context for Claude Code

## Who You Are Talking To

**Silva is the TEACHER of this course, not a student.**
He is building the course material, designing the curriculum, and making architectural decisions.
Treat him as a domain expert making product decisions, not someone learning the tools.

---

## What This Project Is

**SAiRCAMP** — a hands-on, project-based MLOps course.
Single real-world problem: NYC Yellow Taxi trip duration prediction.
Built progressively across modules. Each module adds one concept on top of what already works.

The course runs in parallel with a companion theory course (DDODS).
SAiRCAMP is the applied, production-depth track.

---

## The Full Curriculum Arc

```
Module 1 — 1-intro_and_setup              (DONE, UNTOUCHED)
  Teaches: EDA, data leakage, feature engineering, basic sklearn
  Data: 2016 Kaggle CSV, lat/lon format
  Tool: Jupyter

Module 2 — 2-Exp_tracking                 (DONE, UNTOUCHED)
  Teaches: MLflow tracking, experiment comparison, model registry
  Data: 2016 Kaggle CSV
  Tool: MLflow

Module 3a — 3-Pipeline_and_Orchestrations/pipline_no_perfect  (DONE, UNTOUCHED)
  Teaches: pipeline class, clean code structure, retry logic
  Data: 2016 Kaggle CSV
  Tool: plain Python

Module 3b — 3-Pipeline_and_Orchestrations/pipeline_with_prefect  (DONE, UNTOUCHED)
  Teaches: Prefect @task/@flow, UI visibility, task-level retries
  Data: 2016 Kaggle CSV
  Tool: Prefect

Module 4 — 4-Deploy-Online                (DONE)
  Teaches: schema migration, MLflow registry + aliases, online serving, Docker for API
  Data: TLC 2019 parquet (direct download, zone IDs)
  Tools: FastAPI + Prefect (local) + MLflow + Docker (API only)

Module 5 — 5-Deploy-Offline               (DONE)
  Teaches: batch deployment for analytics, drift detection, monitoring dashboard
  Data: TLC 2020/2022/2024 parquet (the COVID shock-and-recovery story)
  Tools: Prefect + FastAPI + Streamlit + Docker
  Note: NO retrain here — retrain lives in Module 6

Module 6 — 6-Full-System                  (NEXT — not started)
  Teaches: online + offline combined, champion/challenger retrain, auto-promotion
  Combines Module 4 (online API) + Module 5 (batch/monitoring) into one system
  Adds: retrain flow, drift-triggered retraining, auto-promotion gate
```

---

## Module 4 — What Was Built (DONE)

Lives in `4-Deploy-Online/`. Complete and ready to teach.

```
4-Deploy-Online/
├── shared/           feature_engineering.py — single source of truth
├── pipeline/         Prefect flow, 9 steps, 6 models, MLflow, @champion
├── api/              FastAPI /predict, loads @champion from MLflow
├── docs/             DOCKER_DEBUGGING.md — three real Docker problems documented
├── docker-compose.yml
├── MLFLOW_REGISTRY.md
├── DOCKER_FOR_ML.md
└── FASTAPI.md
```

**Key decisions:**
- TLC 2019 data, zone IDs, 23 features
- MLflow 3.x aliases: `@champion` / `@challenger`
- Preprocessor + `train_mae` + `train_duration_mean` saved to MLflow
- Pipeline runs locally (Prefect + Docker incompatibility)
- API runs in Docker with bind mount + `MLFLOW_ARTIFACTS_ROOT` path remapping
- Best model: XGBoost v12, Test R² 0.817, MAE 3.07 min (after retrain on 2019+2020)
- `mlflow==3.13.0` pinned in both requirements.txt files

**Multi-year pipeline support:**
```python
# config.py: train_years: List[int] = [2019]  (was train_year: int)
# flow.py: accepts train_years parameter
trip_duration_pipeline(train_years=[2019, 2020], sample_size=200000)
```

---

## Module 5 — What Was Built (DONE)

Lives in `5-Deploy-Offline/`. Complete standalone offline deployment module.

```
5-Deploy-Offline/
├── batch/
│   ├── core.py              pure scoring logic (no framework)
│   ├── flow.py              Prefect wrapper (local dev)
│   ├── api.py               FastAPI wrapper (Docker, port 8001)
│   ├── Dockerfile
│   ├── main.py              CLI
│   └── batch_exploration.ipynb  ✅ validated drift approach
├── monitoring/
│   └── monitor.py           health report + drift_chart.png
├── dashboard/
│   ├── app.py               Streamlit 3 tabs
│   ├── Dockerfile
│   └── requirements.txt
└── docker-compose.yml       batch (8001) + dashboard (8501)
```

**Two outputs per batch run:**
- `predictions/YYYY_MM.parquet` — per-trip predictions for analytics
- `batch_results.db` — aggregate drift metrics for monitoring

**The drift story (validated from real data):**
```
2019:    7.7M trips   MAE 3.07 min  ← train
2020-04:  204k trips   MAE 5.55 min  ← COVID ⚠️ ALERT (1.81x + volume collapse)
2022-01: 2.3M trips   MAE 3.00 min  ← recovery ✅
2024-01: 2.7M trips   MAE 3.18 min  ← stable ✅
```

**Alert conditions:**
```python
mae_alert    = (batch_mae / train_mae) > 1.5
volume_alert = total_rows < 500_000
```

**Run the full offline stack:**
```bash
cd 5-Deploy-Offline
docker compose up
# Batch API:  http://localhost:8001
# Dashboard:  http://localhost:8501
```

**Batch API endpoints:** `/health` `/score` `/results` `/predictions` `/running`

**IMPORTANT — retrain lives in Module 6, NOT here.**
The champion/challenger retrain flow was built and tested (v12 promoted,
1.37 min better on 2020-06 holdout) but does not belong in the offline module.
It lives in Module 6 where online + offline are combined.

---

## Module 6 — The Plan (NEXT)

Lives in `6-Full-System/`. Not started.

```
6-Full-System/
├── retrain/     champion/challenger gate (built+tested in Module 5, lives here in Module 6)
└── compose/     full docker-compose: online API + batch + dashboard + retrain trigger
```

**The story:**
```
Online API serves real-time predictions (Module 4 API)
Batch scores historical data monthly (Module 5 batch)
Monitoring detects drift (Module 5 monitoring)
Drift alert → triggers retrain (champion/challenger)
New champion → online API reloads automatically
```

The retrain code is already built and tested. Module 6 wires it into the full system.

---

## Key Decisions — Permanent

1. **Modules 1–3 untouched forever.**
2. **Module 4+ uses TLC direct download.**
3. **Feature format: lat/lon → zone IDs.**
4. **No Evidently/Alibi** — MAE ratio + volume, simple and transparent.
5. **No Kafka/streaming** — batch = scheduled, not real-time.
6. **Champion/challenger gate before any auto-promotion.**
7. **No Feast (feature store).**
8. **Pipeline runs locally, APIs run in Docker.**
9. **Retrain is Module 6, not Module 5.**

---

## File Structure

```
mlops-zoomcamp/
├── 1-intro_and_setup/              DONE, UNTOUCHED
├── 2-Exp_tracking/                 DONE, UNTOUCHED
├── 3-Pipeline_and_Orchestrations/  DONE, UNTOUCHED
├── 4-Deploy-Online/                DONE
│   ├── shared/
│   ├── pipeline/
│   ├── api/
│   └── docker-compose.yml
├── 5-Deploy-Offline/               DONE
│   ├── batch/
│   ├── monitoring/
│   ├── dashboard/
│   └── docker-compose.yml
├── 6-Full-System/                  NEXT
└── experiments/
    └── olist_delivery/             rejected
```

---

## Teaching Philosophy

**One concept per module. Extend, never rewrite.**

```
Module 1   model exists
Module 2   model exists + tracked
Module 3a  model exists + tracked + structured
Module 3b  model exists + tracked + structured + orchestrated
Module 4   model exists + ... + served online
Module 5   model exists + ... + served offline + monitored
Module 6   model exists + ... + served online + offline + self-healing
```

**Show the pain before the solution.**
**Online before offline.**
**Use real data to tell real stories.**
The COVID shock (2020-04) proves the need for monitoring better than any manufactured example.
