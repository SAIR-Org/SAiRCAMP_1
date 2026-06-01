"""
Retrain flow — champion/challenger retraining.

Story:
  1. Monitoring detected 2020-04 alert (MAE 1.81x, volume collapsed)
  2. We retrain on 2019 + 2020 data → registers as @challenger
  3. Evaluate champion vs challenger on a neutral 2020 holdout (2020-06)
  4. If challenger wins → promote to @champion
  5. If champion wins  → keep current champion, log the result

The gate (step 4 vs 5) prevents silent degradation:
  auto-retraining without comparison can silently make things worse.
"""
import os
import sys
import pickle
import tempfile
from pathlib import Path
from typing import Optional

import importlib.util

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
import mlflow
from mlflow import MlflowClient
from prefect import flow, task, get_run_logger


# ── Path setup ────────────────────────────────────────────────────────────────
_RETRAIN_DIR  = Path(__file__).parent
_OFFLINE_DIR  = _RETRAIN_DIR.parent
_ONLINE_DIR   = _OFFLINE_DIR.parent / "4-Deploy-Online"
_PIPELINE_DIR = _ONLINE_DIR / "pipeline"

sys.path.insert(0, str(_ONLINE_DIR))    # shared.feature_engineering
sys.path.insert(0, str(_PIPELINE_DIR))  # pipeline imports (flow, config, src)

# Import pipeline flow by path — avoids name conflict with retrain/flow.py
_spec = importlib.util.spec_from_file_location(
    "pipeline_flow", str(_PIPELINE_DIR / "flow.py")
)
_pipeline_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pipeline_module)
_trip_duration_pipeline = _pipeline_module.trip_duration_pipeline

# ── Config ────────────────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{_PIPELINE_DIR / 'mlflow_trip_duration.db'}",
)
MODEL_NAME = "trip_duration_model"

TLC_URL = (
    "https://d37ci6vzurychx.cloudfront.net/trip-data/"
    "yellow_tripdata_{year}-{month:02d}.parquet"
)
EVAL_COLS = [
    "tpep_pickup_datetime", "tpep_dropoff_datetime",
    "PULocationID", "DOLocationID",
    "passenger_count", "trip_distance",
    "VendorID", "RatecodeID", "payment_type",
]
FEATURE_COLS = [
    "tpep_pickup_datetime", "PULocationID", "DOLocationID",
    "passenger_count", "trip_distance", "VendorID", "RatecodeID", "payment_type",
]


# ── Tasks ─────────────────────────────────────────────────────────────────────
@task(name="train-challenger", retries=1, retry_delay_seconds=30)
def train_challenger(
    train_years: list,
    sample_size: int,
    experiment_name: str,
) -> str:
    """
    Run the training pipeline on expanded data → registers @challenger.
    Returns the challenger model version number.
    """
    logger = get_run_logger()
    logger.info(f"Training challenger on years: {train_years}")
    logger.info(f"Sample size: {sample_size:,}")

    result = _trip_duration_pipeline(
        sample_size=sample_size,
        tune=False,             # skip tuning — retraining is about data, not hyperparams
        promote_to_prod=False,  # register as @challenger, not @champion
        experiment_name=experiment_name,
        train_years=train_years,
    )

    logger.info(f"Challenger registered: v{result['model_version']} @challenger")
    logger.info(f"  Test R²: {result['test_r2']:.4f}")
    logger.info(f"  Test MAE: {result['test_mae']:.2f} min")
    return result["model_version"]


@task(name="load-model-for-eval")
def load_model_for_eval(alias: str) -> dict:
    """Load model + preprocessor from MLflow by alias."""
    logger = get_run_logger()
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    mv = client.get_model_version_by_alias(MODEL_NAME, alias)
    logger.info(f"Loading @{alias}: v{mv.version}  run: {mv.run_id[:8]}")

    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{alias}")

    dst = tempfile.mkdtemp()
    art_path = mlflow.artifacts.download_artifacts(
        run_id=mv.run_id,
        artifact_path="preprocessor/preprocessor.pkl",
        dst_path=dst,
    )
    with open(art_path, "rb") as f:
        preprocessor = pickle.load(f)

    return {"model": model, "preprocessor": preprocessor, "version": mv.version, "alias": alias}


