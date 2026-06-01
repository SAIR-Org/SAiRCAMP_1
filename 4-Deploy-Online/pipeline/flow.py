"""
Prefect-orchestrated trip duration ML pipeline — 9 steps, 6 models, MLflow tracking.

Steps:
  1. acquire_data          download TLC parquet, sample per month
  2. preprocess_data       clean, filter, compute target
  3. split_data            train/val/test before feature engineering (no leakage)
  4. engineer_features     fit preprocessor on train only, transform all sets
  5. train_single_model    one @task per model (6 models)
  5b select_best_model     pick winner by val R²
  6. tune_model            HalvingRandomSearchCV on best model
  7. evaluate_model        test set evaluation (runs once, after all training)
  8. register_model        MLflow registry → @challenger or @champion
  9. log_feature_importance tree model importances as artifact

Usage:
  python main.py --sample-size 50000 --no-tune
  python main.py --sample-size 500000 --tune --promote
  prefect server start   # optional UI at http://127.0.0.1:4200
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))         # pipeline/ → config, src
sys.path.insert(0, str(Path(__file__).parent.parent))  # 4-Deploy-Online/ → shared

import mlflow
import numpy as np
from typing import Optional
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score

# ─── Prefect imports ──────────────────────────────────────────────────────────
# @flow  : marks the top-level orchestrator function
# @task  : marks each pipeline step as an observable, retry-able unit
# get_run_logger : returns a logger whose output appears in the Prefect UI
from prefect import flow, task, get_run_logger

# ─── Project imports (plain Python — no Prefect inside these) ─────────────────
from config.config import load_config
from src.data.data_acquisition import DataAcquisition
from src.data.data_preprocessing import DataPreprocessor
from shared.feature_engineering import build_preprocessor
from src.models.model_training import ModelTrainer, build_model_portfolio
from src.models.model_registry import ModelRegistry


# =============================================================================
# TASK 1 — Data Acquisition
#
# WHY @task:
#   retries=3 replaces the @retry_with_backoff(max_retries=3) decorator that
#   was on DataAcquisition.download_dataset() in pipline_no_perfect/.
#   The difference: Prefect retries are visible in the UI — you can see
#   "Attempt 1 failed: network timeout, retrying in 10s..." in the task log.
#
# WHY retry_delay_seconds=10:
#   TLC/S3 downloads can fail transiently. 10s gives the network time to recover.
# =============================================================================
@task(name="acquire-data", retries=3, retry_delay_seconds=10)
def acquire_data(config):
    """Download and load the TLC trip dataset."""
    logger = get_run_logger()
    logger.info("📥 Step 1: Data Acquisition")

    acquisition = DataAcquisition(config.data)
    df = acquisition.run()

    logger.info(f"✅ Loaded {len(df):,} rows, {df.shape[1]} columns")
    return df


# =============================================================================
# TASK 2 — Data Preprocessing
#
# WHY @task:
#   Isolates cleaning as a distinct observable step. If filtering removes too
#   many rows (data quality issue), this task fails with a clear error in the
#   UI — you see exactly which step failed without digging through logs.
#
# WHY no retries:
#   Preprocessing is deterministic. If it fails, retrying won't fix it.
#   The underlying problem needs fixing (bad data, config issue, etc.).
# =============================================================================
@task(name="preprocess-data")
def preprocess_data(df_raw, config):
    """Clean data and extract features/target."""
    logger = get_run_logger()
    logger.info("🧹 Step 2: Data Preprocessing")

    preprocessor = DataPreprocessor(config.data)
    X, y = preprocessor.run(df_raw)

    stats = preprocessor.get_statistics()
    logger.info(f"✅ {stats['final_rows']:,} rows retained "
                f"({stats['retention_pct']:.1f}% of {stats['initial_rows']:,})")
    return X, y


# =============================================================================
# TASK 3 — Data Splitting
#
# WHY @task:
#   Makes the train/val/test split a named, tracked step.
#   Splitting BEFORE feature engineering is the correct pattern (no leakage).
#   Having it as a task makes this contract explicit and visible in the UI.
# =============================================================================
@task(name="split-data")
def split_data(X, y, config):
    """Split data into train, validation, and test sets."""
    logger = get_run_logger()
    logger.info("✂️  Step 3: Data Splitting (before feature engineering — no leakage)")

    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y,
        test_size=config.model.test_size,
        random_state=config.model.random_state
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp,
        test_size=config.model.val_size,
        random_state=config.model.random_state
    )

    total = len(X)
    logger.info(f"   Train: {len(X_train):,} ({len(X_train)/total*100:.1f}%)")
    logger.info(f"   Val:   {len(X_val):,}   ({len(X_val)/total*100:.1f}%)")
    logger.info(f"   Test:  {len(X_test):,}  ({len(X_test)/total*100:.1f}%)")

    return X_train, X_val, X_test, y_train, y_val, y_test


# =============================================================================
# TASK 4 — Feature Engineering
#
# WHY @task:
#   The sklearn Pipeline is fitted on training data ONLY, then applied to
#   val and test. Making this a task ensures the fit+transform contract is
#   tracked — you can verify in the UI that this step always ran before training.
# =============================================================================
@task(name="engineer-features")
def engineer_features(X_train, X_val, X_test, config):
    """Fit feature pipeline on train, transform all sets."""
    logger = get_run_logger()
    logger.info("⚙️  Step 4: Feature Engineering")

    pipeline = build_preprocessor(iqr_factor=config.model.iqr_factor)

    # Fit on TRAINING data only — no leakage from val/test
    pipeline.fit(X_train)

    X_train_p = pipeline.transform(X_train)
    X_val_p   = pipeline.transform(X_val)
    X_test_p  = pipeline.transform(X_test)

    feature_names = pipeline.named_steps['feature_engineer'].get_feature_names()

    logger.info(f"✅ {len(feature_names)} engineered features")
    logger.info(f"   Train: {X_train_p.shape}, Val: {X_val_p.shape}, Test: {X_test_p.shape}")

    return X_train_p, X_val_p, X_test_p, feature_names, pipeline


# =============================================================================
# TASK 5a — Train a SINGLE model
#
# WHY individual @task per model (not one big @task that loops):
#   In pipline_no_perfect/, train_all_models() is a class method that runs all
#   5 models in a plain Python loop. If Random Forest fails, the entire loop
#   fails and all 5 models must restart.
#
#   With Prefect:
#   - Each model is a separate task run in the UI (5 rows, not 1 black box)
#   - retries=1 means ONLY the failed model retries — not all 5
#   - In the future, .submit() can make all 5 run in parallel (one line change)
#
# WHY this task is called from the FLOW (not from another @task):
#   Prefect's rule: tasks called from inside another task run as plain Python.
#   They lose state tracking, retries, and UI visibility.
#   Tasks must be called from the @flow to get full Prefect benefits.
#
# WHY retries=1, retry_delay_seconds=30:
#   Tree-based models (RF, GB) can hit memory/threading issues on first attempt.
#   One retry with a 30s gap handles transient resource contention.
# =============================================================================
@task(name="train-model", retries=1, retry_delay_seconds=30)
def train_single_model(model_name, model, X_train, y_train, X_val, y_val, config):
    """Train one model and log to MLflow. Called from flow — never from another task."""
    logger = get_run_logger()
    logger.info(f"🎯 Training: {model_name}")

    client = mlflow.MlflowClient()
    trainer = ModelTrainer(config.model, config.mlflow, client)

    metrics, trained_model, run_id = trainer.train_single_model(
        model, X_train, y_train, X_val, y_val, model_name
    )

    logger.info(f"   Val R²: {metrics['val_r2']:.4f} | MAE: {metrics['val_mae']:.2f} min | "
                f"Time: {metrics['training_time']:.1f}s")

    return {
        "model_name": model_name,
        "model": trained_model,
        "metrics": metrics,
        "run_id": run_id
    }


# =============================================================================
# TASK 5b — Select the best model from training results
#
# WHY separate @task:
#   Keeps selection logic isolated and visible. The UI shows the winner clearly
#   as a separate step after all individual model tasks complete.
# =============================================================================
@task(name="select-best-model")
def select_best_model(results: dict):
    """Pick the best model based on validation R²."""
    logger = get_run_logger()

    best_name = max(results, key=lambda k: results[k]["metrics"]["val_r2"])
    best = results[best_name]

    logger.info("📊 Model Comparison (Val R²):")
    for name, r in sorted(results.items(), key=lambda x: x[1]["metrics"]["val_r2"], reverse=True):
        marker = " ← BEST" if name == best_name else ""
        logger.info(f"   {name:<25} {r['metrics']['val_r2']:.4f}{marker}")

    logger.info(f"\n🏆 Best: {best_name} | Val R²: {best['metrics']['val_r2']:.4f}")
    return best


# =============================================================================
# TASK 6 — Hyperparameter Tuning (optional)
#
# WHY @task:
#   Tuning can be slow (minutes). Having it as a separate task means:
#   - It appears as its own step in the UI with its own timing
#   - If the pipeline is re-run without tuning, the UI shows it as "skipped"
#     (we return None and the flow handles it)
#   - Future: could add caching to skip tuning if params haven't changed
#
# WHY no retries:
#   HalvingRandomSearchCV is CPU-intensive but deterministic. A failure is a
#   real error (OOM, bad params), not a transient issue.
# =============================================================================
@task(name="tune-model")
def tune_model(best_result, X_train, y_train, X_val, y_val, config):
    """Tune the best model with HalvingRandomSearchCV."""
    logger = get_run_logger()

    model_name = best_result['model_name']
    tunable = config.model.tunable_models

    if model_name not in tunable:
        logger.info(f"⏭️  {model_name} is not tunable — skipping (tunable: {tunable})")
        return None

    logger.info(f"🔧 Step 6: Tuning {model_name}")

    original_score = best_result['metrics']['val_r2']

    # Use a fresh (unfitted) model for the search
    fresh_portfolio = build_model_portfolio(config.model)
    base_model = fresh_portfolio[model_name]

    client = mlflow.MlflowClient()
    trainer = ModelTrainer(config.model, config.mlflow, client)

    tuned_model, tuned_run_id, best_cv_score = trainer.tune_model(
        model_name, base_model, X_train, y_train, original_score
    )

    # Validate tuned model on the validation set
    y_val_pred = tuned_model.predict(X_val)
    tuned_val_r2 = r2_score(y_val, y_val_pred)

    improvement = tuned_val_r2 - original_score
    logger.info(f"   Original Val R²: {original_score:.4f}")
    logger.info(f"   Tuned Val R²:    {tuned_val_r2:.4f}")
    logger.info(f"   Improvement:     {improvement:+.4f}")

    if tuned_val_r2 > original_score:
        logger.info("✅ Tuned model is better — using tuned version")
        return {
            "model_name": model_name,
            "model": tuned_model,
            "run_id": tuned_run_id,
            "metrics": {**best_result["metrics"], "val_r2": tuned_val_r2}
        }
    else:
        logger.info("⚠️  Original model performs better — keeping original")
        return None


# =============================================================================
# TASK 7 — Test Set Evaluation
#
# WHY @task:
#   The test set is held out and evaluated ONCE. Making this a task enforces
#   that contract — you can see in the UI that it ran exactly once, after
#   all training and tuning completed.
# =============================================================================
@task(name="evaluate-model")
def evaluate_model(best_result, X_test, y_test, config):
    """Evaluate the final model on the held-out test set."""
    logger = get_run_logger()
    logger.info("🔬 Step 7: Test Set Evaluation")

    client = mlflow.MlflowClient()
    trainer = ModelTrainer(config.model, config.mlflow, client)

    test_metrics = trainer.evaluate_on_test(
        best_result['model'], X_test, y_test, best_result['run_id']
    )

    logger.info(f"   Test R²:  {test_metrics['test_r2']:.4f}")
    logger.info(f"   Test RMSE:{test_metrics['test_rmse']:.2f} min")
    logger.info(f"   Test MAE: {test_metrics['test_mae']:.2f} min")

    return test_metrics


# =============================================================================
# TASK 8 — Model Registry
#
# WHY @task with retries=2:
#   Registry transitions talk to the MLflow server (SQLite in this case, but
#   could be a remote server). If the server is temporarily unavailable,
#   retrying avoids failing an otherwise successful pipeline run.
# =============================================================================
@task(name="register-model", retries=2, retry_delay_seconds=5)
def register_model(best_result, test_metrics, promote_to_prod, config, preprocessor=None, train_stats=None):
    """Register the best model in MLflow and transition to Staging."""
    logger = get_run_logger()
    logger.info("📦 Step 8: Model Registry")

    registry = ModelRegistry(config.mlflow, mlflow.MlflowClient())

    description = (
        f"Best model: {best_result['model_name']} | "
        f"Test R²: {test_metrics['test_r2']:.4f} | "
        f"Test MAE: {test_metrics['test_mae']:.2f} min | "
        f"Orchestrated by Prefect"
    )
    tags = {
        'algorithm': best_result['model_name'],
        'test_r2': str(round(test_metrics['test_r2'], 4)),
        'test_mae': str(round(test_metrics['test_mae'], 4)),
        'data_leakage': 'none',
        'orchestrator': 'prefect',
        'data_source': 'tlc_direct',
        'schema_version': 'zone_ids'
    }

    version = registry.transition_to_staging(best_result['run_id'], description, tags)

    if version and promote_to_prod:
        registry.transition_to_production(version)
        logger.info(f"✅ Model v{version} → @champion")
    elif version:
        logger.info(f"✅ Model v{version} → @challenger (promote manually when ready)")
    else:
        logger.warning("⚠️  Could not register model — check MLflow connection")

    # Fix: test metrics are logged to best_result['run_id'] (may be the tuning run).
    # If the registered version lives on a different run (e.g. tuning didn't re-register),
    # re-log test metrics to the version's actual run so MLflow shows them on the model.
    if version:
        v_run_id = mlflow.MlflowClient().get_model_version(
            config.mlflow.model_name, version
        ).run_id
        if v_run_id != best_result.get('run_id'):
            with mlflow.start_run(run_id=v_run_id):
                mlflow.log_metrics({
                    'test_r2':   test_metrics['test_r2'],
                    'test_rmse': test_metrics['test_rmse'],
                    'test_mae':  test_metrics['test_mae'],
                })
                mlflow.set_tag('final_model', 'true')
                mlflow.set_tag('deployment_ready', 'true')
            logger.info(f"   ✓ Test metrics re-logged to v{version} run")

    # Save the fitted preprocessor so the API can load it at serving time
    if version and preprocessor is not None:
        import pickle, tempfile
        from pathlib import Path as _Path
        tmp = _Path(tempfile.mkdtemp())
        pkl = tmp / "preprocessor.pkl"
        with open(pkl, "wb") as f:
            pickle.dump(preprocessor, f)
        v_run_id = mlflow.MlflowClient().get_model_version(
            config.mlflow.model_name, version
        ).run_id
        with mlflow.start_run(run_id=v_run_id):
            mlflow.log_artifact(str(pkl), artifact_path="preprocessor")
        logger.info("✅ Preprocessor saved as MLflow artifact")

    # Save training target stats so batch scorer can compute drift without re-downloading 2019 data
    if version and train_stats is not None:
        v_run_id = mlflow.MlflowClient().get_model_version(
            config.mlflow.model_name, version
        ).run_id
        with mlflow.start_run(run_id=v_run_id):
            mlflow.log_metrics({
                'train_duration_mean': train_stats['mean'],
                'train_duration_std':  train_stats['std'],
            })
        logger.info(f"✅ Training stats saved — mean: {train_stats['mean']:.2f} min, std: {train_stats['std']:.2f} min")

    registry.print_registry_status()
    return version


# =============================================================================
# TASK 9 — Feature Importance Logging
#
# WHY @task:
#   Feature importance is a post-registration audit step, not part of training.
#   Keeping it separate makes it visible in the UI and easy to skip/re-run.
# =============================================================================
@task(name="log-feature-importance")
def log_feature_importance(best_result, feature_names, model_version, config):
    """Log tree model feature importances to the registered version's MLflow run."""
    logger = get_run_logger()

    model = best_result['model']
    if not hasattr(model, 'feature_importances_'):
        logger.info(f"⏭️  {best_result['model_name']} has no feature_importances_ — skipping")
        return

    if model_version is None:
        logger.warning("⚠️  No model version — skipping feature importance logging")
        return

    importances = model.feature_importances_
    importance_dict = dict(zip(feature_names, importances.tolist()))
    ranked = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)

    # Log to the registered version's run
    v_run_id = mlflow.MlflowClient().get_model_version(
        config.mlflow.model_name, model_version
    ).run_id

    with mlflow.start_run(run_id=v_run_id):
        mlflow.log_dict(importance_dict, 'feature_importance.json')
        for name, score in ranked[:10]:
            mlflow.log_metric(f'imp_{name}', score)

    logger.info(f"📊 Top 5 features ({best_result['model_name']}):")
    for name, score in ranked[:5]:
        logger.info(f"   {name:<30} {score:.4f}")


