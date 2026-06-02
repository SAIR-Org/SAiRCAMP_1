import os
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class DataConfig:
    """Data acquisition and filtering configuration."""

    tlc_url_template: str = (
        "https://d37ci6vzurychx.cloudfront.net/trip-data/"
        "yellow_tripdata_{year}-{month:02d}.parquet"
    )

    # Training years + months — supports multi-year retraining
    train_years: List[int] = field(default_factory=lambda: [2019])
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
        'fare_amount',   # excluded from features — used for target validation only
        'tip_amount',
        'total_amount',
    ])

    sample_size: int = 500000
    samples_per_month: int = 125000  # recalculated in load_config()

    min_trip_duration: int = 60       # seconds
    max_trip_duration: int = 7200     # seconds (2 hours)
    min_trip_distance: float = 0.1    # miles
    max_trip_distance: float = 50.0   # miles

    min_passenger_count: int = 1
    max_passenger_count: int = 6

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


# Absolute path anchored to pipeline/ — all downstream components share this URI.
_PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MLFLOW_DB_PATH = os.path.join(_PIPELINE_DIR, "mlflow_trip_duration.db")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{_MLFLOW_DB_PATH}")


@dataclass
class MLflowConfig:
    """MLflow tracking and registry configuration."""

    experiment_name: str = "trip_duration_v2"
    model_name: str = "trip_duration_model"
    tracking_uri: str = MLFLOW_TRACKING_URI

    min_r2_improvement: float = 0.01


@dataclass
class Config:
    """Main configuration container."""

    data: DataConfig = field(default_factory=DataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    mlflow: MLflowConfig = field(default_factory=MLflowConfig)


def load_config() -> Config:
    """Load configuration with optional environment variable overrides."""
    config = Config()
    total_months = len(config.data.train_years) * len(config.data.train_months)
    config.data.samples_per_month = config.data.sample_size // total_months

    if os.getenv('RANDOM_STATE'):
        config.model.random_state = int(os.getenv('RANDOM_STATE'))
    if os.getenv('SAMPLE_SIZE'):
        config.data.sample_size = int(os.getenv('SAMPLE_SIZE'))
    if os.getenv('TRAIN_YEAR'):
        config.data.train_year = int(os.getenv('TRAIN_YEAR'))
    if os.getenv('MLFLOW_EXPERIMENT_NAME'):
        config.mlflow.experiment_name = os.getenv('MLFLOW_EXPERIMENT_NAME')

    return config
