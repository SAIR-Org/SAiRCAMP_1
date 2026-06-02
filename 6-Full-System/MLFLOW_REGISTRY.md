# MLflow Model Registry — Mental Model, Concepts & Reference

---

## Part 1 — What Is a Model Registry? (The Mental Model)

### Start with a software release process

In software engineering, code doesn't go straight from a developer's laptop to production.
It goes through a pipeline:

```
Developer writes code
      ↓
Code is reviewed and merged
      ↓
CI builds and tests it
      ↓
Artifact is tagged as a release candidate
      ↓
QA approves it
      ↓
It gets promoted to production
```

At every stage, the artifact has a **status**. Stakeholders know exactly what version is
running in production and what's waiting in the queue. If production breaks, you roll back
to the previous known-good release.

**A model registry is the same thing for ML models.**

Without it:
```
Data scientist trains a model
      ↓
Saves model.pkl to /models/ folder on laptop
      ↓
Emails it to the engineer
      ↓
Engineer hardcodes the path in the serving code
      ↓
???
```

No history. No versioning. No approval process. No rollback. If the new model is worse,
you don't know which version was running last week.

With a registry:
```
Pipeline trains a model
      ↓
Registers it as version 7 of "trip_duration_model"
      ↓
Marks it as @challenger (candidate)
      ↓
Evaluation confirms it beats the current champion
      ↓
Promotes it to @champion
      ↓
API loads model by alias: models:/trip_duration_model@champion
      ↓
Next time the pipeline runs: same process, version 8
```

Versioned. Audited. Rollback is one alias reassignment.

---

### MLflow tracking vs MLflow registry — two different things

Students often confuse these. They are separate systems that work together.

**MLflow Tracking** — records what happened during training:
```
Run ID: abc123
  Parameters: n_estimators=300, learning_rate=0.05
  Metrics: val_r2=0.8156, test_mae=3.07
  Artifacts: model.pkl, feature_importance.json
```
Think of it as a lab notebook. Every experiment, every metric, every run is logged.
You use it to compare runs and find the best model.

**MLflow Model Registry** — manages what goes to production:
```
Registered Model: trip_duration_model
  Version 5: run abc789 — @champion (currently serving)
  Version 6: run abc123 — @challenger (candidate)
  Version 4: run abc456 — (no alias — retired)
```
Think of it as a deployment pipeline. Only the models you consciously promote live here.
Not every training run becomes a registered version.

**The link between them:**
When a training run produces a good model, you register it:
```python
mlflow.sklearn.log_model(
    sk_model=model,
    name='model',
    registered_model_name='trip_duration_model'   # ← this creates a registry version
)
```
The run stays in tracking forever. The registered version points back to the run.

---

### What "loading by alias" means and why it matters

There are three ways to load a model from MLflow:

```python
# 1. By run artifact path — brittle, hardcoded run ID
model = mlflow.sklearn.load_model("runs:/abc123def456/model")

# 2. By version number — better, but still hardcoded
model = mlflow.sklearn.load_model("models:/trip_duration_model/6")

# 3. By alias — production-safe
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")
```

Method 3 is the only one that survives a model update without changing code.

When you promote version 7 to `@champion`, every system loading by alias
immediately serves the new model — with zero code changes. The API, the batch scorer,
the monitoring service — they all load `@champion` and they all get version 7 automatically.

This is not an academic distinction. In a real deployment:
- The API is running in production, serving thousands of requests
- You train a better model
- You promote it to `@champion`
- The API serves the new model on the next startup (or reload)
- No deployment required. No code change. No downtime.

---

## Part 2 — MLflow Registry Concepts

### Registered models, versions, and aliases

```
Registered Model
└── trip_duration_model               ← the model "product"
    ├── Version 1                     ← Linear Regression run
    ├── Version 2                     ← Ridge run
    ├── Version 3                     ← Lasso run
    ├── Version 4                     ← Random Forest run
    ├── Version 5                     ← Gradient Boosting run
    └── Version 6  @champion          ← XGBoost tuned — currently serving
```