# =============================================================================
# FLOW — The main orchestrator
#
# WHY @flow (replaces NYCTaxiMLPipeline.run()):
#   In pipline_no_perfect/, NYCTaxiMLPipeline.run() calls each step as a
#   plain Python method. If step 5 fails, you get a Python traceback.
#   Nothing tells you what succeeded, what failed, or what the state was.
#
#   With @flow:
#   - Prefect creates a FlowRun in its database
#   - Every @task inside gets a TaskRun with state (Pending/Running/Completed/Failed)
#   - The Prefect UI shows the full DAG, timing, and logs for every run
#   - Flow parameters (sample_size, tune, promote_to_prod) appear in the UI
#     and can be edited for re-runs without touching code
#   - If a task fails, you re-run only that task from the UI (future: with caching)
#
# PARAMETERS visible in the Prefect UI:
#   sample_size     : how many rows to train on
#   tune            : whether to run hyperparameter tuning
#   promote_to_prod : whether to auto-promote the model to Production
#   experiment_name : override the MLflow experiment name
# =============================================================================
@flow(
    name="trip-duration-pipeline",
    description="Trip duration prediction — Prefect orchestrated",
    log_prints=True
)
def trip_duration_pipeline(
    sample_size: int = 200000,
    tune: bool = True,
    promote_to_prod: bool = False,
    experiment_name: Optional[str] = None,
    train_years: Optional[list] = None,
):
    """
    End-to-end ML pipeline for trip duration prediction.

    Steps:
      1. Acquire data     (retries=3)
      2. Preprocess data
      3. Split data       (before feature engineering — no leakage)
      4. Engineer features
      5. Train models     (each model is a separate task — retries=1 per model)
      6. Tune best model  (optional)
      7. Evaluate on test set
      8. Register in MLflow (retries=2)
    """
    logger = get_run_logger()

    # ── Load and apply config ─────────────────────────────────────────────────
    config = load_config()
    config.data.sample_size = sample_size
    if train_years:
        config.data.train_years = train_years
    total_months = len(config.data.train_years) * len(config.data.train_months)
    config.data.samples_per_month = sample_size // total_months
    if experiment_name:
        config.mlflow.experiment_name = experiment_name

    # ── Configure MLflow (done once in the flow, all tasks inherit it) ────────
    # WHY here and not in a task: MLflow tracking URI is process-global.
    # Setting it in the flow before any tasks ensures every task that calls
    # mlflow.start_run() uses the right experiment.
    mlflow.set_tracking_uri(config.mlflow.tracking_uri)

    # In Docker, MLFLOW_ARTIFACT_LOCATION points artifacts to the shared volume.
    # Locally this env var is unset and MLflow uses its default (./mlruns/).
    artifact_location = os.getenv("MLFLOW_ARTIFACT_LOCATION")
    if artifact_location:
        try:
            mlflow.create_experiment(config.mlflow.experiment_name, artifact_location=artifact_location)
        except Exception:
            pass  # experiment already exists
    mlflow.set_experiment(config.mlflow.experiment_name)

    logger.info("=" * 60)
    logger.info("TRIP DURATION PIPELINE — PREFECT ORCHESTRATED")
    logger.info(f"  train_years    : {config.data.train_years}")
    logger.info(f"  sample_size    : {sample_size:,}")
    logger.info(f"  tune           : {tune}")
    logger.info(f"  promote_to_prod: {promote_to_prod}")
    logger.info(f"  experiment     : {config.mlflow.experiment_name}")
    logger.info("=" * 60)

    # ── Step 1: Data Acquisition ───────────────────────────────────────────────
    df_raw = acquire_data(config)

    # ── Step 2: Preprocessing ─────────────────────────────────────────────────
    X, y = preprocess_data(df_raw, config)

    # ── Step 3: Split ─────────────────────────────────────────────────────────
    X_train, X_val, X_test, y_train, y_val, y_test = split_data(X, y, config)

    # ── Step 4: Feature Engineering ───────────────────────────────────────────
    X_train_p, X_val_p, X_test_p, feature_names, pipeline = engineer_features(
        X_train, X_val, X_test, config
    )

    # ── Step 5: Train each model as a SEPARATE TASK from the flow ─────────────
    # KEY PATTERN: the loop is in the FLOW, not inside a task.
    # This gives each model its own TaskRun in the Prefect UI.
    # In the future, replace the direct call with .submit() for parallelism:
    #   future = train_single_model.submit(name, model, ...)
    model_portfolio = build_model_portfolio(config.model)
    training_results = {}

    for model_name, model in model_portfolio.items():
        result = train_single_model(
            model_name, model,
            X_train_p, y_train,
            X_val_p, y_val,
            config
        )
        training_results[model_name] = result

    best_result = select_best_model(training_results)

    # ── Step 6: Hyperparameter Tuning (optional) ──────────────────────────────
    if tune:
        tuned = tune_model(best_result, X_train_p, y_train, X_val_p, y_val, config)
        if tuned is not None:
            best_result = tuned
    else:
        logger.info("⏭️  Step 6: Tuning skipped (--no-tune)")

    # ── Step 7: Evaluate on test set ──────────────────────────────────────────
    test_metrics = evaluate_model(best_result, X_test_p, y_test, config)

    # ── Step 8: Register in MLflow ────────────────────────────────────────────
    train_stats = {'mean': float(np.mean(y_train)), 'std': float(np.std(y_train))}
    model_version = register_model(best_result, test_metrics, promote_to_prod, config, pipeline, train_stats)

    # ── Step 9: Feature importance ────────────────────────────────────────────
    log_feature_importance(best_result, feature_names, model_version, config)

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Best model   : {best_result['model_name']}")
    logger.info(f"  Test R²      : {test_metrics['test_r2']:.4f}")
    logger.info(f"  Test MAE     : {test_metrics['test_mae']:.2f} min")
    logger.info(f"  Model version: {model_version}")
    logger.info(f"  Alias        : {'@champion' if promote_to_prod else '@challenger'}")
    logger.info(f"\n  Load model:")
    alias = 'champion' if promote_to_prod else 'challenger'
    logger.info(f"  mlflow.sklearn.load_model('models:/{config.mlflow.model_name}@{alias}')")
    logger.info("=" * 60)

    return {
        "model_name": best_result['model_name'],
        "run_id": best_result['run_id'],
        "model_version": model_version,
        "test_r2": test_metrics['test_r2'],
        "test_mae": test_metrics['test_mae'],
        "status": "success"
    }
