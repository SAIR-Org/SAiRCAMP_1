"""
Batch scoring flow — two outputs from one run:

  1. predictions/YYYY_MM.parquet  — per-trip predictions (batch deployment)
     All scored trips with predicted and actual duration.
     Use for: analytics, route analysis, what-if, A/B testing.

  2. batch_results.db             — aggregate metrics per period (drift engine)
     MAE, volume, drift ratio, alert flag.
     Use for: monitoring, drift chart, alert system.

Default periods tell the drift story:
  2020-04: COVID lockdown — 97% volume collapse, MAE 1.81x → ALERT
  2022-01: new normal    — model recovers,        MAE 0.97x → OK
  2024-01: fares +45%   — model stable,           MAE 1.02x → OK
"""
import os
import sys
import sqlite3
import pickle
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
from sklearn.metrics import mean_absolute_error
import mlflow
from mlflow import MlflowClient
from prefect import flow, task, get_run_logger


# ── Path setup ────────────────────────────────────────────────────────────────
_BATCH_DIR    = Path(__file__).parent
_ONLINE_DIR   = _BATCH_DIR.parent.parent / "4-Deploy-Online"
_PIPELINE_DIR = _ONLINE_DIR / "pipeline"

# shared/ must be importable so the preprocessor pickle loads correctly
sys.path.insert(0, str(_ONLINE_DIR))    # shared.feature_engineering
sys.path.insert(0, str(_PIPELINE_DIR))  # src.features re-export (old pickles)

# ── Config ────────────────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{_PIPELINE_DIR / 'mlflow_trip_duration.db'}",
)
MODEL_NAME  = "trip_duration_model"
MODEL_ALIAS = "champion"

DB_PATH          = _BATCH_DIR / "batch_results.db"
PREDICTIONS_DIR  = _BATCH_DIR / "predictions"

TLC_URL = (
    "https://d37ci6vzurychx.cloudfront.net/trip-data/"
    "yellow_tripdata_{year}-{month:02d}.parquet"
)
COLS = [
    "tpep_pickup_datetime", "tpep_dropoff_datetime",
    "PULocationID", "DOLocationID",
    "passenger_count", "trip_distance",
    "VendorID", "RatecodeID", "payment_type",
]
FEATURE_COLS = [
    "tpep_pickup_datetime", "PULocationID", "DOLocationID",
    "passenger_count", "trip_distance", "VendorID", "RatecodeID", "payment_type",
]

# Alert thresholds (validated in batch_exploration.ipynb)
MAE_RATIO_THRESHOLD = 1.5      # MAE > 1.5x training MAE → model degraded
VOLUME_THRESHOLD    = 500_000  # < 500k trips/month     → volume collapse


