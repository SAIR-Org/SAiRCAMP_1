"""
Model loader for the online API.

Uses MLFLOW_ARTIFACTS_ROOT to remap absolute host artifact paths to
container paths — required because the pipeline runs locally and stores
absolute host paths in the MLflow SQLite DB.

See 4-Deploy-Online/docs/DOCKER_DEBUGGING.md for the full story.
Note: MLFLOW_SERVER.md documents the proper production fix (tracking server).
"""
import os
import sys
import pickle
import sqlite3
import tempfile
from pathlib import Path

import mlflow
import mlflow.sklearn
from mlflow import MlflowClient


# ── Path setup ────────────────────────────────────────────────────────────────
_MODULE_DIR   = Path(__file__).parent.parent   # 6-Full-System/
_PIPELINE_DIR = _MODULE_DIR / "pipeline"

sys.path.insert(0, str(_MODULE_DIR))    # shared.feature_engineering importable
sys.path.insert(0, str(_PIPELINE_DIR))  # src.features re-export (old pickles)

# ── Config ────────────────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{_PIPELINE_DIR / 'mlflow_trip_duration.db'}",
)
MODEL_NAME  = os.getenv("MODEL_NAME",  "trip_duration_model")
MODEL_ALIAS = os.getenv("MODEL_ALIAS", "champion")

# Remap host artifact paths to container paths
# Set MLFLOW_ARTIFACTS_ROOT=/app/pipeline in docker-compose
_ARTIFACTS_ROOT = os.getenv("MLFLOW_ARTIFACTS_ROOT")


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


class _State:
    model        = None
    preprocessor = None
    version: str = "unknown"
    alias: str   = MODEL_ALIAS


_state = _State()


def load_model() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    mv = client.get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)
    _state.version = f"v{mv.version}"
    _state.alias   = MODEL_ALIAS

    if _ARTIFACTS_ROOT and mv.source:
        model_path = _remap(_get_storage_location(mv.version))
        _state.model = mlflow.sklearn.load_model(model_path)
    else:
        _state.model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")

    try:
        if _ARTIFACTS_ROOT:
            artifact_uri = _get_artifact_uri(mv.run_id)
            preprocessor_path = Path(_remap(artifact_uri)) / "preprocessor" / "preprocessor.pkl"
            with open(preprocessor_path, "rb") as f:
                _state.preprocessor = pickle.load(f)
        else:
            dst = tempfile.mkdtemp()
            art_path = mlflow.artifacts.download_artifacts(
                run_id=mv.run_id,
                artifact_path="preprocessor/preprocessor.pkl",
                dst_path=dst,
            )
            with open(art_path, "rb") as f:
                _state.preprocessor = pickle.load(f)
    except Exception as exc:
        raise RuntimeError(
            f"Preprocessor not found in MLflow run {mv.run_id[:8]}. "
            "Re-run the pipeline with --promote to register a model that includes it."
        ) from exc


def get_state() -> _State:
    return _state
