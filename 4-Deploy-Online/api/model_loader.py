import os
import sys
import pickle
import tempfile
from pathlib import Path

import mlflow
import mlflow.sklearn
from mlflow import MlflowClient


_DEPLOYMENT_DIR = Path(__file__).parent.parent        # 4-Deploy-Online/
_PIPELINE_DIR = _DEPLOYMENT_DIR / "pipeline"

sys.path.insert(0, str(_DEPLOYMENT_DIR))  # shared.feature_engineering (new pickles)
sys.path.insert(0, str(_PIPELINE_DIR))    # src.features re-export (old pickles)
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{_PIPELINE_DIR / 'mlflow_trip_duration.db'}",
)
MODEL_NAME = os.getenv("MODEL_NAME", "trip_duration_model")
MODEL_ALIAS = os.getenv("MODEL_ALIAS", "champion")


class _State:
    model = None
    preprocessor = None
    version: str = "unknown"
    alias: str = MODEL_ALIAS


_state = _State()


def load_model() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    mv = client.get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)
    _state.version = f"v{mv.version}"
    _state.alias = MODEL_ALIAS

    _state.model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")

    # Load the fitted preprocessor saved alongside the model
    try:
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
