"""
Core batch scoring logic with Evidently drift detection.
"""
from __future__ import annotations

import json
import logging
import os
import pickle
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sklearn.metrics import mean_absolute_error
import mlflow
from mlflow import MlflowClient

from evidently import Report
from evidently.presets import DataDriftPreset
from evidently.metrics import DriftedColumnsCount

logger = logging.getLogger(__name__)

# ── Path setup ────────────────────────────────────────────────────────────────
_CORE_DIR = Path(__file__).parent
_MODULE_DIR = _CORE_DIR.parent
_PIPELINE_DIR = _MODULE_DIR / "pipeline"

sys.path.insert(0, str(_MODULE_DIR))
sys.path.insert(0, str(_PIPELINE_DIR))

# ── Config ────────────────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{_PIPELINE_DIR / 'mlflow_trip_duration.db'}",
)
MODEL_NAME = "trip_duration_model"
MODEL_ALIAS = "champion"

DATA_DIR = Path(os.getenv("BATCH_DATA_DIR", str(_CORE_DIR)))
DB_PATH = DATA_DIR / "batch_results.db"
PREDICTIONS_DIR = DATA_DIR / "predictions"
DRIFT_REPORTS_DIR = DATA_DIR / "drift_reports"

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
DRIFT_FEATURE_COLS = [
    "PULocationID", "DOLocationID", "trip_distance",
    "passenger_count", "VendorID", "RatecodeID",
]

MAE_RATIO_THRESHOLD = 1.5
VOLUME_THRESHOLD = 500_000
DRIFT_SHARE_THRESHOLD = 0.5

_ARTIFACTS_ROOT = os.getenv("MLFLOW_ARTIFACTS_ROOT")


def _remap(path: str) -> str:
    if not _ARTIFACTS_ROOT or not path:
        return path
    idx = path.find("/mlruns/")
    return _ARTIFACTS_ROOT + path[idx:] if idx >= 0 else path


def _get_storage_location(version: str) -> Optional[str]:
    db_path = MLFLOW_TRACKING_URI.replace("sqlite:///", "")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT storage_location FROM model_versions WHERE name=? AND version=?",
            (MODEL_NAME, version),
        ).fetchone()
    return row[0] if row else None


def _get_artifact_uri(run_id: str) -> Optional[str]:
    db_path = MLFLOW_TRACKING_URI.replace("sqlite:///", "")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT artifact_uri FROM runs WHERE run_uuid=?", (run_id,)
        ).fetchone()
    return row[0] if row else None


