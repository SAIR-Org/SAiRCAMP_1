"""
Model loader for the online API.

With the MLflow tracking server, loading is straightforward:
- MLFLOW_TRACKING_URI points to http://mlflow:5000 (Docker) or local SQLite (dev)
- mlflow.sklearn.load_model() resolves the model URI via the server
- Artifacts downloaded directly from the server's artifact store
- No path remapping needed — the server handles everything
"""
import os
import sys
import pickle
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
    f"sqlite:///{_PIPELINE_DIR / 'mlflow_trip_duration.db'}",  # local dev default
)
MODEL_NAME  = os.getenv("MODEL_NAME",  "trip_duration_model")
MODEL_ALIAS = os.getenv("MODEL_ALIAS", "champion")


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

    # Load model — server resolves URI and serves the artifact directly
    _state.model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")

    # Load preprocessor from the same run
    dst      = tempfile.mkdtemp()
    art_path = mlflow.artifacts.download_artifacts(
        run_id=mv.run_id,
        artifact_path="preprocessor/preprocessor.pkl",
        dst_path=dst,
    )
    with open(art_path, "rb") as f:
        _state.preprocessor = pickle.load(f)


def get_state() -> _State:
    return _state
