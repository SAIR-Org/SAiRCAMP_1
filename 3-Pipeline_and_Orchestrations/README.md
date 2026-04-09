# Pipeline & Orchestration — NYC Taxi Trip Duration

This folder contains two versions of the same ML pipeline, built progressively.
The ML logic is identical in both. What changes is the **orchestration layer**.

```
3-Pipeline_and_Orchestrations/
├── pipline_no_perfect/       Plain Python pipeline — no orchestration framework
└── pipeline_with_prefect/    Same pipeline + Prefect orchestration added on top
```

---

## The Progression

```
Stage 1 (previous folder)   MLflow only            — track experiments, register models
Stage 2 (this folder)       Plain Python pipeline  — structure the code into a repeatable pipeline
Stage 3 (this folder)       + Prefect              — orchestrate the pipeline, observe it live
```

Each stage builds on the previous. Nothing is rewritten — it is extended.

---

## Side-by-Side Comparison

| | `pipline_no_perfect/` | `pipeline_with_prefect/` |
|---|---|---|
| **Orchestration** | `NYCTaxiMLPipeline` class | `@flow` + `@task` (Prefect) |
| **Step structure** | Methods on a class | `@task` functions called from the flow |
| **Retries** | `@retry_with_backoff` decorator (manual) | `@task(retries=N)` (Prefect-managed) |
| **Logging** | `logging.getLogger()` (terminal + file) | `get_run_logger()` (terminal + Prefect UI) |
| **Failure info** | Python traceback — which step failed? | Named task state — `train-model [Random Forest] Failed` |
| **Retry visibility** | Silent — you see the final result | Retry attempts visible in UI with timestamps |
| **Model training** | Loop inside a class method | Each model = separate `@task` called from the flow |
| **UI** | None | Prefect UI at `http://127.0.0.1:4200` |
| **New dependencies** | None | `prefect>=2.14.0` |
| **ML results** | Identical | Identical |

---

## Where Prefect Is Injected

Prefect touches **3 files** and adds **1 new file**. Everything else is unchanged.

### 1. `flow.py` — NEW FILE (the only place Prefect decorators live)

This is the orchestration boundary. All `@task` and `@flow` definitions are here.
The `src/` modules remain plain Python — no Prefect imports, no Prefect coupling.

```python
# BEFORE (pipline_no_perfect/src/pipeline.py)
class NYCTaxiMLPipeline:
    def run(self):
        raw_data    = self.step_1_acquire_data()
        clean_data  = self.step_2_preprocess_data(raw_data)
        splits      = self.step_3_split_data(clean_data)
        features    = self.step_4_engineer_features(splits)
        results     = self.step_5_train_models(features)   # ← all 5 models in one block
        ...

# AFTER (pipeline_with_prefect/flow.py)
from prefect import flow, task, get_run_logger

@task(name="acquire-data", retries=3, retry_delay_seconds=10)     # ← retries declared here
def acquire_data(config): ...

@task(name="train-model", retries=1, retry_delay_seconds=30)      # ← each model retried individually
def train_single_model(model_name, model, ...): ...

@flow(name="nyc-taxi-ml-pipeline", log_prints=True)
def nyc_taxi_pipeline(sample_size: int = 200000, tune: bool = True,
                      promote_to_prod: bool = False, experiment_name: Optional[str] = None):
    raw_data   = acquire_data(config)                              # ← task call from flow
    clean_data = preprocess_data(raw_data, config)
    ...
    for model_name, model in model_portfolio.items():             # ← loop in the FLOW
        result = train_single_model(model_name, model, ...)       # ← each gets its own TaskRun
```

**Critical rule:** Tasks must be called from the **flow**, not from inside another task.
A task calling a task loses all tracking (no retries, no UI row, no state).

---

### 2. `src/data/data_acquisition.py` — MODIFIED

```python
# REMOVED in pipeline_with_prefect/:
@retry_with_backoff(max_retries=3, initial_delay=5.0)
def download_dataset(self, dataset_name: str) -> str:
    ...

# REPLACED BY (in flow.py):
@task(name="acquire-data", retries=3, retry_delay_seconds=10)
def acquire_data(config):
    ...
```

