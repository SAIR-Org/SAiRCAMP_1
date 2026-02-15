"""
NYC Taxi ML Pipeline Configuration
Centralized configuration for all pipeline parameters
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple


@dataclass
class DataConfig:
    """Data acquisition and filtering configuration."""
    
    # Kaggle dataset
    dataset_name: str = "elemento/nyc-yellow-taxi-trip-data"
    file_name: str = "yellow_tripdata_2016-01.csv"
    
    # Sampling
    sample_size: int = 200000
    chunk_size: int = 500000
    num_chunks: int = 2
    
    # Filtering thresholds
    min_trip_duration: int = 60  # seconds
    max_trip_duration: int = 7200  # seconds (2 hours)
    min_trip_distance: float = 0.1  # miles
    max_trip_distance: float = 50.0  # miles
    
    # Geographic bounds (NYC)
    nyc_lat_range: Tuple[float, float] = (40.5, 40.9)
    nyc_lon_range: Tuple[float, float] = (-74.3, -73.7)
    
    # Passenger count
    min_passenger_count: int = 1
    max_passenger_count: int = 6
    
    # Features
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
    
    # Reproducibility
    random_state: int = 42
    test_size: float = 0.2
    val_size: float = 0.2
    cv_folds: int = 5
    n_jobs: int = -1
    
    # Outlier handling
    iqr_factor: float = 1.5
    
    # Model hyperparameters
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
    
    # Hyperparameter tuning
    tuning_n_candidates: int = 6
    tuning_min_resources: int = 100
    tuning_factor: int = 3
    tuning_cv_folds: int = 3
    
    # Model selection
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
    
    experiment_name: str = "nyc_taxi_production_pipeline"
    model_name: str = "nyc_taxi_predictor"
    tracking_uri: str = "sqlite:///mlflow_nyc_taxi.db"
    
    # Tags
    project_tag: str = "nyc_taxi"
    team_tag: str = "data_science"
    framework_tag: str = "scikit-learn"
    
    # Registry stages
    staging_stage: str = "Staging"
    production_stage: str = "Production"
    archived_stage: str = "Archived"
    
    # Promotion criteria
    min_r2_improvement: float = 0.01  # 1% minimum improvement


@dataclass
class PathConfig:
    """File paths configuration."""
    
    # Base directories
    base_dir: str = os.path.abspath(".")
    model_dir: str = "models"
    data_dir: str = "data"
    log_dir: str = "logs"
    
    # MLflow
    mlflow_db_name: str = "mlflow_nyc_taxi.db"
    
    def __post_init__(self):
        """Create directories if they don't exist."""
        for dir_path in [self.model_dir, self.data_dir, self.log_dir]:
            os.makedirs(dir_path, exist_ok=True)
    
    @property
    def mlflow_db_path(self) -> str:
        """Full path to MLflow database."""
        return os.path.join(self.base_dir, self.mlflow_db_name)


@dataclass
class RetryConfig:
    """Retry mechanism configuration."""
    
    max_retries: int = 3
    retry_delay: int = 5  # seconds
    exponential_backoff: bool = True
    backoff_multiplier: float = 2.0


@dataclass
class LogConfig:
    """Logging configuration."""
    
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file: str = "pipeline.log"
    
    # File handler settings
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


@dataclass
class Config:
    """Main configuration container."""
    
    data: DataConfig = field(default_factory=DataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    mlflow: MLflowConfig = field(default_factory=MLflowConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    log: LogConfig = field(default_factory=LogConfig)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            'data': self.data.__dict__,
            'model': self.model.__dict__,
            'mlflow': self.mlflow.__dict__,
            'paths': {k: v for k, v in self.paths.__dict__.items() 
                     if not k.startswith('_')},
            'retry': self.retry.__dict__,
            'log': self.log.__dict__
        }


def load_config() -> Config:
    """Load configuration with environment variable overrides."""
    config = Config()
    
    # Override with environment variables if present
    if os.getenv('RANDOM_STATE'):
        config.model.random_state = int(os.getenv('RANDOM_STATE'))
    
    if os.getenv('SAMPLE_SIZE'):
        config.data.sample_size = int(os.getenv('SAMPLE_SIZE'))
    
    if os.getenv('MLFLOW_EXPERIMENT_NAME'):
        config.mlflow.experiment_name = os.getenv('MLFLOW_EXPERIMENT_NAME')
    
    return config