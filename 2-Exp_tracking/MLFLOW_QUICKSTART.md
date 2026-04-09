# MLflow Quick Start — Mental Model, Concepts & Reference

---

## Part 1 — What Is Experiment Tracking? (The Mental Model)

### Start with the real problem

You train a Random Forest. R² = 0.76. You adjust `max_depth`, retrain. R² = 0.81.
You try a different feature set. R² = 0.79. You tune hyperparameters. R² = 0.83.

Two weeks later: **which model is in production? What hyperparameters? Which data?**

You don't know. You have a `.pkl` file with no memory attached to it.

This is the experiment tracking problem. Without a tracking system:
- You can't reproduce a result from last week
- You can't compare two runs systematically
- You can't explain to a colleague (or your future self) why you chose this model
- You can't roll back to a previous version if the new model breaks in production

**MLflow is the system that gives every model run a permanent, queryable record.**

---

### The lab notebook analogy

A scientist running chemistry experiments keeps a lab notebook. Every experiment gets:
- Date and time
- What was tried (reagents, quantities, conditions)
- What was measured (temperature, yield, purity)
- What was concluded

You never overwrite a notebook entry. If an experiment fails, that's still recorded.
If something worked three weeks ago, you can flip back and reproduce it exactly.

**MLflow is your lab notebook for ML experiments.**

Every time you run `with mlflow.start_run()`, you create one notebook entry (a **run**).
The run records:
- **Parameters** — what you set (`max_depth=10`, `learning_rate=0.1`)
- **Metrics** — what you measured (`val_r2=0.83`, `test_mae=2.27`)
- **Artifacts** — what you produced (the trained model, plots, feature importance)
- **Tags** — labels you attach (`model_family=gradient_boosting`, `data_leakage=none`)

---

### The three stages of ML development

**Stage 1 — No tracking**
```python
model.fit(X_train, y_train)
score = model.score(X_val, y_val)
print(f"Score: {score}")
# Gone. If you close the terminal, this run never existed.
```

**Stage 2 — Manual tracking (spreadsheets, notes)**
```
model        | max_depth | n_estimators | val_r2
Random Forest|     10    |     100      |  0.76
Random Forest|     20    |     100      |  0.81
Random Forest|     20    |     200      |  0.83   ← winner?
```
Better than nothing. But manual, error-prone, doesn't store the actual model,
doesn't store the training data version, and doesn't scale beyond 10 experiments.

**Stage 3 — MLflow**
```python
with mlflow.start_run():
    mlflow.log_param("max_depth", 20)
    mlflow.log_param("n_estimators", 200)
    model.fit(X_train, y_train)
    mlflow.log_metric("val_r2", val_score)
    mlflow.sklearn.log_model(model, "model")
# Every run is permanent, queryable, reproducible.
# Compare 100 runs in the UI. Load any model by run ID.
```

This is what `nyc_mlflow.ipynb` and `nyc_prod.ipynb` do in this folder.

---

### What "reproducibility" actually means

Reproducibility means: given a run from three months ago, you can:
1. Know exactly what data was used
2. Know exactly what hyperparameters were set
3. Reload the exact trained model
4. Re-run the training and get the same result

MLflow handles points 2, 3, and 4. Point 1 (data versioning) requires additional
tools (DVC, Delta Lake) — that's the next layer up from MLflow.

---

## Part 2 — MLflow Architecture

### The four components

MLflow has four components. You use them in order as your needs grow.

```
1. Tracking       Log params, metrics, tags, artifacts per run
2. Projects       Package code for reproducible runs (rarely used now)
3. Models         Standard format for saving and loading models
4. Registry       Version control + lifecycle management for models
```

In this project you use **Tracking** and **Registry**. Projects is mostly replaced
by Docker and Prefect in modern MLOps.

---

### The storage model — where MLflow saves data

MLflow stores two things separately:

```
Backend Store          Run metadata: params, metrics, tags, run IDs
                       Default: local filesystem (mlruns/)
                       Production: SQLite, PostgreSQL, MySQL

Artifact Store         Large files: trained models, plots, CSVs
                       Default: local filesystem (mlruns/)
                       Production: S3, GCS, Azure Blob
```

This folder has many `.db` files — each one is a SQLite backend store for a
different experiment:

```
mlflow_crash_course.db     scratch experiments
mlflow.db                  basic experiments
mlflow_nyc_taxi.db         NYC taxi project
mlflow_registry.db         registry experiments
mlflow_advanced.db         advanced patterns
```

**Why separate files?** Each notebook used a different database to keep experiments
isolated while learning. In production, one database holds all experiments.

