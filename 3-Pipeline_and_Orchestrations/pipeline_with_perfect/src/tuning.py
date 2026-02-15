"""
Hyperparameter Tuning Module
Handles model tuning using HalvingRandomSearchCV for efficiency
"""

import numpy as np
import time
from typing import Dict, Any, Optional
from sklearn.experimental import enable_halving_search_cv
from sklearn.model_selection import HalvingRandomSearchCV
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import r2_score
from prefect import task, get_run_logger
import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature

from config.config import config


def get_tuning_param_grids() -> Dict[str, Dict[str, list]]:
    """
    Get parameter grids for hyperparameter tuning.
    Compact grids for efficient tuning.
    
    Returns:
        Dict: Parameter grids for each model type
    """
    return {
        'Random Forest': {
            'n_estimators': [100, 200],
            'max_depth': [20, None],
            'min_samples_split': [2, 10],
            'min_samples_leaf': [1, 2],
            'max_features': ['sqrt', 0.5]
        },
        'Gradient Boosting': {
            'n_estimators': [100, 150, 200],
            'learning_rate': [0.05, 0.1, 0.15],
            'max_depth': [3, 5, 7],
            'subsample': [0.8, 1.0],
            'min_samples_split': [2, 5]
        }
    }


@task(name="tune_model")
def tune_model(
    model_name: str,
    base_model: Any,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    original_score: float
) -> Optional[Dict[str, Any]]:
    """
    Tune a model using HalvingRandomSearchCV.
    
    Args:
        model_name: Name of the model
        base_model: Base model instance (for cloning)
        X_train: Training features
        y_train: Training targets
        X_val: Validation features
        y_val: Validation targets
        original_score: Original validation R² score
        
    Returns:
        Dict: Tuning results or None if model not tunable
    """
    logger = get_run_logger()
    
    # Check if model is tunable
    tunable_models = ['Random Forest', 'Gradient Boosting']
    if model_name not in tunable_models:
        logger.info(f"⚠️  {model_name} is not tunable. Skipping...")
        return None
    
    logger.info(f"🔧 Tuning {model_name}...")
    
    param_grids = get_tuning_param_grids()
    param_grid = param_grids[model_name]
    
    with mlflow.start_run(run_name=f"{model_name}_tuned") as run:
        # Use HalvingRandomSearchCV for efficient tuning
        search = HalvingRandomSearchCV(
            base_model,
            param_grid,
            n_candidates=config.TUNING_N_CANDIDATES,
            min_resources=config.TUNING_MIN_RESOURCES,
            factor=config.TUNING_FACTOR,
            cv=config.CV_FOLDS,
            scoring='r2',
            n_jobs=config.N_JOBS,
            random_state=config.RANDOM_STATE,
            verbose=0
        )
        
        start_time = time.time()
        search.fit(X_train, y_train)
        tuning_time = time.time() - start_time
        
        # Evaluate on validation set
        y_val_pred = search.best_estimator_.predict(X_val)
        tuned_val_r2 = r2_score(y_val, y_val_pred)
        
        # Calculate improvement
        cv_improvement = search.best_score_ - original_score
        val_improvement = tuned_val_r2 - original_score
        
        # Log parameters
        mlflow.log_params(search.best_params_)
        
        # Log metrics
        mlflow.log_metrics({
            'best_cv_score': search.best_score_,
            'tuned_val_r2': tuned_val_r2,
            'cv_improvement': cv_improvement,
            'val_improvement': val_improvement,
            'tuning_time_seconds': tuning_time,
            'n_iterations': search.n_iterations_,
            'n_candidates_tested': len(search.cv_results_['params'])
        })
        
        # Log tags
        mlflow.set_tag('model_family', model_name)
        mlflow.set_tag('tuned', 'true')
        mlflow.set_tag('tuning_method', 'HalvingRandomSearchCV')
        mlflow.set_tag('data_leakage', 'none')
        
        # Log model (register only if significant improvement)
        signature = infer_signature(X_train, search.predict(X_train))
        
        if val_improvement > 0.01:  # >1% improvement
            mlflow.sklearn.log_model(
                sk_model=search.best_estimator_,
                artifact_path='tuned_model',
                signature=signature,
                registered_model_name=config.MLFLOW_MODEL_NAME
            )
            logger.info(f"   ✓ Model registered (significant improvement)")
        else:
            mlflow.sklearn.log_model(
                sk_model=search.best_estimator_,
                artifact_path='tuned_model',
                signature=signature
            )
        
        logger.info(f"   ✓ Best CV R²: {search.best_score_:.4f}")
        logger.info(f"   ✓ Tuned Val R²: {tuned_val_r2:.4f}")
        logger.info(f"   ✓ Improvement: +{val_improvement:.4f} ({val_improvement/original_score*100:.1f}%)")
        logger.info(f"   ✓ Tuning time: {tuning_time:.1f}s")
        logger.info(f"   ✓ Best params: {search.best_params_}")
        
        return {
            'model': search.best_estimator_,
            'run_id': run.info.run_id,
            'model_name': model_name,
            'best_params': search.best_params_,
            'cv_score': search.best_score_,
            'val_r2': tuned_val_r2,
            'improvement': val_improvement,
            'tuning_time': tuning_time
        }


