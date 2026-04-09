"""
NYC Taxi ML Pipeline Configuration
===================================
Identical to pipline_no_perfect/config/config.py with one change:

  REMOVED: RetryConfig dataclass
  WHY:     Prefect handles retries via @task(retries=N, retry_delay_seconds=N).
           A separate RetryConfig dataclass is no longer needed.
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple


@dataclass
class DataConfig:
    """Data acquisition and filtering configuration."""

    dataset_name: str = "elemento/nyc-yellow-taxi-trip-data"
    file_name: str = "yellow_tripdata_2016-01.csv"

    sample_size: int = 200000
    chunk_size: int = 500000
    num_chunks: int = 2

    min_trip_duration: int = 60       # seconds
    max_trip_duration: int = 7200     # seconds (2 hours)
    min_trip_distance: float = 0.1    # miles
    max_trip_distance: float = 50.0   # miles

    nyc_lat_range: Tuple[float, float] = (40.5, 40.9)
    nyc_lon_range: Tuple[float, float] = (-74.3, -73.7)

    min_passenger_count: int = 1
    max_passenger_count: int = 6

    prediction_time_features: List[str] = field(default_factory=lambda: [
        'tpep_pickup_datetime',
        'pickup_longitude', 'pickup_latitude',
        'dropoff_longitude', 'dropoff_latitude',
        'passenger_count', 'VendorID', 'RatecodeID',
        'trip_distance', 'payment_type'
    ])

    leakage_features: List[str] = field(default_factory=lambda: [
        'fare_amount', 'tip_amount', 'total_amount',
        'extra', 'mta_tax', 'tolls_amount',
        'improvement_surcharge', 'store_and_fwd_flag',
        'tpep_dropoff_datetime'
    ])


@dataclass
class ModelConfig:
    """Model training configuration."""

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
        'Random Forest', 'Gradient Boosting'
    ])

    tunable_models: List[str] = field(default_factory=lambda: [
        'Random Forest', 'Gradient Boosting'
    ])


@dataclass
class MLflowConfig:
    """MLflow tracking and registry configuration."""

    experiment_name: str = "nyc_taxi_prefect_pipeline"
    model_name: str = "nyc_taxi_predictor"
    tracking_uri: str = "sqlite:///mlflow_nyc_taxi.db"

    project_tag: str = "nyc_taxi"
    team_tag: str = "data_science"
    framework_tag: str = "scikit-learn"

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
    mlflow_db_name: str = "mlflow_nyc_taxi.db"

    def __post_init__(self):
        for dir_path in [self.model_dir, self.data_dir, self.log_dir]:
            os.makedirs(dir_path, exist_ok=True)

    @property
    def mlflow_db_path(self) -> str:
        return os.path.join(self.base_dir, self.mlflow_db_name)


@dataclass
class LogConfig:
    """Logging configuration."""

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
            'paths': {k: v for k, v in self.paths.__dict__.items() if not k.startswith('_')},
            'log': self.log.__dict__,
        }


def load_config() -> Config:
    """Load configuration with optional environment variable overrides."""
    config = Config()

    if os.getenv('RANDOM_STATE'):
        config.model.random_state = int(os.getenv('RANDOM_STATE'))
    if os.getenv('SAMPLE_SIZE'):
        config.data.sample_size = int(os.getenv('SAMPLE_SIZE'))
    if os.getenv('MLFLOW_EXPERIMENT_NAME'):
        config.mlflow.experiment_name = os.getenv('MLFLOW_EXPERIMENT_NAME')

    return config
