# Model Registry

**File:** `src/models/model_registry.py`  
**Class:** `ModelRegistry`

---

## Overview

Manages the MLflow model registry for `trip_duration_model`. Handles version registration, alias assignment, and the champion/challenger promotion pattern used across all Module 4 components.

---

## MLflow 3.x: Aliases Replace Stages

MLflow 2.9+ deprecated stage-based transitions. MLflow 3.x removed them entirely.

```
OLD (MLflow < 2.9) — broken in MLflow 3.x:
  client.transition_model_version_stage(model_name, version, "Production")
  mlflow.sklearn.load_model("models:/trip_duration_model/Production")

NEW (MLflow 3.x):
  client.set_registered_model_alias(model_name, "champion", version)
  mlflow.sklearn.load_model("models:/trip_duration_model@champion")
```

**Why aliases are better than stages:**
- A model can have multiple aliases simultaneously (e.g., `@champion` and `@v22`)
- Aliases are free-form strings — you can add domain-specific names (`@production`, `@canary`, `@rollback`)
- The `@alias` URI syntax is unambiguous in load calls

---

## Alias Convention

| Alias | Meaning | Who uses it |
|---|---|---|
| `@champion` | Currently deployed model | `api/`, `batch/`, `monitoring/`, `dashboard/` |
| `@challenger` | New model awaiting comparison | `retrain/` — compared against champion before promotion |

**The promotion flow:**

```
pipeline run
  → trains + evaluates new model
  → registers as @challenger

retrain/ (champion/challenger gate)
  → loads @champion and @challenger
  → evaluates both on holdout
  → if challenger wins: set @champion = challenger
  → if challenger loses: keep existing @champion
```

This gate prevents silent degradation. Without it, auto-retraining can produce a worse model and promote it automatically.

---

## How Downstream Components Load the Model

All downstream components use the same pattern:

```python
import mlflow
from config.config import MLFLOW_TRACKING_URI   # absolute path, works from any directory

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")
```

`MLFLOW_TRACKING_URI` is an absolute path computed from `config.py`'s location:
```
sqlite:////home/silva/.../4-Deploy-Online/pipeline/mlflow_trip_duration.db
```

This means `api/`, `batch/`, and `monitoring/` can all import this constant and point to the same database regardless of which directory they're run from.

---

## Version Lifecycle

```
Training run → model logged → version N created (no alias)
                                    ↓
register_model task → @challenger assigned to version N
                                    ↓
--promote flag → @champion reassigned to version N
                 previous @champion → no alias (still exists, not deleted)
```

Old versions are never deleted. Every training run is permanent. This means you can always roll back by re-assigning the `@champion` alias to any previous version:

```python
client.set_registered_model_alias("trip_duration_model", "champion", "16")
```

---

## Database

```
Location:  4-Deploy-Online/pipeline/mlflow_trip_duration.db
Format:    SQLite
Shared by: pipeline/, api/, batch/, monitoring/, retrain/
```

**Why a separate DB from Module 3?**  
`pipeline_with_prefect/` uses `mlflow_nyc_taxi.db` with model name `nyc_taxi_predictor`. Module 4 uses `mlflow_trip_duration.db` with model name `trip_duration_model`. Students can open both MLflow UIs independently and see the evolution from Module 3 to Module 4.

---

## Fallback Behavior

When `transition_to_staging()` can't find the run_id in the registry (happens when tuning ran but improvement < 0.01 threshold — no new version registered under the tuning run), it falls back to the most recently registered version:

```python
# tuning_run_id not found → fall back to latest version
if not version:
    all_versions = self.get_all_versions()
    version = all_versions[-1].version
```

This ensures registration always succeeds even when the tuning run didn't create a new version.

---

## Test Metrics Re-logging

A subtle bug: when tuning doesn't register a new version, `best_result['run_id']` points to the tuning run while the registered version lives on the base training run. Test metrics get logged to the wrong run.

The fix in `flow.py`'s `register_model` task:

```python
v_run_id = client.get_model_version(model_name, version).run_id
if v_run_id != best_result['run_id']:
    with mlflow.start_run(run_id=v_run_id):
        mlflow.log_metrics({'test_r2': ..., 'test_rmse': ..., 'test_mae': ...})
```

This ensures every registered version always has test metrics visible in the MLflow UI.
