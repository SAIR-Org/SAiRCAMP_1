# Prefect Quick Start — Mental Model, Concepts & Reference

---

## Part 1 — What Is Orchestration? (The Mental Model)

### Start with a factory floor

Imagine a car factory. There are 10 stations on the assembly line:
frame → engine → doors → paint → electronics → wheels → test → inspect → pack → ship.

A **worker** knows how to do their station. They don't know what happens before or after them.
A **foreman** knows the order, knows when a station fails, decides whether to retry or stop,
and reports status to management.

**In software:**
- Workers = your functions (`acquire_data`, `train_model`, `register_model`)
- Foreman = the orchestrator (Prefect)
- Management = you, watching the UI

Without a foreman, if the paint station fails at 2am, nobody knows. The car is half-built.
Wheels were waiting. Ship never gets called. You find out in the morning from a dead process.

With a foreman, the failure is caught immediately. The foreman knows:
- Paint failed (which station)
- Frame, engine, doors completed (what's safe)
- Wheels, test, inspect, pack, ship did not run (what was skipped)
- Paint was retried twice before giving up (retry history)

**That's orchestration.** It's the foreman layer.

---

### The three stages of a pipeline

Most ML pipelines go through three maturity stages:

**Stage 1 — Script**
```
python train.py
```
A single file. Works on your laptop. No structure. If it fails at step 7 of 10,
you rerun from step 1. No retry logic. No visibility. Logs to terminal and gone.

**Stage 2 — Structured Pipeline**
```python
class NYCTaxiMLPipeline:
    def run(self):
        data    = self.step_1_acquire()
        clean   = self.step_2_preprocess(data)
        splits  = self.step_3_split(clean)
        ...
```
Steps are named, ordered, and separated. Better. But failure is still just a Python
traceback. You see *that* it failed. You don't see *what state the world is in* or
*which step* failed without reading the trace. This is `pipline_no_perfect/`.

**Stage 3 — Orchestrated Pipeline**
```python
@flow
def nyc_taxi_pipeline():
    data    = acquire_data()
    clean   = preprocess_data(data)
    splits  = split_data(clean)
    ...
```
Now each step is a tracked unit. The orchestrator knows the state of every step,
manages retries, exposes a UI, stores run history. This is `pipeline_with_prefect/`.

**The ML logic does not change between Stage 2 and Stage 3.**
You're adding a management layer, not changing the work.

---

### What "observable" means

A pipeline is **observable** when you can answer these questions without reading code:

- Is it running right now?
- Which step is it on?
- How long has this step been running?
- Did any step fail? Which one? Why?
- How many times did it retry?
- What were the inputs and outputs?
- When did the last successful run finish?

A Python script answers none of these. A Prefect flow answers all of them.
Observability is the core value proposition of an orchestration tool.

---

### What a DAG is

DAG = Directed Acyclic Graph. Every orchestration tool talks about DAGs.

**Directed** — steps have a direction. A → B means A must finish before B starts.
**Acyclic** — no cycles. You can't have A → B → A. The pipeline must end.
**Graph** — steps can branch and merge, not just run in a straight line.

Your pipeline is a simple linear DAG:

```
acquire → preprocess → split → engineer → [train×5] → select → tune → evaluate → register
```

The `[train×5]` part is 5 parallel-capable branches that merge back at `select`.

Why does this matter? The orchestrator uses the DAG to:
- Know what can run in parallel (the 5 training tasks)
- Know what must wait (select_best_model waits for all 5)
- Know what to skip when a step fails (nothing after the failed step runs)
- Know how to resume (re-run from the failed step, not from the start)

In Prefect, you don't draw the DAG. The execution order of your task calls in the
flow function *is* the DAG. Prefect infers it from the code.

---

### The contract between orchestrator and developer

When you add Prefect, you're making a deal:

**You promise:**
- Each `@task` is a self-contained unit of work
- A task can be retried from scratch without breaking anything
- Tasks communicate through return values, not shared mutable state

**Prefect promises:**
- Track every task run with state, timing, and logs
- Retry failed tasks according to your declared policy
- Give you a UI to observe everything
- Store run history so you can compare runs

This contract is why tasks need to be pure-ish functions. If `train_single_model`
has side effects that can't be repeated safely, retries will cause problems.
In your project, MLflow handles this — each retry creates a new MLflow run,
so duplicate attempts are harmless.

---

## Part 2 — Prefect Specifically

### Why Prefect over Airflow?

Airflow is the industry standard. But it was designed for data engineering in 2014,
before ML pipelines were common. To run a simple Airflow pipeline locally you need:
PostgreSQL, Redis, a scheduler process, a webserver process, a worker process,
and Docker. That's a lot of infrastructure for a laptop.

Prefect was designed in 2018 with Python-first development as the goal.
A Prefect pipeline runs with `pip install prefect` and nothing else.
The server is optional — the flow runs fine without it.

For ML development and learning, Prefect is the right starting point.
The concepts (task, flow, state, retry, schedule, deployment) are identical to Airflow.
When you encounter Airflow in a job, you already understand the mental model.

---

### The Prefect execution model

When you call `nyc_taxi_pipeline()`, here is what actually happens:

```
1. Python calls nyc_taxi_pipeline()

2. Prefect intercepts the call (because of @flow decorator)

3. Prefect creates a FlowRun object
   - assigns it a name (e.g. "romantic-beetle")
   - assigns it a unique ID
   - records start time
   - stores it in ~/.prefect/prefect.db (local SQLite)

4. Prefect starts executing the flow function body

5. When flow calls acquire_data(config):
   - Prefect creates a TaskRun object for acquire_data
   - Sets state: Pending → Running
   - Executes the function
   - On success: sets state Completed, stores return value
   - On failure: checks retry policy, sets Retrying or Failed

6. The return value of acquire_data() is passed to the next task call

7. Repeat for every @task call in the flow

8. When flow function returns:
   - FlowRun state set to Completed
   - Total duration recorded

9. If prefect server is running at http://127.0.0.1:4200:
   - All of the above is sent to the server API in real time
   - UI updates live as each task transitions state
```

Without the server, steps 1–8 happen exactly the same. Step 9 is skipped.
The server is a visibility layer, not a requirement.

---

### The two decorators — what they actually do

```python
@task(name="acquire-data", retries=3, retry_delay_seconds=10)
def acquire_data(config):
    downloader = DataAcquisition(config.data)
    return downloader.load_data(config.data.sample_size)
```

`@task` wraps `acquire_data` in a Prefect-aware wrapper. When called:
1. Creates a TaskRun with the given name
2. Executes the original function body
3. On exception: applies retry policy
4. Returns the function's return value as normal

The function still works exactly like a normal Python function from the caller's perspective.
`result = acquire_data(config)` — you get the return value back. Nothing changes in the flow.

```python
@flow(name="nyc-taxi-ml-pipeline", log_prints=True)
def nyc_taxi_pipeline(sample_size: int = 200000, ...):
    ...
```

`@flow` wraps the flow function. `log_prints=True` means any `print()` call inside
the flow or its tasks gets captured and stored in the run logs automatically.

---

### The one rule — why nested tasks break

This is the most important concept in Prefect. It comes up constantly.

When Prefect sees a `@task` call, it checks: **am I currently inside a flow run?**

- Called from `@flow` → creates a proper TaskRun with full tracking
- Called from `@task` → Prefect is already inside a task context, cannot create a nested TaskRun → runs as plain Python

```python
@task
def train_all_models(portfolio, X_train, y_train):
    results = {}
    for name, model in portfolio.items():
        # This looks like it should work. It doesn't.
        # Prefect sees this task-inside-task call and runs it as plain Python.
        # No TaskRun created. No state. No retries. No UI row.
        results[name] = train_single_model(name, model, X_train, y_train)
    return results

@flow
def pipeline():
    train_all_models(portfolio, X_train, y_train)  # only ONE task row in UI
    # What you see: train-all-models Completed
    # What you wanted: 5 separate train-model rows
```

```python
@flow
def pipeline():
    results = {}
    for name, model in portfolio.items():
        # Called from flow → full TaskRun for each model
        results[name] = train_single_model(name, model, X_train, y_train)
    # What you see: 5 separate train-model rows, each with its own retry budget
```

**This is why `build_model_portfolio()` exists in `model_training.py`.**
The flow needs the model dict to iterate it. A standalone function provides
that without forcing the flow to instantiate `ModelTrainer`.

---

### States — the full picture

States are how Prefect communicates what happened.

```
PENDING     Task is queued, not yet started
RUNNING     Task is currently executing
COMPLETED   Task finished successfully, return value stored
FAILED      Task raised an exception, all retries exhausted
RETRYING    Task failed, waiting before next attempt
CRASHED     Unexpected infrastructure failure (process killed, OOM)
CANCELLED   Manually cancelled by user
PAUSED      Waiting for human input (advanced use case)
```

States are objects, not strings. They carry data:

```python
from prefect.states import Completed, Failed

state = Completed(data={"model": "gradient_boosting", "r2": 0.8382})
state = Failed(message="MemoryError during Random Forest training, attempt 2/2")
```

You usually don't work with state objects directly. Prefect manages them.
But understanding them helps when reading logs and UI output.

---

## Part 3 — Connecting Concepts to Code

### Retries — manual vs Prefect

**Before (manual — `pipline_no_perfect/src/utils/retry_utils.py`)**

```python
def retry_with_backoff(max_retries=3, initial_delay=5.0, backoff_factor=2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        raise
                    time.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator

@retry_with_backoff(max_retries=3, initial_delay=5.0)
def download_dataset(self, dataset_name):
    ...
```

Works perfectly. But when it retries at 2am, you see nothing.
The process is sleeping. No log entry for the retry. No timestamp.
The first you know about it is either success or a final exception.

**After (Prefect — `pipeline_with_prefect/flow.py`)**

```python
@task(name="acquire-data", retries=3, retry_delay_seconds=10)
def acquire_data(config):
    downloader = DataAcquisition(config.data)
    return downloader.load_data(config.data.sample_size)
```

Same behavior. Plus:
- Each retry attempt logged with timestamp and error message
- State visible in UI: `Retrying (attempt 2/3)`
- Retry history stored permanently — you can look back days later
- No code to maintain in `retry_utils.py`

**Retry counts in this project:**

| Task | Retries | Reason |
|---|---|---|
| `acquire_data` | 3 | Network / Kaggle API flakiness |
| `train_single_model` | 1 | Memory spikes on large models |
| `register_model` | 2 | MLflow registry can be briefly unavailable |
| All others | 0 | Deterministic — retrying won't help |

---

### Logging — where logs go

```python
# pipline_no_perfect — standard Python logging
import logging
logger = logging.getLogger(__name__)

# Goes to: terminal + logs/pipeline.log
# Not linked to any specific step. All 13 steps' logs are interleaved.
# To find why Random Forest failed: grep through the whole file.
```

```python
# pipeline_with_prefect — Prefect logger
from prefect import get_run_logger

@task
def train_single_model(model_name, model, ...):
    logger = get_run_logger()  # must be called inside the task
    logger.info(f"Training {model_name}...")

# Goes to: terminal + Prefect UI, attached to this specific TaskRun
# In the UI: click train-model [Random Forest] → see only that model's logs
# Every other model's logs are in their own TaskRun, separate
```

`get_run_logger()` returns a standard Python logger with Prefect handlers attached.
It must be called inside the task body — not at module level — because it needs
to know which TaskRun it belongs to. That context only exists during execution.

---

### Flow parameters and Pydantic

```python
@flow(name="nyc-taxi-ml-pipeline")
def nyc_taxi_pipeline(
    sample_size: int = 200000,
    tune: bool = True,
    promote_to_prod: bool = False,
    experiment_name: Optional[str] = None
):
```

Prefect 3.x uses **Pydantic** under the hood to validate flow parameters.
Pydantic is a Python library for data validation using type annotations.

Type annotations here are not documentation — they're enforced:

```python
nyc_taxi_pipeline(sample_size="big")   # Pydantic raises: int expected, got str
nyc_taxi_pipeline(tune=1)              # Pydantic coerces: 1 → True (int to bool ok)
nyc_taxi_pipeline(experiment_name=None)  # OK if Optional[str], FAILS if just str
```

**The bug this project hit:**
```python
# Broken — Pydantic sees str type, rejects None value
experiment_name: str = None

# Fixed — Optional[str] = Union[str, None], allows both
experiment_name: Optional[str] = None
```

This matters because parameters are also how you trigger flows from the UI.
You can fill in a form with `sample_size=50000`, `tune=False` and Prefect validates
the types before the flow even starts.

---

### Sequential vs parallel execution

**Current — sequential**

```python
@flow
def nyc_taxi_pipeline(...):
    for name, model in model_portfolio.items():
        result = train_single_model(name, model, ...)  # blocking
        training_results[name] = result
# Total runtime = LR(1s) + Ridge(18s) + Lasso(21s) + RF(87s) + GB(142s) = ~269s
```

**Future — parallel (one line change)**

```python
from prefect.task_runners import ConcurrentTaskRunner

@flow(task_runner=ConcurrentTaskRunner())
def nyc_taxi_pipeline(...):
    futures = {}
    for name, model in model_portfolio.items():
        futures[name] = train_single_model.submit(name, model, ...)  # non-blocking
    results = {name: f.result() for name, f in futures.items()}      # wait here
# Total runtime = max(GB) = ~142s   (roughly 2x speedup)
```

`.submit()` returns a `PrefectFuture` immediately — a promise of a future value.
The task runs in the background. `.result()` blocks until it finishes and returns
the actual value.

Sequential is used in this project to keep the code readable. It teaches the
task/flow pattern without the complexity of futures.

---

## Part 4 — The Bigger Picture

### Where Prefect sits in the MLOps stack

```
Data Sources          Kaggle, databases, APIs, S3
      ↓
Orchestration         Prefect (@flow + @task)       ← this layer
      ↓
Experiment Tracking   MLflow (runs, metrics, params)
      ↓
Model Registry        MLflow (versions, stages)
      ↓
Serving               FastAPI + mlflow.pyfunc
      ↓
Monitoring            Evidently, Grafana
```

Prefect manages *when* and *how* things run.
MLflow manages *what was run* and *what was produced*.
They are complementary — not alternatives.

In this project, every `@task` that touches ML logs to MLflow.
Prefect tracks the orchestration. MLflow tracks the experiments.
You need both to have the full picture.

---

### The natural progression from here

```
1. MLflow                   Track experiments, compare runs, register models
2. Structured pipeline      Repeatable, modular code
3. Prefect orchestration    Observable, retriable, parameterized        ← you are here
4. Prefect schedules        Run on a cron: retrain every Monday at 6am
5. Prefect deployments      Package the flow, run it from anywhere (server, cloud)
6. REST API serving         Serve the registered model as a prediction endpoint
7. Docker                   Containerize pipeline + serving for reproducibility
8. Cloud / Kubernetes       Production scale, managed infrastructure
```

Each step makes the previous more powerful. You don't need step 8 to have a working
system. Step 3 alone is enough for a data science team to work reliably.

---

### What you actually built

```
pipline_no_perfect/     "A Python class that runs ML steps in order"
                         Failure = traceback somewhere in a 300-line stack
                         Retries = silent, manual, invisible
                         Visibility = a log file you have to grep

pipeline_with_prefect/  "A Prefect flow with 13 tracked task runs"
                         Failure = named task with state, error, retry history
                         Retries = declared policy, visible in UI with timestamps
                         Visibility = live UI at http://127.0.0.1:4200
```

The ML logic is identical. The model performance is identical.
What changed is your ability to **observe, control, and trust** the pipeline.

That is the value of orchestration.

---

## Quick Reference

### Install and run

```bash
pip install prefect

# Run without UI (works immediately)
python main.py --sample-size 50000 --no-tune

# Run with UI
prefect server start                          # Terminal 1 — http://127.0.0.1:4200
python main.py --sample-size 100000 --no-tune # Terminal 2
```

### Decorator signatures

```python
from prefect import flow, task, get_run_logger
from typing import Optional

@task(
    name="my-task",           # name shown in UI
    retries=3,                # retry attempts on exception
    retry_delay_seconds=10,   # wait between retries
    timeout_seconds=300,      # fail if takes longer than this
    tags=["ml", "training"]   # UI labels for filtering
)
def my_task(arg1, arg2):
    logger = get_run_logger()
    logger.info("running")
    return result

@flow(
    name="my-flow",           # name shown in UI
    log_prints=True,          # capture print() calls
    timeout_seconds=3600      # fail entire flow after 1 hour
)
def my_flow(param: int = 100, name: Optional[str] = None):
    result = my_task(param, name)
    return result
```

### Parallel execution

```python
from prefect.task_runners import ConcurrentTaskRunner

@flow(task_runner=ConcurrentTaskRunner())
def parallel_flow():
    futures = [my_task.submit(i) for i in range(10)]
    results = [f.result() for f in futures]
```

---

## Official Documentation

- Prefect concepts: https://docs.prefect.io/latest/concepts/
- Tasks: https://docs.prefect.io/latest/concepts/tasks/
- Flows: https://docs.prefect.io/latest/concepts/flows/
- States: https://docs.prefect.io/latest/concepts/states/
- Task runners (parallel): https://docs.prefect.io/latest/concepts/task-runners/
- Deployments: https://docs.prefect.io/latest/concepts/deployments/
- Schedules: https://docs.prefect.io/latest/concepts/schedules/