@task(name="evaluate-on-holdout", retries=1, retry_delay_seconds=10)
def evaluate_on_holdout(model_info: dict, eval_year: int, eval_month: int) -> dict:
    """
    Evaluate a model on a neutral holdout period.
    Holdout = 2020-06: never in training, still COVID period → fair comparison.
    """
    logger = get_run_logger()
    logger.info(f"Evaluating v{model_info['version']} @{model_info['alias']} "
                f"on {eval_year}-{eval_month:02d} holdout...")

    url = TLC_URL.format(year=eval_year, month=eval_month)
    df  = pd.read_parquet(url, columns=EVAL_COLS)
    df  = df.dropna(subset=EVAL_COLS)
    df["tpep_pickup_datetime"]  = pd.to_datetime(df["tpep_pickup_datetime"])
    df["tpep_dropoff_datetime"] = pd.to_datetime(df["tpep_dropoff_datetime"])
    df["trip_duration_minutes"] = (
        df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]
    ).dt.total_seconds() / 60
    df = df[(df["trip_duration_minutes"] >= 1)  & (df["trip_duration_minutes"] <= 120)]
    df = df[(df["trip_distance"]         >  0.1) & (df["trip_distance"]         <= 50)]
    df = df[(df["passenger_count"]       >= 1)  & (df["passenger_count"]        <= 6)]

    # Sample for speed (holdout evaluation — no need for full dataset)
    if len(df) > 50_000:
        df = df.sample(50_000, random_state=42)

    X      = model_info["preprocessor"].transform(df[FEATURE_COLS].copy())
    y_pred = model_info["model"].predict(X)
    y_true = df["trip_duration_minutes"].values

    mae = float(mean_absolute_error(y_true, y_pred))
    logger.info(f"  MAE on {eval_year}-{eval_month:02d}: {mae:.2f} min")

    return {
        "version": model_info["version"],
        "alias":   model_info["alias"],
        "mae":     mae,
        "n_rows":  len(df),
    }


@task(name="compare-and-promote", retries=2, retry_delay_seconds=5)
def compare_and_promote(
    champion_eval: dict,
    challenger_eval: dict,
    min_improvement: float,
) -> bool:
    """
    Promote challenger to @champion only if it beats champion by min_improvement.
    Returns True if promoted, False if champion retained.
    """
    logger = get_run_logger()
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    champ_mae = champion_eval["mae"]
    chal_mae  = challenger_eval["mae"]
    diff      = champ_mae - chal_mae

    logger.info("=" * 50)
    logger.info("CHAMPION vs CHALLENGER")
    logger.info("=" * 50)
    logger.info(f"  Champion  v{champion_eval['version']}: MAE = {champ_mae:.2f} min")
    logger.info(f"  Challenger v{challenger_eval['version']}: MAE = {chal_mae:.2f} min")
    logger.info(f"  Difference: {diff:+.2f} min  (threshold: {min_improvement:.2f})")

    if diff > min_improvement:
        # Challenger wins — promote
        client.set_registered_model_alias(
            MODEL_NAME, "champion", str(challenger_eval["version"])
        )
        logger.info(f"\n  ✅ PROMOTED: v{challenger_eval['version']} → @champion")
        logger.info(f"     Improvement: {diff:.2f} min better on 2020 holdout")
        return True
    else:
        logger.info(f"\n  ✅ CHAMPION RETAINED: v{champion_eval['version']} @champion")
        logger.info(f"     Challenger did not improve by {min_improvement:.2f} min")
        return False


# ── Flow ──────────────────────────────────────────────────────────────────────
@flow(name="retrain", log_prints=True)
def retrain_flow(
    train_years: Optional[list] = None,
    sample_size: int = 200_000,
    eval_year: int = 2020,
    eval_month: int = 6,
    min_improvement: float = 0.1,
    experiment_name: str = "trip_duration_v2",
):
    """
    Champion/challenger retraining flow.

    Trains a new model on expanded data, evaluates both models on a neutral
    holdout, and promotes only if the challenger genuinely improves.

    Args:
        train_years:     years to train on (default: [2019, 2020])
        sample_size:     rows per training run (default: 200k — faster than 500k)
        eval_year:       holdout year for comparison (default: 2020)
        eval_month:      holdout month (default: 6 — not in training months)
        min_improvement: min MAE improvement in minutes to trigger promotion
        experiment_name: MLflow experiment to log to
    """
    logger = get_run_logger()

    if train_years is None:
        train_years = [2019, 2020]

    logger.info("=" * 55)
    logger.info("RETRAIN FLOW — NYC TAXI TRIP DURATION")
    logger.info(f"  Train years:     {train_years}")
    logger.info(f"  Sample size:     {sample_size:,}")
    logger.info(f"  Eval holdout:    {eval_year}-{eval_month:02d}")
    logger.info(f"  Min improvement: {min_improvement} min")
    logger.info("=" * 55)

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    # Step 1 — Train challenger
    train_challenger(train_years, sample_size, experiment_name)

    # Step 2 — Load both models
    champion   = load_model_for_eval("champion")
    challenger = load_model_for_eval("challenger")

    # Step 3 — Evaluate on neutral holdout
    champion_eval   = evaluate_on_holdout(champion,   eval_year, eval_month)
    challenger_eval = evaluate_on_holdout(challenger, eval_year, eval_month)

    # Step 4 — Compare and promote
    promoted = compare_and_promote(champion_eval, challenger_eval, min_improvement)

    logger.info("")
    logger.info("=" * 55)
    logger.info("RETRAIN COMPLETE")
    logger.info("=" * 55)
    logger.info(f"  Champion MAE  (2020-06): {champion_eval['mae']:.2f} min")
    logger.info(f"  Challenger MAE (2020-06): {challenger_eval['mae']:.2f} min")
    logger.info(f"  Promoted: {promoted}")

    return {
        "promoted":        promoted,
        "champion_mae":    champion_eval["mae"],
        "challenger_mae":  challenger_eval["mae"],
        "champion_version":    champion_eval["version"],
        "challenger_version":  challenger_eval["version"],
    }
