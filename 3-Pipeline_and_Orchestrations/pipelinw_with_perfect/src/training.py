"""
Model Training Module
Handles model training with MLflow tracking
"""

import numpy as np
import time
from typing import Dict, Any
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from prefect import task, get_run_logger
import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature

from config.config import config


def get_model_portfolio() -> Dict[str, Any]:
    """
    Get the portfolio of models to train.
    
    Returns:
        Dict: Dictionary of model name -> model instance
    """
    return {
        'Linear Regression': LinearRegression(),
        'Ridge': Ridge(
            random_state=config.RANDOM_STATE,
            alpha=config.RIDGE_ALPHA
        ),
        'Lasso': Lasso(
            random_state=config.RANDOM_STATE,
            alpha=config.LASSO_ALPHA,
            max_iter=5000
        ),
        'Random Forest': RandomForestRegressor(
            random_state=config.RANDOM_STATE,
            n_jobs=config.N_JOBS,
            n_estimators=config.RF_N_ESTIMATORS,
            max_depth=config.RF_MAX_DEPTH,
            min_samples_split=config.RF_MIN_SAMPLES_SPLIT
        ),
        'Gradient Boosting': GradientBoostingRegressor(
            random_state=config.RANDOM_STATE,
            n_estimators=config.GB_N_ESTIMATORS,
            learning_rate=config.GB_LEARNING_RATE,
            max_depth=config.GB_MAX_DEPTH
        )
    }


@task(name="train_single_model")
def train_single_model(
    model: Any,
    model_name: str,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list
) -> Dict[str, Any]:
    """
    Train a single model and log to MLflow.
    
    Args:
        model: Scikit-learn model instance
        model_name: Name of the model
        X_train: Training features
        y_train: Training targets
        X_val: Validation features
        y_val: Validation targets
        feature_names: List of feature names
        
    Returns:
        Dict: Training results including metrics, model, and run_id
    """
    logger = get_run_logger()
    logger.info(f"🎯 Training {model_name}...")
    
    with mlflow.start_run(run_name=model_name) as run:
        # Train model
        start_time = time.time()
        model.fit(X_train, y_train)
        training_time = time.time() - start_time
        
        # Predictions
        y_train_pred = model.predict(X_train)
        y_val_pred = model.predict(X_val)
        
        # Calculate metrics
        metrics = {
            'train_r2': r2_score(y_train, y_train_pred),
            'val_r2': r2_score(y_val, y_val_pred),
            'train_rmse': np.sqrt(mean_squared_error(y_train, y_train_pred)),
            'val_rmse': np.sqrt(mean_squared_error(y_val, y_val_pred)),
            'train_mae': mean_absolute_error(y_train, y_train_pred),
            'val_mae': mean_absolute_error(y_val, y_val_pred),
            'training_time': training_time,
            'overfitting_gap': r2_score(y_train, y_train_pred) - r2_score(y_val, y_val_pred)
        }
        
        # Log parameters
        try:
            params = model.get_params()
            # Convert callable objects to strings
            params = {k: str(v) if callable(v) else v for k, v in params.items()}
            mlflow.log_params(params)
        except Exception as e:
            logger.warning(f"Could not log all parameters: {e}")
        
        # Log metrics
        mlflow.log_metrics(metrics)
        
        # Log tags
        mlflow.set_tag('model_family', model_name)
        mlflow.set_tag('data_leakage', 'none')
        mlflow.set_tag('optimization', 'fast_mode')
        mlflow.set_tag('pipeline_version', '1.0')
        
        # Log dataset info
        mlflow.log_param('train_samples', X_train.shape[0])
        mlflow.log_param('val_samples', X_val.shape[0])
        mlflow.log_param('n_features', X_train.shape[1])
        
        # Infer signature and log model with auto-registration
        signature = infer_signature(X_train, y_train_pred)
        
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path='model',
            signature=signature,
            registered_model_name=config.MLFLOW_MODEL_NAME
        )
        
        logger.info(f"   ✓ Val R²: {metrics['val_r2']:.4f} | MAE: {metrics['val_mae']:.2f} min | Time: {training_time:.1f}s")
        
        return {
            'metrics': metrics,
            'model': model,
            'run_id': run.info.run_id,
            'model_name': model_name
        }


@task(name="train_all_models")
def train_all_models(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list
) -> Dict[str, Dict[str, Any]]:
    """
    Train all models in the portfolio.
    
    Args:
        X_train: Training features
        y_train: Training targets
        X_val: Validation features
        y_val: Validation targets
        feature_names: List of feature names
        
    Returns:
        Dict: Results for all models
    """
    logger = get_run_logger()
    logger.info("🚀 Training model portfolio...")
    logger.info("=" * 70)
    
    models = get_model_portfolio()
    results = {}
    
    for name, model in models.items():
        try:
            result = train_single_model(
                model=model,
                model_name=name,
                X_train=X_train,
                y_train=y_train,
                X_val=X_val,
                y_val=y_val,
                feature_names=feature_names
            )
            results[name] = result
            
        except Exception as e:
            logger.error(f"   ❌ Failed to train {name}: {str(e)[:100]}")
            continue
    
    logger.info(f"\n✅ Trained {len(results)}/{len(models)} models successfully")
    
    return results


@task(name="select_best_model")
def select_best_model(results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Select the best model based on validation R².
    
    Args:
        results: Dictionary of training results
        
    Returns:
        Dict: Best model information
    """
    logger = get_run_logger()
    logger.info("🏆 Selecting best model...")
    
    # Extract metrics for comparison
    model_scores = {
        name: result['metrics']['val_r2']
        for name, result in results.items()
    }
    
    # Find best model
    best_name = max(model_scores, key=model_scores.get)
    best_result = results[best_name]
    
    logger.info(f"   Best model: {best_name}")
    logger.info(f"   Val R²: {best_result['metrics']['val_r2']:.4f}")
    logger.info(f"   Val MAE: {best_result['metrics']['val_mae']:.2f} minutes")
    logger.info(f"   Run ID: {best_result['run_id'][:8]}...")
    
    # Log comparison
    logger.info("\n📊 Model Comparison (Val R²):")
    for name, score in sorted(model_scores.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"   {name:<25} {score:.4f}")
    
    return best_result