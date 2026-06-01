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
  Teaches: schema migration, MLflow registry + aliases, online serving, Docker for API
  Data: TLC 2019 parquet (direct download, zone IDs)
  Tools: FastAPI + Prefect (local) + MLflow + Docker (API only)

Module 5 — 5-Deploy-Offline               (IN PROGRESS)
  Teaches: batch scoring, drift detection, champion/challenger retraining, Streamlit dashboard
  Data: TLC 2020/2022/2024 parquet (the shock-and-recovery story)
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
├── docs/        Cross-component implementation docs
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
- **Pipeline runs locally only** — Prefect's ephemeral server doesn't work in Docker
  without a dedicated Prefect server service. Training is a local/development activity.
- **API runs in Docker** — bind-mounts `./pipeline` so it reads the local MLflow registry
- Best model: XGBoost, Test R² 0.817, MAE 3.07 min
- Training stats saved to MLflow: `train_duration_mean=13.01`, `train_duration_std=10.03`, `test_mae=3.07`

**Model registry:**
```python
mlflow.set_tracking_uri("sqlite:///4-Deploy-Online/pipeline/mlflow_trip_duration.db")
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")
```

---

## Module 5 — What Is Being Built (IN PROGRESS)

Lives in `5-Deploy-Offline/`. Batch exploration notebook complete.

```
5-Deploy-Offline/
├── batch/            Prefect scheduled flow — score 2020/2022/2024 monthly data  ⬜
│   └── batch_exploration.ipynb   ✅ complete — validated approach
├── monitoring/       Drift detection, MAE over time, alerts                       ⬜
├── retrain/          Champion/challenger comparison, auto-promotion gate           ⬜
└── dashboard/        Streamlit: predict / batch / drift / health tabs             ⬜
```

### The Drift Story (validated from data)

The story is a **real-world shock-and-recovery** — not three abstract drift types:

```
Train on 2019 → Deploy → Batch score monthly → Watch what actually happened

2019:  ~7.7M trips/month   MAE 3.07 min  ← train and deploy here
2020-04: 204k trips/month  MAE 5.55 min  ← COVID hits — 97% volume collapse, 80% MAE degradation
2022-01: 2.3M trips/month  MAE 2.99 min  ← world recovers, model recovers too
2024-01: 2.7M trips/month  MAE 3.15 min  ← stable new normal
```

**What this teaches:** drift doesn't always happen gradually. Sometimes the world breaks
overnight and your model breaks with it. If you're not monitoring, you don't know.
The 2020 event proves the need for monitoring more powerfully than any manufactured example.

**Alert conditions (validated in notebook):**
```python
mae_alert    = (batch_mae / train_mae) > 1.5   # MAE degraded 50%+ → alert
volume_alert = total_rows < 500_000             # volume collapsed → alert
```

The σ formula (`abs(batch_mean - train_mean) / train_std`) was tested and rejected —
`train_std = 10 min` is too large, absorbs any mean shift. MAE ratio is the right metric.

**Batch scorer SQLite schema:**
```sql
CREATE TABLE batch_results (
    year INTEGER, month INTEGER, scored_at TEXT,
    total_rows INTEGER, n_scored INTEGER,
    mae REAL, mae_ratio REAL,
    target_mean REAL, dist_mean REAL,
    alert INTEGER,
    PRIMARY KEY (year, month)
);
```

---

## Key Decisions — Permanent

**1. Modules 1–3 are untouched forever.**

**2. Module 4+ uses TLC direct download, not Kaggle.**
```python
url = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month:02d}.parquet"
```

**3. Feature format: lat/lon → zone IDs (Module 4 onwards)**

**4. No Evidently/Alibi for drift** — MAE ratio + volume, ~10 lines, students understand immediately.

**5. No Kafka/streaming** — batch means scheduled, not real-time.

**6. No auto-promotion without champion/challenger gate.**

**7. No Feast (feature store)** — not needed for this problem.

**8. Pipeline runs locally, API runs in Docker.**
Prefect requires a dedicated server to run in Docker. Training is a local activity.
Serving is a deployment activity. This is the correct architectural separation.

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
├── 5-Deploy-Offline/                     IN PROGRESS
│   ├── batch/
│   │   └── batch_exploration.ipynb      ✅ validated
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
Module 4: "How do I serve my model?"
Module 5: "How do I know if my model is still good?"

**Use real data to tell real stories.**
The COVID shock (2020-04) is more powerful than any manufactured drift example.
The data proved this — trust what the data shows, not what was planned upfront.
