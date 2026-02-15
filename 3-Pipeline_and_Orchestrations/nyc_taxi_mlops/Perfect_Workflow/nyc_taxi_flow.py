"""
NYC Taxi ML Pipeline - Prefect Orchestration
=============================================

This module defines the Prefect flow for orchestrating the NYC taxi
trip duration prediction ML pipeline with proper task dependencies,
retry logic, caching, and monitoring.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
import pandas as pd
import numpy as np
from pathlib import Path

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
from prefect.artifacts import create_markdown_artifact
from prefect.blocks.system import Secret

# Import your existing pipeline components
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import Config
from src.data.data_acquisition import DataAcquisition
from src.data.data_preprocessing import DataPreprocessor
from src.features.feature_engineering import NYCYellowTaxiFeatureEngineer, OutlierHandler
from src.models.model_training import ModelTrainer
from src.models.model_registry import ModelRegistry
from src.models.model_deployment import ModelDeployment

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler
from sklearn.pipeline import Pipeline


# ============================================
# PREFECT TASKS - Each pipeline step
# ============================================

@task(
    name="Acquire Data",
    description="Download NYC taxi data from Kaggle",
    retries=3,
    retry_delay_seconds=10,
    cache_key_fn=lambda *args, **kwargs: "nyc_taxi_data_acquisition",
    cache_expiration=timedelta(days=7),
    tags=["data", "acquisition", "kaggle"]
)
def acquire_data_task(config: Config) -> pd.DataFrame:
    """
    Download and load NYC taxi data with caching.
    
    Args:
        config: Configuration object
        
    Returns:
        Raw DataFrame
    """
    logger = get_run_logger()
    logger.info("🔵 Starting data acquisition...")
    
    acquisition = DataAcquisition(config)
    df = acquisition.download_and_load()
    
    logger.info(f"✅ Data acquired: {len(df):,} rows")
    return df


@task(
    name="Preprocess Data",
    description="Clean and validate data, remove outliers",
    retries=2,
    retry_delay_seconds=5,
    tags=["data", "preprocessing", "cleaning"]
)
def preprocess_data_task(df: pd.DataFrame, config: Config) -> pd.DataFrame:
    """
    Clean and preprocess data.
    
    Args:
        df: Raw DataFrame
        config: Configuration object
        
    Returns:
        Cleaned DataFrame
    """
    logger = get_run_logger()
    logger.info("🔵 Starting data preprocessing...")
    
    preprocessor = DataPreprocessor(config)
    df_clean = preprocessor.clean_data(df)
    
    logger.info(f"✅ Data cleaned: {len(df_clean):,} rows retained")
    
    # Create data quality artifact
    quality_report = f"""
# Data Quality Report

