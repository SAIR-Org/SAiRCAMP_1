"""Train 6 models, tune the winner, evaluate on test set — all tracked in MLflow."""
import time
import numpy as np
import logging
from typing import Dict, Tuple, Optional
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from xgboost import XGBRegressor
from sklearn.experimental import enable_halving_search_cv  # noqa: F401
from sklearn.model_selection import HalvingRandomSearchCV
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from mlflow import MlflowClient

from config.config import ModelConfig, MLflowConfig


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Standalone function — used by flow.py to build the model portfolio without
# instantiating ModelTrainer (avoids building all 5 models just to get names).
# ─────────────────────────────────────────────────────────────────────────────
def build_model_portfolio(config: ModelConfig) -> Dict:
    """
    Build the model portfolio as a plain dict.

    Exposed as a module-level function so flow.py can iterate models
    and submit each training as a separate Prefect task.
    """
    models = {
        'Linear Regression': LinearRegression(),
        'Ridge': Ridge(
            random_state=config.random_state,
            alpha=config.ridge_alpha
        ),
        'Lasso': Lasso(
            random_state=config.random_state,
            alpha=config.lasso_alpha,
            max_iter=5000
        ),
        'Random Forest': RandomForestRegressor(
            random_state=config.random_state,
            n_jobs=config.n_jobs,
            n_estimators=config.rf_n_estimators,
            max_depth=config.rf_max_depth,
            min_samples_split=config.rf_min_samples_split
        ),
        'Gradient Boosting': GradientBoostingRegressor(
            random_state=config.random_state,
            n_estimators=config.gb_n_estimators,
            learning_rate=config.gb_learning_rate,
            max_depth=config.gb_max_depth
        ),
        'XGBoost': XGBRegressor(
            random_state=config.random_state,
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            tree_method='hist',
            n_jobs=config.n_jobs,
            verbosity=0
        ),
    }

    if config.models_to_train:
        models = {k: v for k, v in models.items() if k in config.models_to_train}

    return models


class ModelTrainer:
    """Handle model training and MLflow tracking."""

    def __init__(self, model_config: ModelConfig, mlflow_config: MLflowConfig, client: MlflowClient):
        self.model_config = model_config
        self.mlflow_config = mlflow_config
        self.client = client

    def train_single_model(
        self,
        model,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        model_name: str
    ) -> Tuple[Dict, object, str]:
        """
        Train a single model with MLflow tracking.

        Retries are handled by Prefect @task(retries=1) in flow.py —
        no manual retry decorator needed here.
        """
        with mlflow.start_run(run_name=model_name) as run:
            logger.info(f"   Training {model_name}...")

            start_time = time.time()
            model.fit(X_train, y_train)
            training_time = time.time() - start_time

            y_train_pred = model.predict(X_train)
            y_val_pred = model.predict(X_val)

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

            try:
                params = model.get_params()
                params = {k: str(v) if callable(v) else v for k, v in params.items()}
                mlflow.log_params(params)
            except Exception as e:
                logger.warning(f"   Could not log parameters: {str(e)}")

            mlflow.log_metrics(metrics)
            mlflow.set_tag('model_family', model_name)
            mlflow.set_tag('data_leakage', 'none')
            mlflow.set_tag('orchestrator', 'prefect')
            mlflow.log_param('train_samples', X_train.shape[0])
            mlflow.log_param('val_samples', X_val.shape[0])
            mlflow.log_param('features', X_train.shape[1])

            signature = infer_signature(X_train, y_train_pred)
            mlflow.sklearn.log_model(
                sk_model=model,
                name='model',
                signature=signature,
                registered_model_name=self.mlflow_config.model_name
            )

            logger.info(f"   ✓ {model_name} — Val R²: {metrics['val_r2']:.4f}, "
                        f"MAE: {metrics['val_mae']:.2f} min, Time: {training_time:.1f}s")

            return metrics, model, run.info.run_id

    def tune_model(
        self,
        model_name: str,
        base_model,
        X_train: np.ndarray,
        y_train: np.ndarray,
        original_score: float
    ) -> Tuple[object, str, float]:
        """
        Tune model using HalvingRandomSearchCV.

        Retries are handled by Prefect @task in flow.py.
        """
        logger.info(f"🔧 Tuning {model_name}...")

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
            },
            'XGBoost': {
                'n_estimators': [300, 500],
                'learning_rate': [0.03, 0.05],
                'max_depth': [5, 6, 8],
                'subsample': [0.8, 1.0],
                'colsample_bytree': [0.8, 1.0],
            }
        }

        if model_name not in param_grids:
            logger.warning(f"   {model_name} not tunable, skipping")
            return base_model, None, original_score

        with mlflow.start_run(run_name=f"{model_name}_tuned") as run:
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

            mlflow.log_params(search.best_params_)
            mlflow.log_metrics({
                'best_cv_score': search.best_score_,
                'improvement': improvement,
                'tuning_time_seconds': tuning_time
            })
            mlflow.set_tag('tuned', 'true')
            mlflow.set_tag('orchestrator', 'prefect')

            signature = infer_signature(X_train, search.predict(X_train))

            if improvement > self.mlflow_config.min_r2_improvement:
                mlflow.sklearn.log_model(
                    sk_model=search.best_estimator_,
                    name='tuned_model',
                    signature=signature,
                    registered_model_name=self.mlflow_config.model_name
                )
                logger.info(f"   ✓ Tuned model registered (improvement: +{improvement:.4f})")
            else:
                mlflow.sklearn.log_model(
                    sk_model=search.best_estimator_,
                    name='tuned_model',
                    signature=signature
                )

            logger.info(f"   Best CV R²: {search.best_score_:.4f}, Time: {tuning_time:.1f}s")

            return search.best_estimator_, run.info.run_id, search.best_score_

    def evaluate_on_test(self, model, X_test, y_test, run_id) -> Dict[str, float]:
        """Evaluate model on the held-out test set."""
        logger.info("🔬 Evaluating on test set...")

        y_test_pred = model.predict(X_test)

        test_metrics = {
            'test_r2': r2_score(y_test, y_test_pred),
            'test_rmse': np.sqrt(mean_squared_error(y_test, y_test_pred)),
            'test_mae': mean_absolute_error(y_test, y_test_pred)
        }

        logger.info(f"   Test R²:   {test_metrics['test_r2']:.4f}")
        logger.info(f"   Test RMSE: {test_metrics['test_rmse']:.2f} min")
        logger.info(f"   Test MAE:  {test_metrics['test_mae']:.2f} min")

        with mlflow.start_run(run_id=run_id):
            mlflow.log_metrics(test_metrics)
            mlflow.set_tag('final_model', 'true')
            mlflow.set_tag('deployment_ready', 'true')

        return test_metrics