The `@retry_with_backoff` decorator is deleted from the module.
Prefect's `@task(retries=3)` does the same thing — but retry attempts are now
visible in the UI with timestamps and error messages.

---

### 3. `src/models/model_training.py` — MODIFIED

```python
# REMOVED in pipeline_with_prefect/:
@retry_with_backoff(max_retries=2, initial_delay=10.0)
def train_single_model(self, model, X_train, y_train, ...):
    ...

# ADDED — standalone function so the flow can iterate models:
def build_model_portfolio(config: ModelConfig) -> Dict:
    """Called by flow.py to get models without instantiating full ModelTrainer."""
    return {
        'Linear Regression': LinearRegression(),
        'Ridge': Ridge(...),
        'Lasso': Lasso(...),
        'Random Forest': RandomForestRegressor(...),
        'Gradient Boosting': GradientBoostingRegressor(...)
    }
```

The `build_model_portfolio()` function is needed because the flow iterates models
and submits each as a separate task. Without it, you'd need to instantiate
`ModelTrainer` (which builds all 5 models) just to get the model names.

---

### 4. `config/config.py` — MODIFIED

```python
# REMOVED in pipeline_with_prefect/:
@dataclass
class RetryConfig:
    max_retries: int = 3
    initial_delay: float = 5.0
    backoff_factor: float = 2.0
    max_delay: float = 60.0

# WHY: Prefect handles all retry configuration at the @task level.
#      RetryConfig is now dead code.
```

---

## What You Gain from Prefect

### Before (plain Python failure)
```
Traceback (most recent call last):
  File "src/pipeline.py", line 312, in step_5_train_models
    metrics, model, run_id = trainer.train_single_model(model, ...)
  File "src/models/model_training.py", line 108, in train_single_model
    model.fit(X_train, y_train)
MemoryError
```
You know it failed. You don't know which of the 5 models, how many retries happened,
or what state the other 4 models are in.

### After (Prefect task visibility)
```
Task run 'train-model [Linear Regression]'   Completed   1.2s
Task run 'train-model [Ridge]'               Completed   18s
Task run 'train-model [Lasso]'               Completed   21s
Task run 'train-model [Random Forest]'       Retrying    attempt 1/2   ← MemoryError
Task run 'train-model [Random Forest]'       Completed   91s           ← recovered
Task run 'train-model [Gradient Boosting]'   Completed   142s
```
You know exactly which task failed, how many retries it took, and that the
other 4 models completed successfully.

---

## Running the Pipelines

### Plain pipeline

```bash
cd pipline_no_perfect
python main.py --sample-size 50000 --skip-tuning    # quick test
python main.py --sample-size 200000                  # full run with tuning
```

### Prefect pipeline (terminal only)

```bash
cd pipeline_with_prefect
python main.py --sample-size 50000 --no-tune         # quick test
python main.py --sample-size 200000 --tune           # full run with tuning
python main.py --sample-size 200000 --tune --promote # full run + promote to Production
```

### Prefect pipeline (with UI)

```bash
# Terminal 1
prefect server start
# Open http://127.0.0.1:4200

# Terminal 2
cd pipeline_with_prefect
python main.py --sample-size 100000 --no-tune
```

### View MLflow results (both pipelines write to the same schema)

```bash
# From inside either pipeline folder
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db
# Open http://127.0.0.1:5000
```

---

## Results

Both pipelines produce identical ML results — Prefect is orchestration only.

| Metric | Value |
|---|---|
| Best model | Gradient Boosting |
| Test R² | 0.8382 |
| Test MAE | 2.27 minutes |
| MLflow | Model registered → Staging |

---

## What's Next

The natural next step after Prefect orchestration is **deployment**:
- Serve the registered model via a REST API (FastAPI + MLflow `pyfunc`)
- Containerize the serving layer (Docker)
- Schedule recurring retraining runs (Prefect deployments + schedules)

These are intentionally not in this folder — orchestration is one concept at a time.