**Registered Model:** A named entity in the registry. In this project: `trip_duration_model`.
One registered model can have many versions. Each version is linked to exactly one training run.

**Version:** An immutable snapshot of a model artifact. Once created, the artifact never
changes. You can add tags and aliases to a version, but not change the model weights.

**Alias:** A mutable pointer to a version. `@champion` today points to v6.
Tomorrow it may point to v7. The alias moves. The versions stay.

---

### MLflow 3.x: aliases replace stages

In MLflow 2.x, models had stages: `None → Staging → Production → Archived`.
These were deprecated because they were inflexible — you could only have one model
in Production at a time, and the stage names were fixed.

MLflow 3.x replaced stages with **aliases** — free-form named pointers.

```python
# MLflow 2.x — deprecated, removed in 3.x
client.transition_model_version_stage(
    name="trip_duration_model",
    version="6",
    stage="Production"
)
# Load:
model = mlflow.pyfunc.load_model("models:/trip_duration_model/Production")

# MLflow 3.x — aliases
client.set_registered_model_alias(
    name="trip_duration_model",
    alias="champion",
    version="6"
)
# Load:
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")
```

This project uses `@champion` and `@challenger` by convention, matching the
champion/challenger evaluation pattern used in `retrain/`. But you can use any names:
`@prod`, `@staging`, `@v2-experiment` — whatever makes sense for your workflow.

---

### The preprocessor artifact — why it matters

A common mistake: registering only the model weights, not the preprocessing pipeline.

```python
# Wrong — registers only the sklearn estimator
mlflow.sklearn.log_model(sk_model=xgboost_model, ...)

# At serving time:
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")
model.predict(raw_features)   # WRONG — raw features ≠ what the model was trained on
```

The model was trained on preprocessed features:
```
raw DataFrame → TripFeatureEngineer → OutlierHandler → RobustScaler → XGBoost
```

If you only save the XGBoost model, you've lost the first three steps. At serving time,
you're passing raw features to a model that expects scaled, engineered features.
The model will predict garbage — and not error. It will silently predict wrong values.

**This project solves it by saving the preprocessor as a separate artifact:**

```python
# In flow.py register_model task:
with open("preprocessor.pkl", "wb") as f:
    pickle.dump(fitted_preprocessor, f)

with mlflow.start_run(run_id=model_run_id):
    mlflow.log_artifact("preprocessor.pkl", artifact_path="preprocessor")
```

**At serving time (api/model_loader.py):**
```python
# Load model
model = mlflow.sklearn.load_model(f"models:/trip_duration_model@champion")

# Load preprocessor from the same run
mv = client.get_model_version_by_alias("trip_duration_model", "champion")
art_path = mlflow.artifacts.download_artifacts(
    run_id=mv.run_id,
    artifact_path="preprocessor/preprocessor.pkl"
)
preprocessor = pickle.load(open(art_path, "rb"))

# Predict
X = preprocessor.transform(raw_df)
prediction = model.predict(X)
```

The preprocessor and model come from the same training run — they are guaranteed to match.

---

### The shared code problem

The preprocessor pickle stores class references, not class definitions. When you pickle
a `TripFeatureEngineer` object, Python saves `src.features.feature_engineering.TripFeatureEngineer`
— the module path, not the code.

When another process unpickles it, Python looks up that module path to reconstruct
the object. If the module isn't importable in the new process — crash.

**This is why `shared/feature_engineering.py` exists.**

Both the pipeline (training) and the API (serving) import from the same location.
The pickle references `shared.feature_engineering.TripFeatureEngineer`.
Both processes have `shared/` on their Python path. The pickle loads in both contexts.

```
4-Deploy-Online/
├── shared/
│   └── feature_engineering.py      ← single source of truth
├── pipeline/
│   └── src/features/
│       └── feature_engineering.py  ← one line: from shared.feature_engineering import *
└── api/
    └── model_loader.py              ← sys.path includes 4-Deploy-Online/ → shared importable
```

This pattern — shared preprocessing code between training and serving — is a real
production problem. It's called **training-serving skew** when the two diverge.
The `shared/` directory prevents it structurally.

