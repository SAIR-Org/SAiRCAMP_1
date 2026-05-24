"""
Model training module for NYC Taxi ML Pipeline
Handles model training, evaluation, and MLflow tracking
"""
import time
import numpy as np
import logging
from typing import Dict, Tuple, List, Optional
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.experimental import enable_halving_search_cv
from sklearn.model_selection import HalvingRandomSearchCV, cross_val_score
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from mlflow import MlflowClient

from config.config import ModelConfig, MLflowConfig
from src.utils.retry_utils import retry_with_backoff, RetryableError


logger = logging.getLogger(__name__)


class ModelTrainer:
    """Handle model training and MLflow tracking."""
    
    def __init__(
        self,
        model_config: ModelConfig,
        mlflow_config: MLflowConfig,
        client: MlflowClient
    ):
        """
        Initialize model trainer.
        
        Args:
            model_config: Model configuration
            mlflow_config: MLflow configuration
            client: MLflow client
        """
        self.model_config = model_config
        self.mlflow_config = mlflow_config
        self.client = client
        self.models = self._build_model_portfolio()
        self.results = {}
        self.trained_models = {}
        self.run_ids = {}
    
    def _build_model_portfolio(self) -> Dict:
        """
        Build portfolio of models to train.
        
        Returns:
            Dictionary of model instances
        """
        logger.info("🎯 Building model portfolio...")
        
        models = {
            'Linear Regression': LinearRegression(),
            'Ridge': Ridge(
                random_state=self.model_config.random_state,
                alpha=self.model_config.ridge_alpha
            ),
            'Lasso': Lasso(
                random_state=self.model_config.random_state,
                alpha=self.model_config.lasso_alpha,
                max_iter=5000
            ),
            'Random Forest': RandomForestRegressor(
                random_state=self.model_config.random_state,
                n_jobs=self.model_config.n_jobs,
                n_estimators=self.model_config.rf_n_estimators,
                max_depth=self.model_config.rf_max_depth,
                min_samples_split=self.model_config.rf_min_samples_split
            ),
            'Gradient Boosting': GradientBoostingRegressor(
                random_state=self.model_config.random_state,
                n_estimators=self.model_config.gb_n_estimators,
                learning_rate=self.model_config.gb_learning_rate,
                max_depth=self.model_config.gb_max_depth
            )
        }
        
        # Filter by configuration
        if self.model_config.models_to_train:
            models = {
                k: v for k, v in models.items()
                if k in self.model_config.models_to_train
            }
        
        logger.info(f"✅ Model portfolio: {len(models)} models")
        for name in models.keys():
            logger.info(f"   • {name}")
        
        return models
    
    @retry_with_backoff(
        max_retries=2,
        delay=5,
        exceptions=(Exception,)
    )
    def train_single_model(
        self,
        model,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        model_name: str
    ) -> Tuple[Dict, any, str]:
        """
        Train single model with MLflow tracking.
        
        Args:
            model: Model instance
            X_train: Training features
            y_train: Training target
            X_val: Validation features
            y_val: Validation target
            model_name: Model name
            
        Returns:
            Tuple of (metrics, trained_model, run_id)
        """
        with mlflow.start_run(run_name=model_name) as run:
            logger.info(f"   Training {model_name}...")
            
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
                params = {k: str(v) if callable(v) else v for k, v in params.items()}
                mlflow.log_params(params)
            except Exception as e:
                logger.warning(f"   Could not log parameters: {str(e)}")
            
            # Log metrics
            mlflow.log_metrics(metrics)
            
            # Log tags
            mlflow.set_tag('model_family', model_name)
            mlflow.set_tag('data_leakage', 'none')
            mlflow.set_tag('optimization', 'fast_mode')
            
            # Log dataset info
            mlflow.log_param('train_samples', X_train.shape[0])
            mlflow.log_param('val_samples', X_val.shape[0])
            mlflow.log_param('features', X_train.shape[1])
            
            # Infer signature and log model
            signature = infer_signature(X_train, y_train_pred)
            
            mlflow.sklearn.log_model(
                sk_model=model,
                artifact_path='model',
                signature=signature,
                registered_model_name=self.mlflow_config.model_name
            )
            
            logger.info(f"   ✓ {model_name} - Val R²: {metrics['val_r2']:.4f}, Time: {training_time:.1f}s")
            
            return metrics, model, run.info.run_id
    
    def train_all_models(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray
    ) -> Dict[str, str]:
        """
        Train all models in portfolio.
        
        Args:
            X_train: Training features
            y_train: Training target
            X_val: Validation features
            y_val: Validation target
            
        Returns:
            Dictionary mapping model names to run IDs
        """
        logger.info("🚀 Training all models...")
        
        for name, model in self.models.items():
            try:
                metrics, trained_model, run_id = self.train_single_model(
                    model, X_train, y_train, X_val, y_val, name
                )
                self.results[name] = metrics
                self.trained_models[name] = trained_model
                self.run_ids[name] = run_id
                
            except Exception as e:
                logger.error(f"   ❌ {name} failed: {str(e)}")
        
        logger.info(f"✅ Trained {len(self.results)}/{len(self.models)} models successfully")
        
        return self.run_ids
    
    def select_best_model(self) -> Tuple[str, any, str]:
        """
        Select best model based on validation R².
        
        Returns:
            Tuple of (best_model_name, best_model, best_run_id)
        """
        logger.info("🏆 Selecting best model...")
        
        if not self.results:
            raise ValueError("No models trained")
        
        # Sort by validation R²
        sorted_models = sorted(
            self.results.items(),
            key=lambda x: x[1]['val_r2'],
            reverse=True
        )
        
        best_model_name = sorted_models[0][0]
        best_model = self.trained_models[best_model_name]
        best_run_id = self.run_ids[best_model_name]
        best_metrics = self.results[best_model_name]
        
        logger.info(f"✅ Best model: {best_model_name}")
        logger.info(f"   Val R²: {best_metrics['val_r2']:.4f}")
        logger.info(f"   Val MAE: {best_metrics['val_mae']:.2f} minutes")
        logger.info(f"   Run ID: {best_run_id[:8]}")
        
        # Tag best run
        self.client.set_tag(best_run_id, "best_model", "true")
        self.client.set_tag(best_run_id, "selection_criteria", "val_r2")
        
        return best_model_name, best_model, best_run_id
    
    @retry_with_backoff(
        max_retries=2,
        delay=5,
        exceptions=(Exception,)
    )
    def tune_model(
        self,
        model_name: str,
        base_model,
        X_train: np.ndarray,
        y_train: np.ndarray,
        original_score: float
    ) -> Tuple[any, str, float]:
        """
        Tune model using HalvingRandomSearchCV.
        
        Args:
            model_name: Model name
            base_model: Base model instance
            X_train: Training features
            y_train: Training target
            original_score: Original validation R²
            
        Returns:
            Tuple of (tuned_model, run_id, best_score)
        """
        logger.info(f"🔧 Tuning {model_name}...")
        
        # Parameter grids
        param_grids = {
            'Random Forest': {
                'n_estimators': [100, 200],
                'max_depth': [20, None],
                'min_samples_split': [2, 10],
                'min_samples_leaf': [1, 2]
            },
            'Gradient Boosting': {
                'n_estimators': [100, 150],
                'learning_rate': [0.05, 0.1],
                'max_depth': [3, 5],
                'subsample': [0.8, 1.0]
            }
        }
        
        if model_name not in param_grids:
            logger.warning(f"   {model_name} not tunable, skipping")
            return base_model, None, original_score
        
        with mlflow.start_run(run_name=f"{model_name}_tuned") as run:
            # HalvingRandomSearchCV
            search = HalvingRandomSearchCV(
                base_model,
                param_grids[model_name],
                n_candidates=self.model_config.tuning_n_candidates,
                min_resources=self.model_config.tuning_min_resources,
                factor=self.model_config.tuning_factor,
                cv=self.model_config.tuning_cv_folds,
                scoring='r2',
                n_jobs=self.model_config.n_jobs,
                random_state=self.model_config.random_state,
                verbose=0
            )
            
            start_time = time.time()
            search.fit(X_train, y_train)
            tuning_time = time.time() - start_time
            
            improvement = search.best_score_ - original_score
            
            # Log results
            mlflow.log_params(search.best_params_)
            mlflow.log_metrics({
                'best_cv_score': search.best_score_,
                'improvement': improvement,
                'tuning_time_seconds': tuning_time
            })
            
            # Log model
            signature = infer_signature(X_train, search.predict(X_train))
            
            if improvement > self.mlflow_config.min_r2_improvement:
                mlflow.sklearn.log_model(
                    sk_model=search.best_estimator_,
                    artifact_path='tuned_model',
                    signature=signature,
                    registered_model_name=self.mlflow_config.model_name
                )
                logger.info(f"   ✓ Tuned model registered (improvement: +{improvement:.4f})")
            else:
                mlflow.sklearn.log_model(
                    sk_model=search.best_estimator_,
                    artifact_path='tuned_model',
                    signature=signature
                )
                logger.info(f"   ✓ Tuned model saved (improvement: +{improvement:.4f}, below threshold)")
            
            logger.info(f"   Best CV R²: {search.best_score_:.4f}")
            logger.info(f"   Tuning time: {tuning_time:.1f}s")
            
            return search.best_estimator_, run.info.run_id, search.best_score_
    
    def cross_validate_model(
        self,
        model,
        X_train: np.ndarray,
        y_train: np.ndarray,
        run_id: str
    ) -> np.ndarray:
        """
        Cross-validate model and log results.
        
        Args:
            model: Model to cross-validate
            X_train: Training features
            y_train: Training target
            run_id: MLflow run ID
            
        Returns:
            Array of CV scores
        """
        logger.info("🔬 Cross-validating best model...")
        
        cv_scores = cross_val_score(
            model,
            X_train,
            y_train,
            cv=self.model_config.cv_folds,
            scoring='r2',
            n_jobs=self.model_config.n_jobs
        )
        
        logger.info(f"   CV R²: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
        
        # Log to MLflow
        with mlflow.start_run(run_id=run_id):
            mlflow.log_metric('cv_r2_mean', cv_scores.mean())
            mlflow.log_metric('cv_r2_std', cv_scores.std())
        
        return cv_scores
    
    def evaluate_on_test(
        self,
        model,
        X_test: np.ndarray,
        y_test: np.ndarray,
        run_id: str
    ) -> Dict[str, float]:
        """
        Evaluate model on test set.
        
        Args:
            model: Trained model
            X_test: Test features
            y_test: Test target
            run_id: MLflow run ID
            
        Returns:
            Dictionary of test metrics
        """
        logger.info("🔬 Evaluating on test set...")
        
        y_test_pred = model.predict(X_test)
        
        test_metrics = {
            'test_r2': r2_score(y_test, y_test_pred),
            'test_rmse': np.sqrt(mean_squared_error(y_test, y_test_pred)),
            'test_mae': mean_absolute_error(y_test, y_test_pred)
        }
        
        logger.info(f"   Test R²: {test_metrics['test_r2']:.4f}")
        logger.info(f"   Test RMSE: {test_metrics['test_rmse']:.2f} minutes")
        logger.info(f"   Test MAE: {test_metrics['test_mae']:.2f} minutes")
        
        # Log to MLflow
        with mlflow.start_run(run_id=run_id):
            mlflow.log_metrics(test_metrics)
            mlflow.set_tag('final_model', 'true')
            mlflow.set_tag('deployment_ready', 'true')
        
        return test_metrics