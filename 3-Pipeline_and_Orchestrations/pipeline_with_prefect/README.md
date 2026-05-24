# NYC Taxi ML Pipeline — Prefect Orchestrated

This folder adds **Prefect orchestration** on top of `pipline_no_perfect/`.
The ML logic is identical. The difference is *how* the pipeline is run and *what you can observe*.

---

## What Changed vs `pipline_no_perfect/`

| `pipline_no_perfect/` | `pipeline_with_prefect/` | Why |
|---|---|---|
| `NYCTaxiMLPipeline` class | `@flow` function in `flow.py` | Flow is the Prefect unit of work |
| `pipeline.step_N_*()` methods | `@task` functions called from the flow | Tasks get individual state tracking |
| `@retry_with_backoff` decorator | `@task(retries=N, retry_delay_seconds=N)` | Retries now visible in UI with timestamps |
| `logging.getLogger()` | `prefect.get_run_logger()` | Logs appear in the Prefect UI per task |
| `train_all_models()` loop in class | Each model is a separate `@task` call in the flow | Each model gets its own UI row and retry |
| Python traceback on failure | Named task state: Pending / Running / Failed / Completed | Failure is pinpointed to the exact task |
| No UI | Prefect UI at `http://127.0.0.1:4200` | Watch the pipeline live |

### Files changed from `pipline_no_perfect/`

```
flow.py                           NEW  — all @task and @flow definitions (only Prefect file)
main.py                           NEW  — simple CLI entry point
config/config.py                  MOD  — removed RetryConfig (Prefect handles retries)
src/data/data_acquisition.py      MOD  — removed @retry_with_backoff decorators
src/models/model_training.py      MOD  — removed @retry_with_backoff, added build_model_portfolio()
```

### Files unchanged

```
src/data/data_preprocessing.py
src/features/feature_engineering.py
src/models/model_registry.py
src/models/model_deployment.py
src/utils/logging_utils.py
src/utils/retry_utils.py          kept for reference, no longer used
```

---

## Pipeline Architecture

```
@flow  nyc_taxi_pipeline(sample_size, tune, promote_to_prod, experiment_name)
│
├── @task  acquire_data            retries=3, delay=10s
├── @task  preprocess_data
├── @task  split_data
├── @task  engineer_features
│
├── @task  train_single_model  [Linear Regression]    retries=1, delay=30s
├── @task  train_single_model  [Ridge]                retries=1, delay=30s
├── @task  train_single_model  [Lasso]                retries=1, delay=30s
├── @task  train_single_model  [Random Forest]        retries=1, delay=30s
├── @task  train_single_model  [Gradient Boosting]    retries=1, delay=30s
│
├── @task  select_best_model
├── @task  tune_model              (skipped if --no-tune or model not tunable)
├── @task  evaluate_model
└── @task  register_model          retries=2, delay=5s
```

The training loop lives in the **flow**, not inside a task. This is the critical
Prefect rule: a task calling another task loses all tracking. Tasks must be called
from the flow to get retries, state, and UI visibility.

---

## How to Run

### Without the UI (terminal only)

```bash
# From repo root (one-time):
uv sync
source .venv/bin/activate

cd 3-Pipeline_and_Orchestrations/pipeline_with_prefect

# Quick test
python main.py --sample-size 50000 --no-tune

# Full run with tuning
python main.py --sample-size 200000 --tune

# Full run + promote best model to Production in MLflow
python main.py --sample-size 200000 --tune --promote

# Custom MLflow experiment name
python main.py --experiment-name my_run_v2
```

### With the Prefect UI

```bash
# Terminal 1 — start the server
prefect server start
# UI at http://127.0.0.1:4200

# Terminal 2 — run the pipeline
cd pipeline_with_prefect
python main.py --sample-size 100000 --no-tune
```

Open `http://127.0.0.1:4200` while the pipeline runs and watch each task appear.

### View MLflow results

```bash
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db
# Open http://127.0.0.1:5000
```

---

## What the Prefect UI Shows

```
Flow Run: nyc-taxi-ml-pipeline / romantic-beetle
Status: Completed   Duration: 4m 32s

Tasks:
  acquire-data         Completed   0.8s
  preprocess-data      Completed   2.1s
  split-data           Completed   0.3s
  engineer-features    Completed   4.2s
  train-model          Completed   1.2s    [Linear Regression]
  train-model          Completed   18s     [Ridge]
  train-model          Completed   21s     [Lasso]
  train-model          Completed   87s     [Random Forest]
  train-model          Completed   142s    [Gradient Boosting]
  select-best-model    Completed   0.1s
  tune-model           Completed   54s
  evaluate-model       Completed   0.2s
  register-model       Completed   0.5s
```

If a task fails and retries:

```
  train-model          Retrying    [Random Forest]   attempt 1/2
  train-model          Completed   [Random Forest]   91s
```

---

## Project Structure

```
pipeline_with_prefect/
├── flow.py               WHERE PREFECT LIVES — read this to understand the orchestration
├── main.py               CLI entry point
├── requirements.txt      prefect>=2.14.0 is the only new dependency
├── README.md
├── config/
│   └── config.py         Config dataclasses (RetryConfig removed)
└── src/
    ├── data/
    │   ├── data_acquisition.py    retry decorators removed
    │   └── data_preprocessing.py  unchanged
    ├── features/
    │   └── feature_engineering.py unchanged
    ├── models/
    │   ├── model_training.py      retry removed, build_model_portfolio() added
    │   ├── model_registry.py      unchanged
    │   └── model_deployment.py    unchanged
    └── utils/
        ├── logging_utils.py       unchanged
        └── retry_utils.py         kept for reference, not used
```

---

## Key Design Decisions

### Why is `flow.py` the only Prefect file?
Prefect is an orchestration layer, not an ML layer. All `src/` modules remain plain
Python — testable, importable, and usable without Prefect. The boundary is explicit.

### Why does the training loop live in the flow, not in a task?
Prefect rule: when a `@task` calls another `@task`, the inner task runs as plain Python.
It loses state tracking, retries, and UI visibility. The training loop must be in the
`@flow` so each model gets its own tracked TaskRun.

### Why `Optional[str]` for `experiment_name`?
Prefect 3.x uses Pydantic for flow parameter validation. `str = None` fails validation
because `str` is not nullable. `Optional[str] = None` is required.

### Why not use `.submit()` for parallel training?
Sequential for now — keeps the code readable and focused on the task/flow pattern.
Switching to parallel is one line per model:
```python
# Current (sequential):
result = train_single_model(name, model, ...)

# Future (parallel):
future = train_single_model.submit(name, model, ...)
```

---

## Actual Results (200K samples, tuning enabled)

Same ML results as `pipline_no_perfect/` — the ML logic is identical, only orchestration changed.

**Winner: Gradient Boosting — Test R²: 0.8382, Test MAE: 2.27 min**
Model registered as version 5 → Staging in MLflow.
