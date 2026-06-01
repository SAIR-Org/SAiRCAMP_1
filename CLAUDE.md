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
  Notebooks: nyc_1 (explore) → nyc_2 (deliberate mistakes) → nyc_3 (fix properly)
  Data: 2016 Kaggle CSV, lat/lon format
  Tool: Jupyter

Module 2 — 2-Exp_tracking                 (DONE, UNTOUCHED)
  Teaches: MLflow tracking, experiment comparison, model registry, staging→production
  Data: 2016 Kaggle CSV
  Tool: MLflow

Module 3a — 3-Pipeline_and_Orchestrations/pipline_no_perfect     (DONE, UNTOUCHED)
  Teaches: pipeline class, clean code structure, retry logic, explicit steps
  Data: 2016 Kaggle CSV
  Tool: plain Python

Module 3b — 3-Pipeline_and_Orchestrations/pipeline_with_prefect  (DONE, UNTOUCHED)
  Teaches: Prefect @task/@flow, UI visibility, task-level retries, orchestration boundary
  Data: 2016 Kaggle CSV
  Tool: Prefect

Module 4 — 4-Deploy-Online                (DONE)
  Teaches: schema migration, MLflow registry + aliases, online serving, Docker for ML
  Data: TLC 2019 parquet (direct download, zone IDs)
  Tools: FastAPI + Prefect + MLflow + Docker

Module 5 — 5-Deploy-Offline               (NEXT — not started)
  Teaches: batch scoring, drift detection, champion/challenger retraining, Streamlit dashboard
  Data: TLC 2020, 2022, 2024 parquet (the drift story)
  Tools: Prefect + MLflow + Streamlit
```

---

## Module 4 — What Was Built (DONE)

Lives in `4-Deploy-Online/`. Complete and ready to teach.

```
4-Deploy-Online/
├── shared/      feature_engineering.py — single source of truth for pipeline + api
├── pipeline/    Prefect flow, 9 steps, 6 models, MLflow tracking, @champion registration
├── api/         FastAPI /predict endpoint, loads @champion + preprocessor from MLflow
├── docs/        Cross-component implementation docs (populated as module grows)
├── docker-compose.yml
├── MLFLOW_REGISTRY.md    concept guide
├── DOCKER_FOR_ML.md      concept guide
└── FASTAPI.md            concept guide
```

**Key decisions made in Module 4:**
- TLC 2019 data, direct parquet download (no Kaggle)
- Zone IDs replace lat/lon — 23 features (was 19)
- MLflow 3.x aliases: `@champion` / `@challenger` (not deprecated stages)
- Preprocessor saved as MLflow artifact alongside model (prevents training-serving skew)
- `shared/feature_engineering.py` — both pipeline and api import from here
- Docker: named volume `mlflow_store` shared between pipeline and api containers
- Best model: XGBoost, Test R² 0.817, MAE 3.07 min

**Model registry:**
```python
mlflow.set_tracking_uri("sqlite:///4-Deploy-Online/pipeline/mlflow_trip_duration.db")
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")
```

---

## Module 5 — The Plan (NEXT)

Lives in `5-Deploy-Offline/`. Not started.

```
5-Deploy-Offline/
├── batch/       Prefect scheduled flow — score 2020/2022/2024 monthly data
├── monitoring/  Drift detection, MAE over time, alerts
├── retrain/     Champion/challenger comparison, auto-promotion gate
└── dashboard/   Streamlit: Tab1 predict, Tab2 batch, Tab3 drift, Tab4 health
```

### The Drift Story (the crown jewel of Module 5)

```
Train on 2019 → Deploy → Batch score by year → Watch degradation

2019:  7.7M trips/month  avg_dist=2.83mi  avg_fare=$12.53  ← train here
2020:  238k trips/month  avg_dist=4.04mi  avg_fare=$11.67  ← COVID collapse   (volume drift)
2022:  2.5M trips/month  avg_dist=5.37mi  avg_fare=$12.95  ← new normal       (feature drift)
2024:  3.0M trips/month  avg_dist=3.65mi  avg_fare=$18.18  ← +45% fares       (label drift)
```

**Batch method:** Prefect scheduled flow + MLflow registry + SQLite output
- Load `@champion` from `models:/trip_duration_model@champion`
- Score monthly TLC data
- Log MAE + drift score to MLflow per run
- Write results to SQLite `batch_results.db`

**Drift detection:** simple statistical comparison, no external libraries
```python
drift_score = abs(batch_mean - train_mean) / train_std
if drift_score > 2.0: alert
```
No Evidently, no Alibi. 10 lines. Students understand it immediately.

**Retraining:** champion/challenger gate before auto-promotion.
New model must beat champion on holdout before auto-promoting.
Without this gate, auto-retraining can silently make things worse.

**Dashboard:** Streamlit with 4 tabs
- Tab 1: Try the model (online predict)
- Tab 2: Batch results (offline scores)
- Tab 3: MAE over time (drift chart)
- Tab 4: System health + Retrain button

---

## Key Decisions — Permanent

**1. Modules 1–3 are untouched forever.**
Teaching artifacts. Never modify them.

**2. Module 4 uses TLC direct download, not Kaggle.**
```python
url = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month:02d}.parquet"
```

**3. Feature format: lat/lon → zone IDs (Module 4 onwards)**
Zone IDs are better features for tree models.

**4. No Evidently/Alibi for drift** — keep it simple (10-line statistical check).

**5. No Kafka/streaming** — batch means scheduled, not real-time.

**6. No auto-promotion without champion/challenger gate.**

**7. No Feast (feature store)** — not needed for this problem.

---

## File Structure

```
mlops-zoomcamp/
├── 1-intro_and_setup/                    DONE, UNTOUCHED
├── 2-Exp_tracking/                       DONE, UNTOUCHED
├── 3-Pipeline_and_Orchestrations/        DONE, UNTOUCHED
│   ├── pipline_no_perfect/
│   └── pipeline_with_prefect/
├── 4-Deploy-Online/                      DONE
│   ├── shared/
│   ├── pipeline/
│   ├── api/
│   ├── docs/
│   └── docker-compose.yml
├── 5-Deploy-Offline/                     NEXT — not started
│   ├── batch/
│   ├── monitoring/
│   ├── retrain/
│   └── dashboard/
└── experiments/
    └── olist_delivery/                   rejected dataset feasibility checks
```

---

## Teaching Philosophy

**One concept per module. Extend, never rewrite.**

```
Module 1   model exists
Module 2   model exists + tracked
Module 3a  model exists + tracked + structured
Module 3b  model exists + tracked + structured + orchestrated
Module 4   model exists + tracked + structured + orchestrated + served online
Module 5   model exists + tracked + structured + orchestrated + served online + monitored + self-healing
```

**Show the pain before the solution.**
Every tool is introduced by first showing what breaks without it.
Students feel the need before they learn the fix.

**Online before offline.**
Module 4 teaches real-time serving. Module 5 teaches batch and monitoring.
The split follows the natural question progression:
- "How do I serve my model?" → Module 4
- "How do I know if my model is still good?" → Module 5
