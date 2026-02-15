"""
NYC Taxi ML Pipeline Configuration
Centralized configuration for reproducibility and easy tuning
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Centralized configuration for the ML pipeline."""
    
    # ============ PROJECT PATHS ============
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"
    MODEL_DIR: Path = PROJECT_ROOT / "models"
    LOG_DIR: Path = PROJECT_ROOT / "logs"
    
    # ============ MLFLOW CONFIG ============
    MLFLOW_DB_PATH: str = str(PROJECT_ROOT / "mlflow_nyc_taxi.db")
    MLFLOW_TRACKING_URI: str = f"sqlite:///{MLFLOW_DB_PATH}"
    MLFLOW_EXPERIMENT_NAME: str = "nyc_taxi_production_pipeline"
    MLFLOW_MODEL_NAME: str = "nyc_taxi_predictor"
    
    # ============ REPRODUCIBILITY ============
    RANDOM_STATE: int = 42
    TEST_SIZE: float = 0.2
    VAL_SIZE: float = 0.2
    CV_FOLDS: int = 3
    N_JOBS: int = -1
    
    # ============ DATA FILTERING ============
    SAMPLE_SIZE: int = 200000
    MIN_TRIP_DURATION: int = 60  # seconds
    MAX_TRIP_DURATION: int = 7200  # seconds
    MIN_TRIP_DISTANCE: float = 0.1  # miles
    MAX_TRIP_DISTANCE: float = 50.0  # miles
    
    # ============ GEOGRAPHIC BOUNDS ============
    NYC_LAT_MIN: float = 40.5
    NYC_LAT_MAX: float = 40.9
    NYC_LON_MIN: float = -74.3
    NYC_LON_MAX: float = -73.7
    
    # ============ MODEL HYPERPARAMETERS ============
    # Random Forest
    RF_N_ESTIMATORS: int = 100
    RF_MAX_DEPTH: int = 20
    RF_MIN_SAMPLES_SPLIT: int = 10
    
    # Gradient Boosting
    GB_N_ESTIMATORS: int = 100
    GB_LEARNING_RATE: float = 0.1
    GB_MAX_DEPTH: int = 5
    
    # Linear Models
    RIDGE_ALPHA: float = 10.0
    LASSO_ALPHA: float = 0.1
    ELASTIC_ALPHA: float = 0.1
    ELASTIC_L1_RATIO: float = 0.5
    
    # ============ FEATURE ENGINEERING ============
    IQR_FACTOR: float = 1.5
    
    # ============ TUNING CONFIG ============
    TUNING_N_CANDIDATES: int = 6
    TUNING_MIN_RESOURCES: int = 100
    TUNING_FACTOR: int = 3
    
    def __post_init__(self):
        """Create necessary directories."""
        for directory in [self.DATA_DIR, self.MODEL_DIR, self.LOG_DIR]:
            directory.mkdir(parents=True, exist_ok=True)


# Create global config instance
config = Config()


# Features to use for prediction (available at pickup time)
PREDICTION_TIME_FEATURES = [
    'tpep_pickup_datetime',
    'pickup_longitude', 'pickup_latitude',
    'dropoff_longitude', 'dropoff_latitude',
    'passenger_count', 'VendorID', 'RatecodeID',
    'trip_distance', 'payment_type'
]

# Features that cause data leakage (known after trip completion)
LEAKAGE_FEATURES = [
    'fare_amount', 'tip_amount', 'total_amount',
    'extra', 'mta_tax', 'tolls_amount',
    'improvement_surcharge', 'store_and_fwd_flag',
    'tpep_dropoff_datetime'
]