---

### The three deployment scenarios (from `mlflow_Scenarios/`)

Your `mlflow_Scenarios/` folder covers the three real-world MLflow setups:

**Scenario 1 — Solo data scientist (local, no server)**
```python
import mlflow
# Tracking URI defaults to ./mlruns — no server needed
mlflow.set_experiment("my-experiment")
with mlflow.start_run():
    mlflow.log_param("C", 0.1)
    mlflow.log_metric("accuracy", 0.96)
```
```
mlruns/
└── experiment_id/
    └── run_id/
        ├── params/
        ├── metrics/
        └── artifacts/
```
Works immediately. No infrastructure. Data stored as flat files.
Model registry **not available** — it requires a database backend.

**Scenario 2 — Small team (local SQLite server)**
```bash
mlflow server --backend-store-uri sqlite:///backend.db
```
```python
mlflow.set_tracking_uri("http://127.0.0.1:5000")
# Now the registry is available — you can register and stage models
```
One server, one database. Team members point at the same URI.
Model registry works. This is what `pipeline_with_prefect/` uses.

**Scenario 3 — Multi-team production (remote server)**
```python
mlflow.set_tracking_uri("http://ec2-instance:5000")
# Backend: PostgreSQL  Artifacts: S3 bucket
```
Shared server. Concurrent writes. Artifacts in cloud storage.
This is the production pattern — used when multiple teams share one MLflow instance.

**You are at Scenario 2.** That's the right level for an MLOps course.

---

## Part 3 — Core Concepts

### Experiments and Runs

**Experiment** = a named group of runs. Think of it as a project or a model type.
```python
mlflow.set_experiment("nyc_taxi_prefect_pipeline")
# All runs go into this experiment
# If it doesn't exist, MLflow creates it
```

**Run** = one execution of your training code. One notebook cell block.
```python
with mlflow.start_run(run_name="gradient_boosting_v2"):
    # everything logged here belongs to this run
    mlflow.log_param(...)
    mlflow.log_metric(...)
    mlflow.sklearn.log_model(...)
# run automatically closed when the with block exits
```

A run has:
- A unique `run_id` (UUID, auto-generated)
- A human-readable `run_name` (auto-generated like "calm-duck" or set by you)
- Start time, end time, duration
- Status: RUNNING / FINISHED / FAILED / KILLED

---

### Parameters vs Metrics vs Tags vs Artifacts

These four concepts cover everything you log to a run:

**Parameters** — inputs you control. Logged once per run.
```python
mlflow.log_param("max_depth", 20)
mlflow.log_param("n_estimators", 200)
mlflow.log_params({"learning_rate": 0.1, "subsample": 0.8})  # batch version
```
Parameters are immutable after logging. They describe what you set going in.

**Metrics** — outputs you measure. Can be logged multiple times (per epoch/step).
```python
mlflow.log_metric("val_r2", 0.8327)
mlflow.log_metric("val_mae", 2.48)
mlflow.log_metric("train_loss", 0.42, step=10)  # with step for time-series metrics
mlflow.log_metrics({"test_r2": 0.8382, "test_mae": 2.27})  # batch version
```
Metrics are what you're optimizing. MLflow stores the full history when step is used.

**Tags** — free-form labels for filtering and categorization.
```python
mlflow.set_tag("model_family", "gradient_boosting")
mlflow.set_tag("data_leakage", "none")
mlflow.set_tag("orchestrator", "prefect")
```
Tags don't have types — everything is a string. Use them to filter runs in the UI.

**Artifacts** — files produced by the run.
```python
mlflow.sklearn.log_model(model, artifact_path="model")   # trained model
mlflow.log_artifact("feature_importance.png")            # any file
mlflow.log_dict({"features": feature_list}, "metadata.json")  # dict as JSON
```
Artifacts are stored in the artifact store (filesystem or S3).
Models logged as artifacts can be loaded later by run ID or registered in the Registry.

---

### The Model Registry

The Registry is version control for models. It separates "a trained model in a run"
from "a model version we're considering for production."

```
Training Run          →    Model Artifact    →    Registry Version
(run_id: abc123)           (runs:/abc123/model)   (name: nyc_taxi_predictor, v5)
```

**Stages** — a version moves through stages as it's validated:

```
None → Staging → Production → Archived
```

```
None        Just registered. Not validated yet.
Staging     Under evaluation. Not serving traffic.
Production  Live. Serving predictions.
Archived    Replaced. Kept for audit trail.
```