# ── Database ──────────────────────────────────────────────────────────────────
def _init_db():
    PREDICTIONS_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS batch_results (
            year         INTEGER,
            month        INTEGER,
            scored_at    TEXT,
            total_rows   INTEGER,
            mae          REAL,
            mae_ratio    REAL,
            target_mean  REAL,
            dist_mean    REAL,
            alert        INTEGER,
            predictions_path TEXT,
            PRIMARY KEY (year, month)
        )
    """)
    conn.commit()
    conn.close()


# ── Tasks ─────────────────────────────────────────────────────────────────────
@task(name="load-champion", retries=2, retry_delay_seconds=10)
def load_champion() -> dict:
    """Load @champion model, preprocessor, and training baseline from MLflow."""
    logger = get_run_logger()
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    mv = client.get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)
    logger.info(f"Champion: v{mv.version}  run: {mv.run_id[:8]}")

    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")
    logger.info(f"Model: {type(model).__name__}")

    dst = tempfile.mkdtemp()
    art_path = mlflow.artifacts.download_artifacts(
        run_id=mv.run_id,
        artifact_path="preprocessor/preprocessor.pkl",
        dst_path=dst,
    )
    with open(art_path, "rb") as f:
        preprocessor = pickle.load(f)
    logger.info("Preprocessor loaded")

    run        = client.get_run(mv.run_id)
    train_mae  = float(run.data.metrics["test_mae"])
    train_mean = float(run.data.metrics["train_duration_mean"])
    logger.info(f"Baseline — test MAE: {train_mae:.2f} min  "
                f"duration mean: {train_mean:.2f} min")
    logger.info(f"Alert if MAE > {train_mae * MAE_RATIO_THRESHOLD:.2f} min "
                f"or volume < {VOLUME_THRESHOLD:,}")

    return {
        "model":        model,
        "preprocessor": preprocessor,
        "train_mae":    train_mae,
        "train_mean":   train_mean,
        "version":      mv.version,
        "run_id":       mv.run_id,
    }


@task(name="score-month", retries=1, retry_delay_seconds=30)
def score_month(year: int, month: int, champion: dict) -> dict:
    """
    Download ALL trips for a month, score every one, save predictions.

    Output 1 (batch deployment):
        predictions/YYYY_MM.parquet — per-trip predictions for analytics

    Output 2 (drift engine):
        Returns aggregate metrics dict → written to batch_results.db
    """
    logger = get_run_logger()
    logger.info(f"Downloading {year}-{month:02d}...")

    url = TLC_URL.format(year=year, month=month)
    df  = pd.read_parquet(url, columns=COLS)
    df  = df.dropna(subset=COLS)
    df["tpep_pickup_datetime"]  = pd.to_datetime(df["tpep_pickup_datetime"])
    df["tpep_dropoff_datetime"] = pd.to_datetime(df["tpep_dropoff_datetime"])
    df["trip_duration_minutes"] = (
        df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]
    ).dt.total_seconds() / 60
    df = df[(df["trip_duration_minutes"] >= 1)  & (df["trip_duration_minutes"] <= 120)]
    df = df[(df["trip_distance"]         >  0.1) & (df["trip_distance"]         <= 50)]
    df = df[(df["passenger_count"]       >= 1)  & (df["passenger_count"]        <= 6)]

    total_rows = len(df)
    logger.info(f"  {total_rows:,} valid trips — scoring all of them")

    # ── Score ALL trips (batch deployment) ────────────────────────────────────
    X      = champion["preprocessor"].transform(df[FEATURE_COLS].copy())
    y_pred = champion["model"].predict(X)

    # ── Build predictions DataFrame ───────────────────────────────────────────
    predictions = pd.DataFrame({
        "pickup_datetime":         df["tpep_pickup_datetime"].values,
        "PULocationID":            df["PULocationID"].values,
        "DOLocationID":            df["DOLocationID"].values,
        "trip_distance":           df["trip_distance"].values,
        "actual_duration_minutes": df["trip_duration_minutes"].values,
        "predicted_duration_minutes": y_pred,
        "error_minutes":           y_pred - df["trip_duration_minutes"].values,
        "model_version":           champion["version"],
    })

    # ── Save predictions → Parquet (batch deployment artifact) ────────────────
    parquet_path = PREDICTIONS_DIR / f"{year}_{month:02d}.parquet"
    predictions.to_parquet(parquet_path, index=False)
    logger.info(f"  Predictions saved → {parquet_path.name}  "
                f"({parquet_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # ── Aggregate metrics (drift engine) ──────────────────────────────────────
    y_true    = df["trip_duration_minutes"].values
    mae       = float(mean_absolute_error(y_true, y_pred))
    mae_ratio = mae / champion["train_mae"]
    target_mean = float(y_true.mean())
    dist_mean   = float(df["trip_distance"].mean())

    mae_alert    = mae_ratio  > MAE_RATIO_THRESHOLD
    volume_alert = total_rows < VOLUME_THRESHOLD
    alert        = mae_alert or volume_alert

    reasons = []
    if mae_alert:    reasons.append(f"MAE {mae_ratio:.1f}x training")
    if volume_alert: reasons.append(f"volume collapse ({total_rows:,} trips)")
    status = f"⚠️  ALERT: {', '.join(reasons)}" if alert else "✅ OK"

    logger.info(f"  MAE:           {mae:.2f} min  (ratio={mae_ratio:.2f}x)")
    logger.info(f"  Duration mean: {target_mean:.2f} min  "
                f"(train: {champion['train_mean']:.2f})")
    logger.info(f"  {status}")

    return {
        "year": year, "month": month,
        "scored_at":        datetime.utcnow().isoformat(),
        "total_rows":       total_rows,
        "mae":              mae,
        "mae_ratio":        mae_ratio,
        "target_mean":      target_mean,
        "dist_mean":        dist_mean,
        "alert":            int(alert),
        "predictions_path": str(parquet_path),
    }


@task(name="save-result")
def save_result(result: dict, champion: dict):
    """Write aggregate metrics to SQLite and log to MLflow."""
    logger = get_run_logger()

    # ── SQLite (monitoring reads this) ────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO batch_results
        (year, month, scored_at, total_rows, mae, mae_ratio,
         target_mean, dist_mean, alert, predictions_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result["year"],         result["month"],
        result["scored_at"],    result["total_rows"],
        result["mae"],          result["mae_ratio"],
        result["target_mean"],  result["dist_mean"],
        result["alert"],        result["predictions_path"],
    ))
    conn.commit()
    conn.close()
    logger.info(f"Metrics saved → batch_results.db")

    # ── MLflow (experiment tracking) ──────────────────────────────────────────
    with mlflow.start_run(run_name=f"batch_{result['year']}_{result['month']:02d}"):
        mlflow.set_tag("type", "batch_score")
        mlflow.set_tag("model_version", str(champion["version"]))
        mlflow.log_params({"year": result["year"], "month": result["month"]})
        mlflow.log_metrics({
            "mae":         result["mae"],
            "mae_ratio":   result["mae_ratio"],
            "target_mean": result["target_mean"],
            "dist_mean":   result["dist_mean"],
            "total_rows":  float(result["total_rows"]),
            "alert":       float(result["alert"]),
        })
        mlflow.log_artifact(result["predictions_path"], artifact_path="predictions")


# ── Flow ──────────────────────────────────────────────────────────────────────
@flow(name="batch-score", log_prints=True)
def batch_score_flow(
    periods: Optional[list] = None,
    experiment_name: str = "batch_scoring",
):
    """
    Batch scoring flow — two outputs per period:

    predictions/YYYY_MM.parquet   per-trip predictions (batch deployment)
    batch_results.db              aggregate drift metrics (monitoring)

    Default periods:
      (2020, 4) — COVID: MAE 1.81x, volume 204k  → ALERT
      (2022, 1) — normal: MAE 0.97x, volume 2.3M → OK
      (2024, 1) — stable: MAE 1.02x, volume 2.7M → OK
    """
    logger = get_run_logger()

    if periods is None:
        periods = [(2020, 4), (2022, 1), (2024, 1)]

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experiment_name)
    _init_db()

    logger.info("=" * 55)
    logger.info("BATCH SCORING — NYC TAXI TRIP DURATION")
    logger.info(f"  Periods:  {periods}")
    logger.info(f"  DB:       {DB_PATH.name}")
    logger.info(f"  Output:   predictions/ (parquet) + batch_results.db")
    logger.info("=" * 55)

    champion = load_champion()

    results = []
    for year, month in periods:
        result = score_month(year, month, champion)
        save_result(result, champion)
        results.append(result)

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 55)
    logger.info("SUMMARY")
    logger.info("=" * 55)
    for r in results:
        flag = "⚠️ " if r["alert"] else "✅"
        logger.info(
            f"  {flag} {r['year']}-{r['month']:02d}  "
            f"MAE={r['mae']:.2f}  ratio={r['mae_ratio']:.2f}x  "
            f"vol={r['total_rows']:,}"
        )
    alerts = sum(r["alert"] for r in results)
    logger.info(f"\n  {alerts}/{len(results)} periods triggered alerts")
    logger.info(f"  Predictions: {PREDICTIONS_DIR}/")
    logger.info(f"  Metrics:     {DB_PATH.name}")

    return results
