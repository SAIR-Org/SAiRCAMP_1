# Module 2 — Experiment Tracking with MLflow

**Project:** NYC Yellow Taxi Trip Duration Prediction  
**New layer:** MLflow — every training run gets a permanent, queryable record.

---

## What This Module Adds

Module 1 trained models and printed scores to the terminal. Two weeks later: which model
is in production? What hyperparameters? Which data? You don't know.

This module adds MLflow so every run is logged, comparable, and reproducible.

```
Module 1   model exists
Module 2   model exists + tracked       ← this module
Module 3   model exists + tracked + structured + orchestrated
```

---

## Learning Path

Work through the files in this order:

```
Step 1   mlflow_crash_course.ipynb      Learn MLflow from scratch (2 hours)
Step 2   mlflow_Scenarios/              Understand the 3 real-world deployment setups
Step 3   nyc_mlflow.ipynb               Apply MLflow tracking to the NYC Taxi problem
Step 4   nyc_prod.ipynb                 Full registry pipeline — staging, production, rollback
Step 5   MLFLOW_QUICKSTART.md           Concepts reference (read any time)
```

---

## The Three Scenarios

The `mlflow_Scenarios/` folder covers how MLflow is deployed in practice:

| Scenario | Setup | Registry? | When |
|---|---|---|---|
| `scenario-1.ipynb` | No server — local filesystem (`mlruns/`) | No | Solo work, competitions |
| `scenario-2.ipynb` | Local SQLite server | Yes | Small team, this course |
| `scenario-3.ipynb` | Remote server (EC2 + PostgreSQL + S3) | Yes | Production, multi-team |

You are at **Scenario 2** after this module. That is the right level for an MLOps course.

---

## The NYC Taxi Notebooks

### `nyc_mlflow.ipynb` — Tracking

Takes the Module 1 pipeline and wraps every training run in `mlflow.start_run()`.
Every model gets params, metrics, and a saved artifact logged automatically.

```python
with mlflow.start_run(run_name="gradient_boosting"):
    mlflow.log_params(model.get_params())
    model.fit(X_train, y_train)
    mlflow.log_metrics({"val_r2": 0.838, "val_mae": 2.48})
    mlflow.sklearn.log_model(model, "model")
```

After running: open the MLflow UI and compare all runs in a table. Sort by `val_r2`.
Pick the winner without touching a spreadsheet.

### `nyc_prod.ipynb` — Registry

Extends `nyc_mlflow.ipynb` with the **Model Registry** — version control for trained models.

```
Training run  →  register as version N  →  Staging  →  Production
                                                          ↓
                                               load by stage (always current)
                                               model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/Production")
```

The registry separates "a model artifact in a run" from "the model we're currently serving."
Rolling back is re-assigning the Production stage to a previous version.

---

## Setup

```bash
# From repo root (one-time):
uv sync
source .venv/bin/activate
```

## How to Start the MLflow UI

```bash
cd 2-Exp_tracking
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db
# Open http://127.0.0.1:5000
```

Each `.db` file in this folder is an isolated SQLite backend from a different notebook:

| Database | What's in it |
|---|---|
| `mlflow_crash_course.db` | Crash course experiments |
| `mlflow_nyc_taxi.db` | NYC Taxi tracking runs |
| `mlflow_registry.db` | Registry experiments |
| `mlflow_advanced.db` | Advanced patterns (nested runs, etc.) |

---

## What You Can Do After This Module

- Compare 50 training runs in a table — sorted by any metric, filtered by any tag
- Reproduce any run from 3 months ago — load the exact model by `run_id`
- Load the current Production model by name without knowing the version:
  ```python
  model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/Production")
  ```
- Roll back to a previous version if the new model degrades:
  ```python
  client.transition_model_version_stage("nyc_taxi_predictor", version=4, stage="Production")
  ```

---

## Reference

**`MLFLOW_QUICKSTART.md`** — full concepts reference: tracking API, registry API,
MLflow architecture, storage model, nested runs, MlflowClient, and how the NYC Taxi
project uses each concept.
