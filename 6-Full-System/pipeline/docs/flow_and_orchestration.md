# Flow and Orchestration

**File:** `flow.py`  
**Framework:** Prefect 3.x

---

## Overview

`flow.py` is the only file where Prefect exists in this pipeline. Every `src/` module is plain Python — testable, importable, and runnable without Prefect. The flow wires them together and adds observability.

---

## The 9 Steps

```
Step 1   acquire_data              Download TLC parquet, sample per month
Step 2   preprocess_data           Clean data, compute duration target
Step 3   split_data                train/val/test split (before feature engineering)
Step 4   engineer_features         Fit preprocessor on train, transform all sets
Step 5a  train_single_model × 6    One @task per model (LR, Ridge, Lasso, RF, GBM, XGB)
Step 5b  select_best_model         Pick winner by validation R²
Step 6   tune_model                HalvingRandomSearchCV on the best model
Step 7   evaluate_model            Test set evaluation — runs exactly once
Step 8   register_model            MLflow registry → @challenger or @champion
Step 9   log_feature_importance    Tree model feature importances as artifact
```

---

## Why Each Step Is a Separate @task

**Step 1 — acquire_data** `retries=3, retry_delay_seconds=10`  
Network calls fail. Three retries with backoff handle transient S3/CloudFront errors. The retry is visible in the Prefect UI — you can see which month failed and how many attempts it took.

**Steps 2–4 — preprocess, split, engineer**  
These are pure data transformations. Making them tasks gives each step:
- Its own timing in the UI (students see that feature engineering takes ~2s, not the 90s they expect)
- Isolated failure: if preprocessing fails, Prefect knows exactly which step failed and why

**Step 5a — train_single_model × 6** `retries=1, retry_delay_seconds=30`  
Each model is a separate task. Critical design decision:

```python
# In the FLOW (not inside a task):
for model_name, model in model_portfolio.items():
    result = train_single_model(model_name, model, ...)
```

This gives each model its own TaskRun row in the Prefect UI. If XGBoost fails, only XGBoost retries — not all 6 models. In the future, changing `train_single_model(...)` to `train_single_model.submit(...)` makes all 6 run in parallel — one word change.

**Step 5b — select_best_model**  
Isolated selection logic. The UI shows the winner as a distinct step, making it clear that selection is a deliberate gate, not just a side effect of training.

**Step 6 — tune_model**  
No retries — tuning failures are deterministic (OOM, bad params), not transient. Returns `None` if the model is not tunable or if tuning doesn't improve. The flow handles `None` gracefully.

**Step 7 — evaluate_model**  
The test set is sacred. Making evaluation a separate task enforces the contract: it runs exactly once, after all training and tuning. Students can verify in the UI that it ran after the tuning step.

**Step 8 — register_model** `retries=2, retry_delay_seconds=5`  
Registry writes talk to the SQLite database. Two retries handle file locking issues if another process is accessing the DB.

**Step 9 — log_feature_importance**  
Post-registration audit step. Kept separate because it has no effect on the model — it's purely informational logging. Easy to skip or re-run independently.

---

## The No-Leakage Guarantee

The split happens in Step 3, **before** the preprocessor fits in Step 4:

```
Step 3: X_train_raw, X_val_raw, X_test_raw = split(X, y)
Step 4: preprocessor.fit(X_train_raw)          ← training data only
        X_train_p = preprocessor.transform(X_train_raw)
        X_val_p   = preprocessor.transform(X_val_raw)   ← unseen
        X_test_p  = preprocessor.transform(X_test_raw)  ← unseen
```

The scaler's median, IQR, and the outlier bounds are computed from training rows only. Val and test rows are transformed using those training-derived parameters — exactly as production inference would work.

---

## Flow Parameters

```python
@flow
def trip_duration_pipeline(
    sample_size:     int  = 500_000,
    tune:            bool = False,
    promote_to_prod: bool = False,
    experiment_name: str  = None,
)
```

These parameters appear in the Prefect UI and can be edited for re-runs without touching code. A student can trigger a new run from the UI with `sample_size=50000` to test a change quickly.

### CLI flags (main.py)

```bash
python main.py --sample-size 500000   # how many rows to train on
python main.py --tune                 # run HalvingRandomSearchCV
python main.py --no-tune              # skip tuning (faster)
python main.py --promote              # promote winner to @champion
```

---

## Prefect Server (optional)

The pipeline runs without a Prefect server — Prefect starts a temporary local server automatically. To see the full UI:

```bash
# Terminal 1:
prefect server start
# → http://127.0.0.1:4200

# Terminal 2:
python main.py --sample-size 500000 --tune --promote
```

With the server running, every task appears as a node in the flow graph, with timing, logs, and retry state visible in real time.

---

## MLflow vs Prefect: What Each Tracks

| | MLflow | Prefect |
|---|---|---|
| **What** | Model artifacts, metrics, params | Task execution, timing, retries |
| **When** | During training (inside @tasks) | During orchestration (the @flow) |
| **UI** | Model comparison, experiment browser | Task graph, failure state, run history |
| **Persistent** | Yes — survives pipeline re-runs | Ephemeral by default (local server) |

They complement each other. MLflow answers "which model is best?" Prefect answers "did the pipeline run successfully and how long did each step take?"