---

## Part 3 — Connecting Concepts to Code

### The full registry flow in this project

```
flow.py                           model_registry.py
──────────────────────────────    ──────────────────────────────
train_single_model()              
  mlflow.sklearn.log_model()   →  Creates version N in registry
  
register_model()
  registry.transition_to_staging()
    client.set_registered_model_alias(name, "challenger", version)
    
  if promote_to_prod:
    registry.transition_to_production()
      client.set_registered_model_alias(name, "champion", version)
      
  # Save preprocessor to the model's run
  mlflow.log_artifact("preprocessor.pkl", artifact_path="preprocessor")
```

### Loading in the API

```python
# api/model_loader.py

# 1. Resolve alias → version → run ID
mv = client.get_model_version_by_alias("trip_duration_model", "champion")
# mv.version = "6", mv.run_id = "a7752301970f..."

# 2. Load model artifact
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")

# 3. Load preprocessor from the same run
art_path = mlflow.artifacts.download_artifacts(
    run_id=mv.run_id,
    artifact_path="preprocessor/preprocessor.pkl"
)
preprocessor = pickle.load(open(art_path, "rb"))
```

### Promoting a new champion

```python
from mlflow import MlflowClient
from config.config import MLFLOW_TRACKING_URI

import mlflow
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
client = MlflowClient()

# Promote version 7 to champion (demotes version 6 automatically)
client.set_registered_model_alias("trip_duration_model", "champion", "7")

# The API will serve the new model on next startup — no code change needed
```

---

## Part 4 — The Bigger Picture

### Where the registry sits in the MLOps stack

```
Training Pipeline      Trains models, logs metrics to tracking
        ↓
MLflow Tracking        Stores all run history, metrics, artifacts
        ↓
MLflow Registry        Versions and promotes the best models     ← this layer
        ↓
API / Batch / Retrain  Load @champion, serve predictions
        ↓
Monitoring             Detect drift, trigger retraining
```

The registry is the **hand-off point** between training and serving.
Everything upstream (data, training, evaluation) produces candidates.
Everything downstream (serving, monitoring, retraining) consumes the champion.

---

### What you actually built

```
Without registry:
  "I saved the model to pipeline/models/xgboost_v6.pkl"
  → Where is the preprocessor? What metrics did it get?
  → Which version is in production? When was it trained?
  → How do I roll back to the previous version?

With registry:
  models:/trip_duration_model@champion
  → Version 6, run a7752301, trained 2026-06-01
  → Test R²=0.817, MAE=3.07 min
  → Preprocessor at preprocessor/preprocessor.pkl in same run
  → Previous champion was version 5 — rollback = one alias reassignment
```

The registry turns model deployment from file management into a governed process.

---

## Quick Reference

### Key MLflow client methods

```python
from mlflow import MlflowClient
client = MlflowClient()

# Register a model version
mlflow.sklearn.log_model(sk_model=model, registered_model_name="trip_duration_model", ...)

# Set an alias
client.set_registered_model_alias("trip_duration_model", "champion", version="6")

# Remove an alias
client.delete_registered_model_alias("trip_duration_model", "champion")

# Get version by alias
mv = client.get_model_version_by_alias("trip_duration_model", "champion")
mv.version   # "6"
mv.run_id    # "a7752301970f426d9bd966566acf3b17"

# List all versions
versions = client.search_model_versions("name='trip_duration_model'")

# Load by alias
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")

# Download artifact from a run
path = mlflow.artifacts.download_artifacts(run_id=mv.run_id, artifact_path="preprocessor/preprocessor.pkl")
```

### Model URI formats

```
runs:/RUN_ID/ARTIFACT_PATH          → specific run, specific artifact
models:/MODEL_NAME/VERSION          → specific version number
models:/MODEL_NAME@ALIAS            → alias (production-safe, use this)
```

### View the registry

```bash
cd 4-Deploy-Online/pipeline
mlflow ui --backend-store-uri sqlite:///mlflow_trip_duration.db
# Open http://127.0.0.1:5000 → Models tab
```