# ── Database ──────────────────────────────────────────────────────────────────
def init_db() -> None:
    """Initialize database with schema migration."""
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    DRIFT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        # Create table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_results (
                year              INTEGER,
                month             INTEGER,
                scored_at         TEXT,
                total_rows        INTEGER,
                mae               REAL,
                mae_ratio         REAL,
                target_mean       REAL,
                dist_mean         REAL,
                alert             INTEGER,
                predictions_path  TEXT,
                PRIMARY KEY (year, month)
            )
        """)
        
        # Add new columns if they don't exist
        columns_to_add = [
            ("drift_score", "REAL"),
            ("drift_detected", "INTEGER"),
            ("drift_report_html", "TEXT"),
            ("drift_report_json", "TEXT"),
        ]
        
        # Get existing columns
        cursor = conn.execute("PRAGMA table_info(batch_results)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        
        for col_name, col_type in columns_to_add:
            if col_name not in existing_cols:
                try:
                    conn.execute(f"ALTER TABLE batch_results ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column: {col_name}")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not add column {col_name}: {e}")
        
        conn.commit()


# ── Model loading ─────────────────────────────────────────────────────────────
def load_champion() -> dict:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()
    mv = client.get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)

    if _ARTIFACTS_ROOT and mv.source:
        model = mlflow.sklearn.load_model(_remap(_get_storage_location(mv.version)))
        preprocessor_path = (
            Path(_remap(_get_artifact_uri(mv.run_id))) / "preprocessor" / "preprocessor.pkl"
        )
        with open(preprocessor_path, "rb") as f:
            preprocessor = pickle.load(f)
    else:
        model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")
        with tempfile.TemporaryDirectory() as dst:
            art_path = mlflow.artifacts.download_artifacts(
                run_id=mv.run_id,
                artifact_path="preprocessor/preprocessor.pkl",
                dst_path=dst,
            )
            with open(art_path, "rb") as f:
                preprocessor = pickle.load(f)

    run = client.get_run(mv.run_id)
    return {
        "model": model,
        "preprocessor": preprocessor,
        "train_mae": float(run.data.metrics["test_mae"]),
        "train_mean": float(run.data.metrics["train_duration_mean"]),
        "version": mv.version,
        "run_id": mv.run_id,
    }


# ── Reference data ────────────────────────────────────────────────────────────
def load_reference_data() -> pd.DataFrame:
    """Load the reference baseline (2019-01) for drift detection."""
    url = TLC_URL.format(year=2019, month=1)
    df = pd.read_parquet(url, columns=COLS)
    df = df.dropna(subset=COLS)
    return df[DRIFT_FEATURE_COLS].copy()


# ── Drift detection ───────────────────────────────────────────────────────────
def run_drift_report(current: pd.DataFrame, reference: pd.DataFrame, year: int, month: int) -> dict:
    """Run Evidently drift report and save results."""
    DRIFT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path = DRIFT_REPORTS_DIR / f"drift_{year}_{month:02d}.html"
    json_path = DRIFT_REPORTS_DIR / f"drift_{year}_{month:02d}.json"

    result = {
        "drift_score": 0.0,
        "drift_detected": 0,
        "drift_report_html": None,
        "drift_report_json": None,
    }

    try:
        report = Report([
            DataDriftPreset(drift_share=DRIFT_SHARE_THRESHOLD),
            DriftedColumnsCount(drift_share=DRIFT_SHARE_THRESHOLD),
        ])
        eval_result = report.run(current_data=current, reference_data=reference)
        eval_dict = eval_result.dict()

        # Extract drift metrics
        for metric in eval_dict.get("metrics", []):
            if metric.get("metric_name", "").startswith("DriftedColumnsCount"):
                value = metric.get("value", {})
                if isinstance(value, dict):
                    result["drift_score"] = float(value.get("share", 0.0) or 0.0)
                    result["drift_detected"] = 1 if result["drift_score"] >= DRIFT_SHARE_THRESHOLD else 0
                break

        # Save reports
        eval_result.save_html(str(html_path))
        result["drift_report_html"] = str(html_path)

        with open(json_path, "w") as f:
            json.dump(eval_dict, f, indent=2, default=str)
        result["drift_report_json"] = str(json_path)

        logger.info("Drift %s-%02d: score=%.3f detected=%s", year, month,
                    result["drift_score"], bool(result["drift_detected"]))

    except Exception as e:
        logger.warning("Drift failed for %s-%02d: %s", year, month, e)

    return result


# ── Core scoring ──────────────────────────────────────────────────────────────
def score_month(year: int, month: int, champion: dict) -> dict:
    url = TLC_URL.format(year=year, month=month)
    df = pd.read_parquet(url, columns=COLS)
    df = df.dropna(subset=COLS)
    df["tpep_pickup_datetime"] = pd.to_datetime(df["tpep_pickup_datetime"])
    df["tpep_dropoff_datetime"] = pd.to_datetime(df["tpep_dropoff_datetime"])
    df["trip_duration_minutes"] = (
        df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]
    ).dt.total_seconds() / 60

    # Filter outliers
    df = df[
        (df["trip_duration_minutes"] >= 1) & (df["trip_duration_minutes"] <= 120) &
        (df["trip_distance"] > 0.1) & (df["trip_distance"] <= 50) &
        (df["passenger_count"] >= 1) & (df["passenger_count"] <= 6)
    ]

    total_rows = len(df)
    X = champion["preprocessor"].transform(df[FEATURE_COLS].copy())
    y_pred = champion["model"].predict(X)
    y_true = df["trip_duration_minutes"].values

    # Save predictions
    parquet_path = PREDICTIONS_DIR / f"{year}_{month:02d}.parquet"
    pd.DataFrame({
        "pickup_datetime": df["tpep_pickup_datetime"].values,
        "PULocationID": df["PULocationID"].values,
        "DOLocationID": df["DOLocationID"].values,
        "trip_distance": df["trip_distance"].values,
        "actual_duration_minutes": y_true,
        "predicted_duration_minutes": y_pred,
        "error_minutes": y_pred - y_true,
        "model_version": champion["version"],
    }).to_parquet(parquet_path, index=False)

    # Compute metrics
    mae = float(mean_absolute_error(y_true, y_pred))
    mae_ratio = mae / champion["train_mae"]
    target_mean = float(y_true.mean())
    dist_mean = float(df["trip_distance"].mean())
    alert = int((mae_ratio > MAE_RATIO_THRESHOLD) or (total_rows < VOLUME_THRESHOLD))

    # Run drift detection
    try:
        reference = load_reference_data()
        current_features = df[DRIFT_FEATURE_COLS].copy()
        drift = run_drift_report(current_features, reference, year, month)
    except Exception as e:
        logger.warning("Could not run drift for %s-%02d: %s", year, month, e)
        drift = {"drift_score": 0.0, "drift_detected": 0,
                 "drift_report_html": None, "drift_report_json": None}

    return {
        "year": year,
        "month": month,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "total_rows": total_rows,
        "mae": mae,
        "mae_ratio": mae_ratio,
        "target_mean": target_mean,
        "dist_mean": dist_mean,
        "alert": alert,
        "predictions_path": str(parquet_path),
        **drift,
    }


def save_result(result: dict, champion: dict) -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    # Ensure schema is up to date before inserting
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO batch_results
            (year, month, scored_at, total_rows, mae, mae_ratio,
             target_mean, dist_mean, alert, predictions_path,
             drift_score, drift_detected, drift_report_html, drift_report_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result["year"], result["month"],
            result["scored_at"], result["total_rows"],
            result["mae"], result["mae_ratio"],
            result["target_mean"], result["dist_mean"],
            result["alert"], result["predictions_path"],
            result.get("drift_score", 0.0),
            result.get("drift_detected", 0),
            result.get("drift_report_html"),
            result.get("drift_report_json"),
        ))
        conn.commit()

    with mlflow.start_run(run_name=f"batch_{result['year']}_{result['month']:02d}"):
        mlflow.set_tag("type", "batch_score")
        mlflow.set_tag("model_version", str(champion["version"]))
        mlflow.log_params({"year": result["year"], "month": result["month"]})
        mlflow.log_metrics({
            "mae": result["mae"],
            "mae_ratio": result["mae_ratio"],
            "target_mean": result["target_mean"],
            "dist_mean": result["dist_mean"],
            "total_rows": float(result["total_rows"]),
            "alert": float(result["alert"]),
            "drift_score": result.get("drift_score", 0.0),
            "drift_detected": float(result.get("drift_detected", 0)),
        })
        mlflow.log_artifact(result["predictions_path"], artifact_path="predictions")
        if result.get("drift_report_html"):
            mlflow.log_artifact(result["drift_report_html"], artifact_path="drift_reports")
        if result.get("drift_report_json"):
            mlflow.log_artifact(result["drift_report_json"], artifact_path="drift_reports")


# ── Read helpers ──────────────────────────────────────────────────────────────
def get_all_results() -> list:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT * FROM batch_results ORDER BY year, month")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def get_result(year: int, month: int) -> Optional[dict]:
    if not DB_PATH.exists():
        return None
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT * FROM batch_results WHERE year=? AND month=?", (year, month)
        )
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
    return dict(zip(cols, row)) if row else None
