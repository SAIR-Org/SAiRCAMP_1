"""
Core batch scoring logic — no Prefect, no FastAPI.
Imported by both flow.py (local/Prefect) and api.py (Docker/FastAPI).
"""
import os
import sys
import sqlite3
import pickle
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from sklearn.metrics import mean_absolute_error
import mlflow
from mlflow import MlflowClient


# ── Path setup ────────────────────────────────────────────────────────────────
_CORE_DIR     = Path(__file__).parent
_ONLINE_DIR   = _CORE_DIR.parent.parent / "4-Deploy-Online"
_PIPELINE_DIR = _ONLINE_DIR / "pipeline"

sys.path.insert(0, str(_ONLINE_DIR))    # shared.feature_engineering
sys.path.insert(0, str(_PIPELINE_DIR))  # src.features re-export (old pickles)

# ── Config ────────────────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{_PIPELINE_DIR / 'mlflow_trip_duration.db'}",
)

MODEL_NAME  = "trip_duration_model"
MODEL_ALIAS = "champion"

# Data paths — BATCH_DATA_DIR overrides for Docker (defaults to local batch/ dir)
DATA_DIR         = Path(os.getenv("BATCH_DATA_DIR", str(_CORE_DIR)))
DB_PATH          = DATA_DIR / "batch_results.db"
PREDICTIONS_DIR  = DATA_DIR / "predictions"

# Artifact path remapping for Docker (see 4-Deploy-Online/docs/DOCKER_DEBUGGING.md)
_ARTIFACTS_ROOT = os.getenv("MLFLOW_ARTIFACTS_ROOT")

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

MAE_RATIO_THRESHOLD = 1.5
VOLUME_THRESHOLD    = 500_000


# ── MLflow artifact path remapping ───────────────────────────────────────────
def _remap(path: str) -> str:
    if not _ARTIFACTS_ROOT or not path:
        return path
    idx = path.find("/mlruns/")
    return _ARTIFACTS_ROOT + path[idx:] if idx >= 0 else path


def _get_storage_location(version: str) -> str:
    db_path = MLFLOW_TRACKING_URI.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT storage_location FROM model_versions WHERE name=? AND version=?",
        (MODEL_NAME, version),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _get_artifact_uri(run_id: str) -> str:
    db_path = MLFLOW_TRACKING_URI.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT artifact_uri FROM runs WHERE run_uuid=?", (run_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None

def init_db():
    PREDICTIONS_DIR.mkdir(parents=True , exist_ok= True) 

    conn = sqlite3.connect(DB_PATH) 
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_result (
        year                        INTEGER,
        month                       INTEGER,
        score_at                    TEXT ,
        total_rows                  INTEGER ,
        mae                         REAL,
        mae_ratio                   REAL,
        target_mean                 REAL,
        dist_mean                   REAL,
        alret                       INTEGER,
        prediction_path             TEXT,
        PRIMARY KEY                 (year, month)
        )
        """
    ) 

    conn.commit()
    conn.close() 

def load_champion() -> dict:
    """Load @champion model, preprocessor, and training baseline from MLflow."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()
    mv     = client.get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)

    if _ARTIFACTS_ROOT:
        model = mlflow.sklearn.load_model(_remap(_get_storage_location(mv.version)))
        preprocessor_path = (
            Path(_remap(_get_artifact_uri(mv.run_id))) / "preprocessor" / "preprocessor.pkl"
        )
        with open(preprocessor_path, "rb") as f:
            preprocessor = pickle.load(f)
    else:
        model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")
        dst   = tempfile.mkdtemp()
        art_path = mlflow.artifacts.download_artifacts(
            run_id=mv.run_id,
            artifact_path="preprocessor/preprocessor.pkl",
            dst_path=dst,
        )
        with open(art_path, "rb") as f:
            preprocessor = pickle.load(f)

    run        = client.get_run(mv.run_id)
    train_mae  = float(run.data.metrics["test_mae"])
    train_mean = float(run.data.metrics["train_duration_mean"])

    return {
        "model":        model,
        "preprocessor": preprocessor,
        "train_mae":    train_mae,
        "train_mean":   train_mean,
        "version":      mv.version,
        "run_id":       mv.run_id,
    } 


def score_month(year:int , month:int, champion:dict) -> dict :

    url = TLC_URL.format(year=year , month=month) 
    df = pd.read_parquet(url , columns=COLS) 
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

    X = champion["preprocessor"].transform(df[FEATURE_COLS].copy()) 
    y_pred = champion["model"].predict(X) 
    y_true = df["tpep_dropoff_datetime"] 

    parquet_path = PREDICTIONS_DIR / f"{year}_{month:0.2d}.parquet" 

    pd.DataFrame(
        {
        "pickup_datetime":              df["tpep_pickup_datetime"].values,
        "PULocationID":                 df["PULocationID"].values,
        "DOLocationID":                 df["DOLocationID"].values,
        "trip_distance":                df["trip_distance"].values,
        "actual_duration_minutes":      y_true,
        "predicted_duration_minutes":   y_pred,
        "error_minutes":                y_pred - y_true,
        "model_version":                champion["version"],
        }
    ).to_parquet(parquet_path , index=False) 


    # ── Compute aggregate metrics (drift engine) ──────────────────────────────
    mae         = float(mean_absolute_error(y_true, y_pred))
    mae_ratio   = mae / champion["train_mae"]
    target_mean = float(y_true.mean())
    dist_mean   = float(df["trip_distance"].mean())
    alert       = int((mae_ratio > MAE_RATIO_THRESHOLD) or (total_rows < VOLUME_THRESHOLD))

    return {
        "year":            year,
        "month":           month,
        "scored_at":       datetime.utcnow().isoformat(),
        "total_rows":      total_rows,
        "mae":             mae,
        "mae_ratio":       mae_ratio,
        "target_mean":     target_mean,
        "dist_mean":       dist_mean,
        "alert":           alert,
        "predictions_path": str(parquet_path),
    } 


def save_results(result:dict , champion:dict):

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI) 

    conn = sqlite3.connectq(DB_PATH) 

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

def get_all_results() -> list : 

    # read all the rows from the batch_results.db 

    if not DB_PATH.exists():
        return [] 

    conn = sqlite3.connect(DB_PATH) 
    cur = conn.execute(
        "SELECT * FROM batch_results.db ORDER BY year , month"
    ) 

    cols = [d[0] for d in cur.description] 
    rows = cur.fetchall() 
    conn.close() 
    return [
        dict(zip(cols,row)) for row in rows
    ] 

def get_results(year:int , month:int) -> Optional[dict]:

    if not DB_PATH.exists():
        return None 

    conn = sqlite3.connect(DB_PATH) 
    cur = conn.execute(
        "SELECT * FROM batch_results WHERE year = ? AND month=?",
        (year ,month)
    ) 

    cols = [d[0] for d in cur.description] 
    row = cur.fetchone() 
    conn.close() 
    return dict(zip(cols , row)) if row else None
 









