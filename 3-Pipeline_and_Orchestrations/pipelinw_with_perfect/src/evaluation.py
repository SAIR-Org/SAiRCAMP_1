"""
Model Evaluation Module
Handles model evaluation on test set and cross-validation
"""

import numpy as np
from typing import Dict, Any
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from prefect import task, get_run_logger
import mlflow


@task(name="evaluate_on_test_set")
def evaluate_on_test_set(
    model: Any,
    X_test: np.ndarray,
    y_test: np.ndarray,
    run_id: str
) -> Dict[str, float]:
    """
    Evaluate model on the test set.
    
    Args:
        model: Trained model
        X_test: Test features
        y_test: Test targets
        run_id: MLflow run ID to log metrics to
        
    Returns:
        Dict: Test metrics
    """
    logger = get_run_logger()
    logger.info("🔬 Evaluating on test set...")
    
    # Make predictions
    y_test_pred = model.predict(X_test)
    
    # Calculate metrics
    test_metrics = {
        'test_r2': r2_score(y_test, y_test_pred),
        'test_rmse': np.sqrt(mean_squared_error(y_test, y_test_pred)),
        'test_mae': mean_absolute_error(y_test, y_test_pred)
    }
    
    logger.info(f"   • R² Score: {test_metrics['test_r2']:.4f} ({test_metrics['test_r2']*100:.1f}%)")
    logger.info(f"   • RMSE: {test_metrics['test_rmse']:.2f} minutes")
    logger.info(f"   • MAE: {test_metrics['test_mae']:.2f} minutes")
    
    # Log to MLflow
    with mlflow.start_run(run_id=run_id):
        mlflow.log_metrics(test_metrics)
        mlflow.set_tag('final_model', 'true')
        mlflow.set_tag('deployment_ready', 'true')
    
    logger.info(f"✅ Test metrics logged to run: {run_id[:8]}...")
    
    return test_metrics


@task(name="cross_validate_model")
def cross_validate_model(
    model: Any,
    X_train: np.ndarray,
    y_train: np.ndarray,
    run_id: str,
    cv: int = 3
) -> Dict[str, float]:
    """
    Perform cross-validation on the training set.
    
    Args:
        model: Trained model
        X_train: Training features
        y_train: Training targets
        run_id: MLflow run ID to log metrics to
        cv: Number of CV folds
        
    Returns:
        Dict: CV metrics
    """
    logger = get_run_logger()
    logger.info(f"🔬 Running {cv}-fold cross-validation...")
    
    # Perform CV
    cv_scores = cross_val_score(
        model, X_train, y_train,
        cv=cv,
        scoring='r2',
        n_jobs=-1
    )
    
    cv_metrics = {
        'cv_r2_mean': cv_scores.mean(),
        'cv_r2_std': cv_scores.std(),
        'cv_r2_min': cv_scores.min(),
        'cv_r2_max': cv_scores.max()
    }
    
    logger.info(f"   CV R²: {cv_metrics['cv_r2_mean']:.4f} ± {cv_metrics['cv_r2_std']:.4f}")
    logger.info(f"   Range: [{cv_metrics['cv_r2_min']:.4f}, {cv_metrics['cv_r2_max']:.4f}]")
    
    # Log to MLflow
    with mlflow.start_run(run_id=run_id):
        mlflow.log_metrics(cv_metrics)
    
    logger.info(f"✅ CV metrics logged to run: {run_id[:8]}...")
    
    return cv_metrics


@task(name="generate_evaluation_report")
def generate_evaluation_report(
    model_name: str,
    train_metrics: Dict[str, float],
    test_metrics: Dict[str, float],
    cv_metrics: Dict[str, float]
) -> str:
    """
    Generate a comprehensive evaluation report.
    
    Args:
        model_name: Name of the model
        train_metrics: Training/validation metrics
        test_metrics: Test metrics
        cv_metrics: Cross-validation metrics
        
    Returns:
        str: Formatted report
    """
    logger = get_run_logger()
    
    report = f"""
╔════════════════════════════════════════════════════════════════╗
║                    MODEL EVALUATION REPORT                     ║
╚════════════════════════════════════════════════════════════════╝

📊 MODEL: {model_name}

┌─ TRAINING METRICS ─────────────────────────────────────────────┐
│ • R² Score:  {train_metrics['train_r2']:.4f}                    
│ • RMSE:      {train_metrics['train_rmse']:.2f} minutes          
│ • MAE:       {train_metrics['train_mae']:.2f} minutes           
└────────────────────────────────────────────────────────────────┘

┌─ VALIDATION METRICS ───────────────────────────────────────────┐
│ • R² Score:  {train_metrics['val_r2']:.4f}                      
│ • RMSE:      {train_metrics['val_rmse']:.2f} minutes            
│ • MAE:       {train_metrics['val_mae']:.2f} minutes             
│ • Overfit:   {train_metrics['overfitting_gap']:.4f}             
└────────────────────────────────────────────────────────────────┘

┌─ CROSS-VALIDATION METRICS ─────────────────────────────────────┐
│ • CV R²:     {cv_metrics['cv_r2_mean']:.4f} ± {cv_metrics['cv_r2_std']:.4f}
│ • Range:     [{cv_metrics['cv_r2_min']:.4f}, {cv_metrics['cv_r2_max']:.4f}]
└────────────────────────────────────────────────────────────────┘

┌─ TEST METRICS (FINAL) ─────────────────────────────────────────┐
│ • R² Score:  {test_metrics['test_r2']:.4f} ({test_metrics['test_r2']*100:.1f}%)
│ • RMSE:      {test_metrics['test_rmse']:.2f} minutes            
│ • MAE:       {test_metrics['test_mae']:.2f} minutes             
└────────────────────────────────────────────────────────────────┘

✅ MODEL PERFORMANCE: {'EXCELLENT' if test_metrics['test_r2'] > 0.85 else 'GOOD' if test_metrics['test_r2'] > 0.75 else 'ACCEPTABLE'}
✅ GENERALIZATION: {'GOOD' if train_metrics['overfitting_gap'] < 0.05 else 'MODERATE' if train_metrics['overfitting_gap'] < 0.10 else 'NEEDS ATTENTION'}
✅ DEPLOYMENT READY: {'YES' if test_metrics['test_r2'] > 0.70 else 'NEEDS IMPROVEMENT'}
"""
    
    logger.info(report)
    
    return report