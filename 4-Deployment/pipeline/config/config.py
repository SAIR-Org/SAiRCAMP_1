"""
Configuration for 4-Deployment/pipeline
=========================================
CHANGES FROM pipeline_with_prefect/config/config.py:

  DataConfig:
    REMOVED: dataset_name, file_name       (Kaggle-specific params)
    REMOVED: nyc_lat_range, nyc_lon_range  (lat/lon no longer used)
    REMOVED: chunk_size, num_chunks        (parquet reads don't need chunking)
    ADDED:   tlc_url_template              (direct TLC parquet URL)
    ADDED:   train_year, train_months      (year/month selectors)
    ADDED:   raw_columns                   (columns to fetch from parquet)
    CHANGED: prediction_time_features      (lat/lon → PULocationID/DOLocationID)
    CHANGED: sample_size                   (200k → 500k, larger 2019 dataset)

  MLflowConfig:
    CHANGED: experiment_name  (nyc_taxi_prefect_pipeline → nyc_taxi_v2_tlc)
    CHANGED: model_name       (nyc_taxi_predictor → nyc_taxi_v2)
    CHANGED: tracking_uri     (relative → absolute path, anchored to pipeline/)
             WHY: api/, batch/, monitoring/ run from different dirs and need
                  to point to the same DB without path resolution ambiguity.

  ModelConfig:
    ADDED:   'XGBoost' to models_to_train and tunable_models
    WHY:     XGBoost closed the R² gap vs 2016 pipeline from 0.05 to 0.02.
             Became the champion model at R²=0.817, MAE=3.07 min on 2019 data.

  PathConfig: unchanged
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple


@dataclass
class DataConfig:
    """Data acquisition and filtering configuration."""

    # TLC direct download — no Kaggle credentials needed
    tlc_url_template: str = (
        "https://d37ci6vzurychx.cloudfront.net/trip-data/"
        "yellow_tripdata_{year}-{month:02d}.parquet"
    )

    # Training data: 2019 quarterly sample (Jan/Apr/Jul/Oct = seasonal coverage)
    # Change train_months to list(range(1,13)) for full year
    train_year: int = 2019
    train_months: List[int] = field(default_factory=lambda: [1, 4, 7, 10])

    # Columns to fetch from parquet (avoids downloading unused columns)
    raw_columns: List[str] = field(default_factory=lambda: [
        'tpep_pickup_datetime',
        'tpep_dropoff_datetime',
        'PULocationID',
        'DOLocationID',
        'passenger_count',
        'trip_distance',
        'VendorID',
        'RatecodeID',
        'payment_type',
        'fare_amount',       # leakage — excluded from features, used for target validation
        'tip_amount',        # leakage
        'total_amount',      # leakage
    ])

    sample_size: int = 500000       # total rows sampled across all months
    samples_per_month: int = 125000 # sample_size / len(train_months)

    min_trip_duration: int = 60       # seconds
    max_trip_duration: int = 7200     # seconds (2 hours)
    min_trip_distance: float = 0.1    # miles
    max_trip_distance: float = 50.0   # miles

    min_passenger_count: int = 1
    max_passenger_count: int = 6

    # Zone IDs replace lat/lon — no geographic bounds filter needed
    # PULocationID and DOLocationID are integers 1–265 (NYC zones only)
    prediction_time_features: List[str] = field(default_factory=lambda: [
        'tpep_pickup_datetime',
        'PULocationID',
        'DOLocationID',
        'passenger_count',
        'VendorID',
        'RatecodeID',
        'trip_distance',
        'payment_type',
    ])

    leakage_features: List[str] = field(default_factory=lambda: [
        'fare_amount', 'tip_amount', 'total_amount',
        'tpep_dropoff_datetime',
    ])


@dataclass
class ModelConfig:
    """Model training configuration — identical to pipeline_with_prefect."""

    random_state: int = 42
    test_size: float = 0.2
    val_size: float = 0.2
    cv_folds: int = 5
    n_jobs: int = -1

    iqr_factor: float = 1.5

    rf_n_estimators: int = 100
    rf_max_depth: int = 20
    rf_min_samples_split: int = 10

    gb_n_estimators: int = 100
    gb_learning_rate: float = 0.1
    gb_max_depth: int = 5

    ridge_alpha: float = 10.0
    lasso_alpha: float = 0.1
    elastic_alpha: float = 0.1
    elastic_l1_ratio: float = 0.5

    tuning_n_candidates: int = 6
    tuning_min_resources: int = 100
    tuning_factor: int = 3
    tuning_cv_folds: int = 3

    models_to_train: List[str] = field(default_factory=lambda: [
        'Linear Regression', 'Ridge', 'Lasso',
        'Random Forest', 'Gradient Boosting', 'XGBoost'
    ])

    tunable_models: List[str] = field(default_factory=lambda: [
        'Random Forest', 'Gradient Boosting', 'XGBoost'
    ])


# Absolute path to the MLflow DB — anchored to pipeline/ dir, not cwd.
# All downstream components (api/, batch/, monitoring/) must use this same URI.
_PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MLFLOW_DB_PATH = os.path.join(_PIPELINE_DIR, "mlflow_nyc_taxi_v2.db")
MLFLOW_TRACKING_URI = f"sqlite:///{_MLFLOW_DB_PATH}"


@dataclass
class MLflowConfig:
    """MLflow tracking and registry configuration."""

    # v2 names — separate from pipeline_with_prefect registry entries
    experiment_name: str = "nyc_taxi_v2_tlc"
    model_name: str = "nyc_taxi_v2"
    tracking_uri: str = MLFLOW_TRACKING_URI

    project_tag: str = "nyc_taxi"
    team_tag: str = "data_science"
    framework_tag: str = "scikit-learn"
    data_tag: str = "tlc_2019"

    staging_stage: str = "Staging"
    production_stage: str = "Production"
    archived_stage: str = "Archived"

    min_r2_improvement: float = 0.01


@dataclass
class PathConfig:
    """File paths configuration."""

    base_dir: str = os.path.abspath(".")
    model_dir: str = "models"
    data_dir: str = "data"
    log_dir: str = "logs"
    mlflow_db_name: str = "mlflow_nyc_taxi_v2.db"

    def __post_init__(self):
        for dir_path in [self.model_dir, self.data_dir, self.log_dir]:
            os.makedirs(dir_path, exist_ok=True)

    @property
    def mlflow_db_path(self) -> str:
        return os.path.join(self.base_dir, self.mlflow_db_name)


@dataclass
class LogConfig:
    """Logging configuration — identical to pipeline_with_prefect."""

    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file: str = "pipeline.log"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass
class Config:
    """Main configuration container."""

    data: DataConfig = field(default_factory=DataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    mlflow: MLflowConfig = field(default_factory=MLflowConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    log: LogConfig = field(default_factory=LogConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'data': self.data.__dict__,
            'model': self.model.__dict__,
            'mlflow': self.mlflow.__dict__,
            'paths': {k: v for k, v in self.paths.__dict__.items()
                      if not k.startswith('_')},
            'log': self.log.__dict__,
        }


def load_config() -> Config:
    """Load configuration with optional environment variable overrides."""
    config = Config()
    config.data.samples_per_month = (
        config.data.sample_size // len(config.data.train_months)
    )

    if os.getenv('RANDOM_STATE'):
        config.model.random_state = int(os.getenv('RANDOM_STATE'))
    if os.getenv('SAMPLE_SIZE'):
        config.data.sample_size = int(os.getenv('SAMPLE_SIZE'))
    if os.getenv('TRAIN_YEAR'):
        config.data.train_year = int(os.getenv('TRAIN_YEAR'))
    if os.getenv('MLFLOW_EXPERIMENT_NAME'):
        config.mlflow.experiment_name = os.getenv('MLFLOW_EXPERIMENT_NAME')

    return config
