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
Module 1 — intro_and_setup         (DONE, UNTOUCHED)
  Teaches: EDA, data leakage, feature engineering, basic sklearn
  Notebooks: nyc_1 (explore) → nyc_2 (deliberate mistakes) → nyc_3 (fix properly)
  Data: 2016 Kaggle CSV, lat/lon format
  Tool: Jupyter

Module 2 — Exp_tracking            (DONE, UNTOUCHED)
  Teaches: MLflow tracking, experiment comparison, model registry, staging→production
  Data: 2016 Kaggle CSV
  Tool: MLflow

Module 3a — pipline_no_perfect     (DONE, UNTOUCHED)
  Teaches: pipeline class, clean code structure, retry logic, 10 explicit steps
  Data: 2016 Kaggle CSV
  Tool: plain Python

Module 3b — pipeline_with_prefect  (DONE, UNTOUCHED)
  Teaches: Prefect @task/@flow, UI visibility, task-level retries, orchestration boundary
  Data: 2016 Kaggle CSV
  Tool: Prefect

Module 4 — Deployment              (IN PROGRESS — built in 4-Deployment/)
  Teaches: schema migration, online serving, batch deployment,
           drift monitoring, auto-retraining, full production system
  Data: TLC 2019 parquet (direct download, zone IDs)
  Tools: FastAPI + Prefect + MLflow + Streamlit
```

---

## The Grand Plan for Module 4

Module 4 lives entirely in `4-Deployment/`. It is built from scratch — modules 1–3 are never modified.

```
4-Deployment/
├── pipeline/     Step 1 — train on 2019 TLC data, register model in MLflow
├── api/          Step 2 — FastAPI online serving, load Production model from registry
├── batch/        Step 3 — Prefect scheduled flow, score 2020→2022→2024 monthly data
├── monitoring/   Step 4 — drift detection, MAE chart over time, alerts
├── retrain/      Step 5 — champion/challenger, auto-promote if challenger wins
└── dashboard/    Step 6 — Streamlit: Tab1 predict, Tab2 batch, Tab3 drift, Tab4 health
```

### The Drift Story (the crown jewel of Module 4)

```
Train on 2019 → Deploy → Batch score by year → Watch degradation

2019:  7.7M trips/month  avg_dist=2.83mi  avg_fare=$12.53  ← train here
2020:  238k  trips/month  avg_dist=4.04mi  avg_fare=$11.67  ← COVID collapse
2022:  2.5M  trips/month  avg_dist=5.37mi  avg_fare=$12.95  ← new normal
2024:  3.0M  trips/month  avg_dist=3.65mi  avg_fare=$18.18  ← +45% fares

Three drift types in one dataset:
  Volume drift     (2020): 97% fewer trips — model never saw this
  Feature drift    (2022): Uber took short trips, only long taxi trips remain
  Label drift      (2024): fares 45% higher due to inflation + fare hikes
```

---

## Key Decisions Already Made

**1. Modules 1–3 are untouched forever.**
They are teaching artifacts showing the progression. Students reference them.
Never modify them. The schema inconsistency (2016 vs 2019) is intentional —
schema migration is explicitly taught as a lesson in Module 4.

**2. Module 4 uses TLC direct download, not Kaggle.**
```python
url = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month:02d}.parquet"
```
No Kaggle credentials needed. Any year from 2017+ works. Parquet format.

**3. Feature format changed: lat/lon → zone IDs.**
```
OUT: pickup_longitude, pickup_latitude, dropoff_longitude, dropoff_latitude
IN:  PULocationID, DOLocationID  (1–265 zone IDs)
```
Zone IDs are better features for tree models — they encode neighborhood semantics.
No geographic filter needed (zone IDs are already within NYC).

**4. Batch method: Prefect scheduled flow + MLflow registry + SQLite output.**
- Load model from `mlflow.sklearn.load_model("models:/nyc_taxi_v2/Production")`
- Score monthly TLC data
- Log MAE + drift score to MLflow per run
- Write results to SQLite `batch_results.db`

**5. Drift detection: simple statistical comparison, no external libraries.**
```python
drift_score = abs(batch_mean - train_mean) / train_std
if drift_score > 2.0: alert
```
No Evidently, no Alibi. 10 lines. Students understand it immediately.

**6. Retraining: champion/challenger gate before auto-promotion.**
New model must beat champion on holdout before auto-promoting to Production.
Without this gate, auto-retraining can silently make things worse.

**7. Dashboard: Streamlit with 4 tabs.**
Tab 1: Try the model (online)
Tab 2: Batch results (offline)
Tab 3: MAE over time (drift)
Tab 4: System health + Retrain button (triggers Prefect flow)

---

## Datasets Investigated and Rejected

**Olist Brazilian E-commerce delivery time:**
- R² ceiling ~0.46 — cannot exceed 0.5 regardless of features
- Community pivots to classification (late/on-time), not regression
- Decision: rejected as taxi replacement

**Airbnb price prediction:**
- R² varies wildly (0.08–0.57) depending on city/features — unreliable
- Decision: rejected

**Used Car Price Prediction:**
- R² 0.81–0.87 consistently — strong signal
- Considered as taxi replacement, but taxi + COVID drift story is stronger
- Decision: not needed — taxi with 2019/2020/2024 data is the right choice

---

## What NOT to Do

- Never modify `1-intro_and_setup/`, `2-Exp_tracking/`, `3-Pipeline_and_Orchestrations/`
- Never use Kaggle data in Module 4 — always TLC direct download
- Never add Feast (feature store) — not needed for this problem
- Never add Evidently/Alibi for drift detection — keep it simple (10-line statistical check)
- Never use Kafka/streaming — batch means scheduled, not real-time
- Never auto-promote a retrained model without the champion/challenger comparison gate

---

## File Structure Reference

```
mlops-zoomcamp/
├── 1-intro_and_setup/              UNTOUCHED
├── 2-Exp_tracking/                 UNTOUCHED
├── 3-Pipeline_and_Orchestrations/  UNTOUCHED
│   ├── pipline_no_perfect/         base pipeline (plain Python)
│   └── pipeline_with_prefect/      orchestrated pipeline (Prefect)
├── 4-Deployment/                   ACTIVE WORK
│   ├── pipeline/                   training pipeline (2019 TLC data)
│   ├── api/                        FastAPI serving
│   ├── batch/                      Prefect batch scoring
│   ├── monitoring/                 drift detection
│   ├── retrain/                    champion/challenger
│   └── dashboard/                  Streamlit
└── experiments/
    └── olist_delivery/             feasibility checks (completed, rejected)
```

---

## Teaching Philosophy

**One concept per module. Extend, never rewrite.**

Each module adds exactly one layer:
```
Module 1  model exists
Module 2  model exists + tracked
Module 3a model exists + tracked + structured
Module 3b model exists + tracked + structured + orchestrated
Module 4  model exists + tracked + structured + orchestrated + deployed + monitored + self-healing
```

The schema migration (2016 Kaggle → 2019 TLC) in Module 4 is a deliberate teaching moment,
not a flaw. It shows students that data sources change and systems must adapt.

**Show the pain before the solution.**
Every tool is introduced by first showing what breaks without it.
Students feel the need before they learn the fix.