```python
from mlflow import MlflowClient

client = MlflowClient()

# Register a model from a run
mlflow.register_model(
    model_uri=f"runs:/{run_id}/model",
    name="nyc_taxi_predictor"
)

# Transition to staging
client.transition_model_version_stage(
    name="nyc_taxi_predictor",
    version=5,
    stage="Staging"
)

# Promote to production
client.transition_model_version_stage(
    name="nyc_taxi_predictor",
    version=5,
    stage="Production"
)
```

**Loading a model from the registry:**
```python
# By stage (always gets the current production model)
model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/Production")

# By version (pinned — always the same model regardless of stage changes)
model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/5")

# By run ID (direct artifact reference)
model = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
```

Loading by stage is what serving infrastructure uses — it always gets the
current production model without code changes when you promote a new version.

---

### Nested Runs

Runs can be nested. A parent run represents the whole training job.
Child runs represent individual models or folds.

```python
with mlflow.start_run(run_name="full_training_job") as parent_run:
    mlflow.log_param("sample_size", 200000)

    for model_name, model in models.items():
        with mlflow.start_run(run_name=model_name, nested=True):
            model.fit(X_train, y_train)
            mlflow.log_metric("val_r2", score)
            mlflow.sklearn.log_model(model, "model")
```

In the UI, the parent run collapses to show all child runs beneath it.
Useful when you want to group a hyperparameter search or a cross-validation sweep.

This project uses **flat runs** (no nesting) — each model training call creates
its own top-level run. Simpler, and easier to compare models directly.

---

### MlflowClient — the programmatic API

`mlflow.log_*` functions work on the **currently active run** (inside a `with` block).
`MlflowClient` lets you query and manipulate runs **programmatically** from outside a run.

```python
from mlflow import MlflowClient

client = MlflowClient()

# Search runs in an experiment
runs = client.search_runs(
    experiment_ids=["1"],
    filter_string="metrics.val_r2 > 0.80",
    order_by=["metrics.val_r2 DESC"]
)

# Get the best run
best_run = runs[0]
print(best_run.info.run_id)
print(best_run.data.metrics)

# Register a model
client.create_registered_model("nyc_taxi_predictor")

# Add a version description
client.update_model_version(
    name="nyc_taxi_predictor",
    version=5,
    description="Gradient Boosting, test R²=0.8382, MAE=2.27min"
)
```

The `MlflowClient` is what `pipeline_with_prefect/src/models/model_registry.py` uses
to query the registry and transition stages after training.

---

## Part 4 — What This Project Does With MLflow

### Every training run logs the same structure

From `src/models/model_training.py` in `pipeline_with_prefect/`:

```python
with mlflow.start_run(run_name=model_name) as run:

    # 1. Train
    model.fit(X_train, y_train)

    # 2. Log params (what you set)
    mlflow.log_params(model.get_params())
    mlflow.log_param("train_samples", X_train.shape[0])
    mlflow.log_param("features", X_train.shape[1])

    # 3. Log metrics (what you measured)
    mlflow.log_metrics({
        "train_r2": ..., "val_r2": ...,
        "train_rmse": ..., "val_rmse": ...,
        "train_mae": ..., "val_mae": ...,
        "training_time": ...,
        "overfitting_gap": train_r2 - val_r2
    })

    # 4. Log tags (labels for filtering)
    mlflow.set_tag("model_family", model_name)
    mlflow.set_tag("data_leakage", "none")
    mlflow.set_tag("orchestrator", "prefect")

    # 5. Log model artifact with signature
    signature = infer_signature(X_train, y_train_pred)
    mlflow.sklearn.log_model(
        sk_model=model,
        artifact_path="model",
        signature=signature,
        registered_model_name="nyc_taxi_predictor"
    )
```

`infer_signature` captures the input/output schema of the model. When you load
the model later, MLflow can validate that new data has the right shape and types.

---

### The overfitting gap metric

```python
"overfitting_gap": r2_score(y_train, y_train_pred) - r2_score(y_val, y_val_pred)
```

This is a custom metric — not from sklearn. It's the difference between train R²
and val R². A large gap means the model is overfitting.

In the MLflow UI you can sort by `overfitting_gap` to find models that generalize
well, not just models that score high on training data.
This is the kind of insight that only exists because you explicitly logged it.

---

### After training — the selection and registration flow

```python
# 1. Select best model by val_r2
best_name = max(training_results, key=lambda n: training_results[n]["val_r2"])

# 2. Evaluate on test set (done ONCE, after model selection)
test_metrics = trainer.evaluate_on_test(best_model, X_test, y_test, best_run_id)

# 3. Register and transition to Staging
registry.transition_to_staging(best_run_id, model_name="nyc_taxi_predictor")

# 4. Optionally promote to Production
if promote_to_prod:
    registry.transition_to_production(version, model_name="nyc_taxi_predictor")
```