- **Original Rows**: {len(df):,}
- **Cleaned Rows**: {len(df_clean):,}
- **Retention Rate**: {len(df_clean)/len(df)*100:.1f}%
- **Missing Values**: {df_clean.isnull().sum().sum()}
- **Duplicate Rows**: {df_clean.duplicated().sum()}
"""
    create_markdown_artifact(
        key="data-quality-report",
        markdown=quality_report,
        description="Data quality metrics after preprocessing"
    )
    
    return df_clean


@task(
    name="Split Data",
    description="Split data into train/val/test sets BEFORE feature engineering",
    tags=["data", "splitting"]
)
def split_data_task(
    df: pd.DataFrame,
    config: Config
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """
    Split data into train/val/test sets.
    
    Args:
        df: Cleaned DataFrame
        config: Configuration object
        
    Returns:
        Tuple of (X_train, X_val, X_test, y_train, y_val, y_test)
    """
    logger = get_run_logger()
    logger.info("🔵 Splitting data...")
    
    # Define prediction-time features
    PREDICTION_TIME_FEATURES = [
        'tpep_pickup_datetime',
        'pickup_longitude', 'pickup_latitude',
        'dropoff_longitude', 'dropoff_latitude',
        'passenger_count', 'VendorID', 'RatecodeID',
        'trip_distance', 'payment_type'
    ]
    
    X = df[PREDICTION_TIME_FEATURES]
    y = df['trip_duration_minutes'].values
    
    # Split: train/temp then temp -> val/test
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y,
        test_size=config.model.test_size,
        random_state=config.model.random_state
    )
    
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp,
        test_size=config.model.val_size,
        random_state=config.model.random_state
    )
    
    logger.info(f"✅ Data split complete:")
    logger.info(f"   Train: {len(X_train):,} samples")
    logger.info(f"   Val:   {len(X_val):,} samples")
    logger.info(f"   Test:  {len(X_test):,} samples")
    
    return X_train, X_val, X_test, y_train, y_val, y_test


@task(
    name="Engineer Features",
    description="Create feature engineering pipeline and transform data",
    tags=["features", "engineering", "transformation"]
)
def engineer_features_task(
    X_train: pd.DataFrame,
    X_val: pd.DataFrame,
    X_test: pd.DataFrame,
    config: Config
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Pipeline, List[str]]:
    """
    Create and fit feature engineering pipeline.
    
    Args:
        X_train, X_val, X_test: Split datasets
        config: Configuration object
        
    Returns:
        Tuple of (X_train_processed, X_val_processed, X_test_processed, preprocessor, feature_names)
    """
    logger = get_run_logger()
    logger.info("🔵 Engineering features...")
    
    # Build preprocessing pipeline
    preprocessor = Pipeline([
        ('feature_engineer', NYCYellowTaxiFeatureEngineer(config=config)),
        ('outlier_handler', OutlierHandler(factor=config.model.iqr_factor)),
        ('scaler', RobustScaler())
    ])
    
    # Fit on training data only
    preprocessor.fit(X_train)
    
    # Transform all datasets
    X_train_processed = preprocessor.transform(X_train)
    X_val_processed = preprocessor.transform(X_val)
    X_test_processed = preprocessor.transform(X_test)
    
    feature_names = preprocessor.named_steps['feature_engineer'].get_feature_names()
    
    logger.info(f"✅ Features engineered: {len(feature_names)} features")
    logger.info(f"   Shape: Train {X_train_processed.shape}, Val {X_val_processed.shape}, Test {X_test_processed.shape}")
    
    return X_train_processed, X_val_processed, X_test_processed, preprocessor, feature_names


@task(
    name="Train Models",
    description="Train all models with MLflow tracking",
    retries=2,
    retry_delay_seconds=10,
    tags=["model", "training", "mlflow"]
)
def train_models_task(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    config: Config,
    feature_names: List[str]
) -> Dict[str, Any]:
    """
    Train all models with MLflow tracking.
    
    Args:
        X_train, y_train: Training data
        X_val, y_val: Validation data
        config: Configuration object
        feature_names: List of feature names
        
    Returns:
        Dictionary with training results
    """
    logger = get_run_logger()
    logger.info("🔵 Training models...")
    
    trainer = ModelTrainer(config)
    results = trainer.train_all_models(
        X_train, y_train,
        X_val, y_val,
        feature_names
    )
    
    # Create model comparison artifact
    comparison_md = "# Model Comparison\n\n"
    comparison_md += "| Model | Val R² | Val MAE | Training Time |\n"
    comparison_md += "|-------|--------|---------|---------------|\n"
    
    for name, metrics in results['metrics'].items():
        comparison_md += f"| {name} | {metrics['val_r2']:.4f} | {metrics['val_mae']:.2f} | {metrics['training_time']:.1f}s |\n"
    
    create_markdown_artifact(
        key="model-comparison",
        markdown=comparison_md,
        description="Performance comparison of all trained models"
    )
    
    logger.info(f"✅ Models trained: {len(results['models'])} models")
    logger.info(f"   Best model: {results['best_model_name']} (R²: {results['best_metrics']['val_r2']:.4f})")
    
    return results


@task(
    name="Tune Best Model",
    description="Hyperparameter tuning with HalvingRandomSearchCV",
    timeout_seconds=3600,  # 1 hour timeout
    retries=1,
    tags=["model", "tuning", "optimization"]
)
def tune_model_task(
    training_results: Dict[str, Any],
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    config: Config
) -> Optional[Dict[str, Any]]:
    """
    Tune the best model's hyperparameters.
    
    Args:
        training_results: Results from training task
        X_train, y_train: Training data
        X_val, y_val: Validation data
        config: Configuration object
        
    Returns:
        Tuning results or None if skipped
    """
    logger = get_run_logger()
    
    if config.model.skip_tuning:
        logger.info("⏭️  Skipping hyperparameter tuning (skip_tuning=True)")
        return None
    
    best_model_name = training_results['best_model_name']
    
    # Only tune tree-based models
    if best_model_name not in ['Random Forest', 'Gradient Boosting']:
        logger.info(f"⏭️  Skipping tuning for {best_model_name} (not tunable)")
        return None
    
    logger.info(f"🔵 Tuning {best_model_name}...")
    
    trainer = ModelTrainer(config)
    tuning_results = trainer.tune_model(
        best_model_name,
        training_results['models'][best_model_name],
        X_train, y_train,
        X_val, y_val,
        training_results['best_metrics']['val_r2']
    )
    
    if tuning_results:
        logger.info(f"✅ Tuning complete:")
        logger.info(f"   Best CV R²: {tuning_results['best_score']:.4f}")
        logger.info(f"   Improvement: +{tuning_results['improvement']:.4f}")
    
    return tuning_results


@task(
    name="Cross-Validate",
    description="K-fold cross-validation for final model",
    tags=["model", "validation", "cv"]
)
def cross_validate_task(
    training_results: Dict[str, Any],
    tuning_results: Optional[Dict[str, Any]],
    X_train: np.ndarray,
    y_train: np.ndarray,
    config: Config
) -> Dict[str, float]:
    """
    Perform cross-validation on final model.
    
    Args:
        training_results: Results from training
        tuning_results: Results from tuning (or None)
        X_train, y_train: Training data
        config: Configuration object
        
    Returns:
        CV metrics
    """
    logger = get_run_logger()
    
    if config.model.skip_cv:
        logger.info("⏭️  Skipping cross-validation (skip_cv=True)")
        return {}
    
    logger.info("🔵 Running cross-validation...")
    
    # Use tuned model if available, otherwise use best trained model
    if tuning_results and tuning_results['improvement'] > 0.01:
        model = tuning_results['best_model']
        logger.info("   Using tuned model")
    else:
        model = training_results['best_model']
        logger.info("   Using best trained model")
    
    trainer = ModelTrainer(config)
    cv_metrics = trainer.cross_validate_model(
        model, X_train, y_train
    )
    
    logger.info(f"✅ CV complete: R² = {cv_metrics['cv_r2_mean']:.4f} ± {cv_metrics['cv_r2_std']:.4f}")
    
    return cv_metrics


@task(
    name="Evaluate on Test Set",
    description="Final evaluation on held-out test set",
    tags=["model", "evaluation", "test"]
)
def evaluate_test_task(
    training_results: Dict[str, Any],
    tuning_results: Optional[Dict[str, Any]],
    X_test: np.ndarray,
    y_test: np.ndarray
) -> Dict[str, float]:
    """
    Evaluate final model on test set.
    
    Args:
        training_results: Results from training
        tuning_results: Results from tuning (or None)
        X_test, y_test: Test data
        
    Returns:
        Test metrics
    """
    logger = get_run_logger()
    logger.info("🔵 Evaluating on test set...")
    
    # Select final model
    if tuning_results and tuning_results['improvement'] > 0.01:
        model = tuning_results['best_model']
        model_type = "tuned"
    else:
        model = training_results['best_model']
        model_type = "trained"
    
    # Predictions
    y_test_pred = model.predict(X_test)
    
    # Calculate metrics
    from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
    
    test_metrics = {
        'test_r2': r2_score(y_test, y_test_pred),
        'test_rmse': np.sqrt(mean_squared_error(y_test, y_test_pred)),
        'test_mae': mean_absolute_error(y_test, y_test_pred)
    }
    
    logger.info(f"✅ Test evaluation complete ({model_type} model):")
    logger.info(f"   R²:   {test_metrics['test_r2']:.4f}")
    logger.info(f"   RMSE: {test_metrics['test_rmse']:.2f} min")
    logger.info(f"   MAE:  {test_metrics['test_mae']:.2f} min")
    
    # Create test results artifact
    test_report = f"""