@task(name="tune_best_model")
def tune_best_model(
    best_result: Dict[str, Any],
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray
) -> Optional[Dict[str, Any]]:
    """
    Tune the best model if it's tunable.
    
    Args:
        best_result: Best model result from training
        X_train: Training features
        y_train: Training targets
        X_val: Validation features
        y_val: Validation targets
        
    Returns:
        Dict: Tuning result or None
    """
    logger = get_run_logger()
    logger.info("🎯 Starting hyperparameter tuning for best model...")
    logger.info("=" * 70)
    
    model_name = best_result['model_name']
    original_score = best_result['metrics']['val_r2']
    
    # Create a fresh instance of the model for tuning
    if model_name == 'Random Forest':
        base_model = RandomForestRegressor(
            random_state=config.RANDOM_STATE,
            n_jobs=config.N_JOBS
        )
    elif model_name == 'Gradient Boosting':
        base_model = GradientBoostingRegressor(
            random_state=config.RANDOM_STATE
        )
    else:
        logger.info(f"⚠️  {model_name} is not tunable. Skipping tuning phase.")
        return None
    
    tuning_result = tune_model(
        model_name=model_name,
        base_model=base_model,
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        original_score=original_score
    )
    
    if tuning_result:
        logger.info(f"\n✅ Tuning complete!")
        logger.info(f"   Original Val R²: {original_score:.4f}")
        logger.info(f"   Tuned Val R²:    {tuning_result['val_r2']:.4f}")
        logger.info(f"   Improvement:     +{tuning_result['improvement']:.4f}")
        
        # Decide if tuned model is better
        if tuning_result['improvement'] > 0:
            logger.info(f"\n🏆 TUNED MODEL IS BETTER - Using tuned version")
            return tuning_result
        else:
            logger.info(f"\n⚠️  Original model performs better - Keeping original")
            return None
    
    return None


@task(name="compare_tuning_results")
def compare_tuning_results(
    original_result: Dict[str, Any],
    tuning_result: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compare original and tuned models and select the best.
    
    Args:
        original_result: Original training result
        tuning_result: Tuning result (or None)
        
    Returns:
        Dict: Best model result
    """
    logger = get_run_logger()
    
    if tuning_result is None:
        logger.info("📊 No tuning performed - using original model")
        return original_result
    
    original_score = original_result['metrics']['val_r2']
    tuned_score = tuning_result['val_r2']
    
    logger.info("\n📊 TUNING COMPARISON:")
    logger.info(f"   Original Model: {original_score:.4f}")
    logger.info(f"   Tuned Model:    {tuned_score:.4f}")
    logger.info(f"   Difference:     {tuned_score - original_score:+.4f}")
    
    if tuned_score > original_score:
        logger.info("\n🏆 WINNER: Tuned Model")
        # Update the result structure to match training output
        return {
            'model': tuning_result['model'],
            'run_id': tuning_result['run_id'],
            'model_name': tuning_result['model_name'],
            'metrics': {
                'val_r2': tuning_result['val_r2'],
                'train_r2': original_result['metrics']['train_r2'],
                'val_rmse': original_result['metrics']['val_rmse'],
                'val_mae': original_result['metrics']['val_mae'],
                'train_rmse': original_result['metrics']['train_rmse'],
                'train_mae': original_result['metrics']['train_mae'],
                'overfitting_gap': original_result['metrics']['overfitting_gap'],
                'training_time': original_result['metrics']['training_time']
            }
        }
    else:
        logger.info("\n🏆 WINNER: Original Model")
        return original_result