The test set evaluation happens exactly once — on the final chosen model.
Evaluating on the test set during model selection would be data leakage.
MLflow makes it easy to log test metrics back to an existing run by run ID:

```python
with mlflow.start_run(run_id=existing_run_id):  # reopen the run
    mlflow.log_metrics({"test_r2": 0.8382, "test_mae": 2.27})
    mlflow.set_tag("final_model", "true")
```

---

## Part 5 — The Bigger Picture

### Where MLflow sits in the MLOps stack

```
Data Sources          Kaggle, databases, APIs
      ↓
Feature Engineering   sklearn Pipeline, custom transformers
      ↓
Experiment Tracking   MLflow Tracking ← logs params, metrics, artifacts
      ↓
Model Registry        MLflow Registry ← versions, stages, lineage
      ↓
Orchestration         Prefect ← runs the whole pipeline reliably
      ↓
Serving               FastAPI + mlflow.pyfunc.load_model()
      ↓
Monitoring            Compare new predictions to registry baseline
```

MLflow sits at the center — everything upstream feeds into it,
everything downstream reads from it. The Registry is the handoff point
between training and serving.

---

### MLflow vs alternatives

| | MLflow | Weights & Biases | Neptune | Comet |
|---|---|---|---|---|
| Open source | Yes | No | No | No |
| Self-hosted | Yes | Paid | Paid | Paid |
| Setup | `pip install mlflow` | SaaS account | SaaS account | SaaS account |
| Model registry | Yes | Yes | Yes | Yes |
| Best for | MLOps courses, self-hosted | Deep learning, teams | Research tracking | Enterprise |

MLflow is the standard for MLOps courses and self-hosted setups.
W&B is more common in deep learning research. At a job you'll likely encounter both.

---

### The natural progression from MLflow

```
1. Notebook experiments         log a few runs manually
2. Script with MLflow           every training run logged automatically
3. MLflow + Model Registry      versions, stages, rollback capability    ← you are here
4. Prefect + MLflow             orchestrated, observable pipeline
5. REST API serving             load Production model, serve predictions
6. Monitoring                   detect when the model degrades over time
7. Retraining trigger           schedule or drift-triggered retraining
```

---

## Quick Reference

### Install and start

```bash
pip install mlflow

# Start the UI (with SQLite backend)
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db
# Open http://127.0.0.1:5000

# Start a server (enables Registry + multi-user)
mlflow server --backend-store-uri sqlite:///mlflow_nyc_taxi.db
# Open http://127.0.0.1:5000
```

### Tracking API

```python
import mlflow

mlflow.set_tracking_uri("sqlite:///mlflow_nyc_taxi.db")   # or http://127.0.0.1:5000
mlflow.set_experiment("nyc_taxi_prefect_pipeline")

with mlflow.start_run(run_name="gradient_boosting"):
    mlflow.log_param("max_depth", 5)
    mlflow.log_params({"lr": 0.1, "n_estimators": 200})

    mlflow.log_metric("val_r2", 0.83)
    mlflow.log_metrics({"test_r2": 0.84, "test_mae": 2.27})

    mlflow.set_tag("model_family", "gradient_boosting")

    mlflow.sklearn.log_model(model, "model")
    mlflow.log_artifact("plot.png")
```

### Registry API

```python
from mlflow import MlflowClient

client = MlflowClient()

# Register
mlflow.register_model(f"runs:/{run_id}/model", "nyc_taxi_predictor")

# Transition stage
client.transition_model_version_stage("nyc_taxi_predictor", version=5, stage="Staging")
client.transition_model_version_stage("nyc_taxi_predictor", version=5, stage="Production")

# Load
model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/Production")
model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/5")
model = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
```

### Search runs

```python
runs = client.search_runs(
    experiment_ids=["1"],
    filter_string="metrics.val_r2 > 0.80 and tags.model_family = 'gradient_boosting'",
    order_by=["metrics.val_r2 DESC"],
    max_results=10
)
best_run_id = runs[0].info.run_id
```

---

## Official Documentation

- MLflow concepts: https://mlflow.org/docs/latest/concepts.html
- Tracking: https://mlflow.org/docs/latest/tracking.html
- Model registry: https://mlflow.org/docs/latest/model-registry.html
- Models (signatures, flavors): https://mlflow.org/docs/latest/models.html
- MLflow + sklearn: https://mlflow.org/docs/latest/python_api/mlflow.sklearn.html