# Test Set Evaluation

## Model: {training_results['best_model_name']} ({model_type})

### Performance Metrics
- **R² Score**: {test_metrics['test_r2']:.4f}
- **RMSE**: {test_metrics['test_rmse']:.2f} minutes
- **MAE**: {test_metrics['test_mae']:.2f} minutes

### Dataset Info
- **Test Samples**: {len(y_test):,}
- **Predictions Range**: [{y_test_pred.min():.1f}, {y_test_pred.max():.1f}] minutes
"""
    
    create_markdown_artifact(
        key="test-evaluation",
        markdown=test_report,
        description="Final test set evaluation results"
    )
    
    return test_metrics


@task(
    name="Register Model",
    description="Register model in MLflow Model Registry and transition to Staging",
    retries=3,
    retry_delay_seconds=5,
    tags=["mlflow", "registry", "deployment"]
)
def register_model_task(
    training_results: Dict[str, Any],
    tuning_results: Optional[Dict[str, Any]],
    cv_metrics: Dict[str, float],
    test_metrics: Dict[str, float],
    config: Config
) -> Dict[str, Any]:
    """
    Register model in MLflow Registry.
    
    Args:
        training_results: Training results
        tuning_results: Tuning results (or None)
        cv_metrics: CV metrics
        test_metrics: Test metrics
        config: Configuration object
        
    Returns:
        Registry information
    """
    logger = get_run_logger()
    logger.info("🔵 Registering model in MLflow...")
    
    # Determine which run to use
    if tuning_results and tuning_results['improvement'] > 0.01:
        run_id = tuning_results['run_id']
        model_type = "tuned"
    else:
        run_id = training_results['best_run_id']
        model_type = "trained"
    
    registry = ModelRegistry(config)
    registry_info = registry.register_and_transition(
        run_id=run_id,
        model_name=config.mlflow.model_name,
        test_metrics=test_metrics,
        cv_metrics=cv_metrics,
        model_type=training_results['best_model_name']
    )
    
    logger.info(f"✅ Model registered:")
    logger.info(f"   Version: {registry_info['version']}")
    logger.info(f"   Stage: {registry_info['stage']}")
    logger.info(f"   Type: {model_type}")
    
    return registry_info


@task(
    name="Create Deployment Package",
    description="Save deployment artifacts (model, preprocessor, metadata)",
    tags=["deployment", "artifacts"]
)
def create_deployment_task(
    training_results: Dict[str, Any],
    tuning_results: Optional[Dict[str, Any]],
    preprocessor: Pipeline,
    test_metrics: Dict[str, float],
    cv_metrics: Dict[str, float],
    registry_info: Dict[str, Any],
    config: Config
) -> str:
    """
    Create deployment package.
    
    Args:
        training_results: Training results
        tuning_results: Tuning results (or None)
        preprocessor: Fitted preprocessing pipeline
        test_metrics: Test metrics
        cv_metrics: CV metrics
        registry_info: Registry information
        config: Configuration object
        
    Returns:
        Path to deployment package
    """
    logger = get_run_logger()
    logger.info("🔵 Creating deployment package...")
    
    # Select final model
    if tuning_results and tuning_results['improvement'] > 0.01:
        model = tuning_results['best_model']
    else:
        model = training_results['best_model']
    
    deployment = ModelDeployment(config)
    package_path = deployment.create_package(
        model=model,
        preprocessor=preprocessor,
        model_name=training_results['best_model_name'],
        test_metrics=test_metrics,
        cv_metrics=cv_metrics,
        registry_info=registry_info
    )
    
    logger.info(f"✅ Deployment package created:")
    logger.info(f"   Path: {package_path}")
    
    return package_path


# ============================================
# MAIN PREFECT FLOW
# ============================================

@flow(
    name="NYC Taxi ML Pipeline",
    description="End-to-end ML pipeline for NYC taxi trip duration prediction",
    task_runner=ConcurrentTaskRunner(),
    flow_run_name=lambda: f"nyc-taxi-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    retries=0,  # Flow-level retries (tasks have their own retries)
    retry_delay_seconds=60,
    log_prints=True
)
def nyc_taxi_ml_pipeline(
    sample_size: Optional[int] = None,
    random_state: Optional[int] = None,
    skip_tuning: bool = False,
    skip_cv: bool = False,
    models: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Complete NYC Taxi ML Pipeline orchestrated with Prefect.
    
    This flow orchestrates the entire ML pipeline from data acquisition
    to model deployment with proper task dependencies, retry logic,
    caching, and monitoring.
    
    Args:
        sample_size: Number of samples to use (None = use default)
        random_state: Random seed (None = use default)
        skip_tuning: Skip hyperparameter tuning
        skip_cv: Skip cross-validation
        models: List of model names to train (None = train all)
        
    Returns:
        Dictionary with pipeline results and metadata
    """
    logger = get_run_logger()
    
    # ============================================
    # Pipeline Start
    # ============================================
    
    pipeline_start_time = time.time()
    
    logger.info("=" * 70)
    logger.info("🚀 NYC TAXI ML PIPELINE - PREFECT ORCHESTRATION")
    logger.info("=" * 70)
    
    # ============================================
    # Configuration
    # ============================================
    
    config = Config()
    
    # Override config with flow parameters
    if sample_size is not None:
        config.data.sample_size = sample_size
    if random_state is not None:
        config.model.random_state = random_state
    if skip_tuning:
        config.model.skip_tuning = True
    if skip_cv:
        config.model.skip_cv = True
    if models is not None:
        config.model.models_to_train = models
    
    logger.info(f"📋 Configuration:")
    logger.info(f"   Sample size: {config.data.sample_size:,}")
    logger.info(f"   Random state: {config.model.random_state}")
    logger.info(f"   Skip tuning: {config.model.skip_tuning}")
    logger.info(f"   Skip CV: {config.model.skip_cv}")
    
    # ============================================
    # Step 1: Data Acquisition
    # ============================================
    
    df_raw = acquire_data_task(config)
    
    # ============================================
    # Step 2: Data Preprocessing
    # ============================================
    
    df_clean = preprocess_data_task(df_raw, config)
    
    # ============================================
    # Step 3: Data Splitting
    # ============================================
    
    X_train, X_val, X_test, y_train, y_val, y_test = split_data_task(df_clean, config)
    
    # ============================================
    # Step 4: Feature Engineering
    # ============================================
    
    X_train_proc, X_val_proc, X_test_proc, preprocessor, feature_names = engineer_features_task(
        X_train, X_val, X_test, config
    )
    
    # ============================================
    # Step 5: Model Training
    # ============================================
    
    training_results = train_models_task(
        X_train_proc, y_train,
        X_val_proc, y_val,
        config, feature_names
    )
    
    # ============================================
    # Step 6: Hyperparameter Tuning (Optional)
    # ============================================
    
    tuning_results = tune_model_task(
        training_results,
        X_train_proc, y_train,
        X_val_proc, y_val,
        config
    )
    
    # ============================================
    # Step 7: Cross-Validation (Optional)
    # ============================================
    
    cv_metrics = cross_validate_task(
        training_results, tuning_results,
        X_train_proc, y_train,
        config
    )
    
    # ============================================
    # Step 8: Test Set Evaluation
    # ============================================
    
    test_metrics = evaluate_test_task(
        training_results, tuning_results,
        X_test_proc, y_test
    )
    
    # ============================================
    # Step 9: Model Registry
    # ============================================
    
    registry_info = register_model_task(
        training_results, tuning_results,
        cv_metrics, test_metrics,
        config
    )
    
    # ============================================
    # Step 10: Deployment Package
    # ============================================
    
    package_path = create_deployment_task(
        training_results, tuning_results,
        preprocessor, test_metrics, cv_metrics,
        registry_info, config
    )
    
    # ============================================
    # Pipeline Complete
    # ============================================
    
    pipeline_duration = time.time() - pipeline_start_time
    
    logger.info("=" * 70)
    logger.info("✅ PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"⏱️  Total duration: {pipeline_duration:.1f} seconds")
    logger.info(f"🏆 Best model: {training_results['best_model_name']}")
    logger.info(f"📊 Test R²: {test_metrics['test_r2']:.4f}")
    logger.info(f"📦 Deployment: {package_path}")
    logger.info(f"🔗 MLflow: models:/{config.mlflow.model_name}/Staging")
    
    # Create final summary artifact
    summary_md = f"""
# Pipeline Execution Summary

## ✅ Status: COMPLETE

## ⏱️ Execution Time
- **Total Duration**: {pipeline_duration:.1f} seconds
- **Started**: {datetime.now() - timedelta(seconds=pipeline_duration)}
- **Completed**: {datetime.now()}

## 📊 Model Performance
- **Algorithm**: {training_results['best_model_name']}
- **Test R²**: {test_metrics['test_r2']:.4f}
- **Test RMSE**: {test_metrics['test_rmse']:.2f} minutes
- **Test MAE**: {test_metrics['test_mae']:.2f} minutes

## 📦 Artifacts
- **Deployment Package**: `{package_path}`
- **MLflow Model**: `models:/{config.mlflow.model_name}/{registry_info['stage']}`
- **Model Version**: {registry_info['version']}

## 📈 Dataset Statistics
- **Training Samples**: {len(X_train):,}
- **Validation Samples**: {len(X_val):,}
- **Test Samples**: {len(X_test):,}
- **Features**: {len(feature_names)}

## 🎯 Next Steps
1. Review model performance in MLflow UI
2. Test deployment package locally
3. Promote model to Production if metrics are satisfactory
4. Monitor model performance in production
"""
    
    create_markdown_artifact(
        key="pipeline-summary",
        markdown=summary_md,
        description="Complete pipeline execution summary"
    )
    
    # Return results
    return {
        'status': 'success',
        'duration': pipeline_duration,
        'best_model': training_results['best_model_name'],
        'test_metrics': test_metrics,
        'registry_info': registry_info,
        'package_path': package_path,
        'mlflow_uri': f"models:/{config.mlflow.model_name}/{registry_info['stage']}"
    }


# ============================================
# SCHEDULED FLOWS
# ============================================

@flow(
    name="NYC Taxi Weekly Retrain",
    description="Weekly model retraining with production data"
)
def weekly_retrain_flow():
    """
    Weekly scheduled retraining with full dataset.
    """
    logger = get_run_logger()
    logger.info("📅 Starting weekly retraining...")
    
    # Run full pipeline without skipping anything
    results = nyc_taxi_ml_pipeline(
        sample_size=None,  # Use all data
        skip_tuning=False,
        skip_cv=False
    )
    
    logger.info("✅ Weekly retraining complete")
    return results


@flow(
    name="NYC Taxi Fast Validation",
    description="Quick validation run for testing pipeline"
)
def fast_validation_flow():
    """
    Fast validation run with small sample for testing.
    """
    logger = get_run_logger()
    logger.info("⚡ Starting fast validation...")
    
    # Run with small sample and skip expensive operations
    results = nyc_taxi_ml_pipeline(
        sample_size=10000,
        skip_tuning=True,
        skip_cv=True,
        models=["Linear Regression", "Random Forest"]
    )
    
    logger.info("✅ Fast validation complete")
    return results


if __name__ == "__main__":
    # Run the pipeline locally
    nyc_taxi_ml_pipeline()
