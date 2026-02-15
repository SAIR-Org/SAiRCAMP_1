"""
Main ML Pipeline for NYC Taxi Trip Duration Prediction
Orchestrates the complete training pipeline with MLflow integration
"""
import os
import sys
import warnings
import mlflow
from mlflow import MlflowClient
import logging
from typing import Tuple
import numpy as np
from sklearn.model_selection import train_test_split

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.config import Config
from src.utils.logging_utils import setup_logger, log_section, log_metrics, log_config
from src.utils.retry_utils import retry_with_backoff, RetryableError
from src.data.data_acquisition import DataAcquisition
from src.data.data_preprocessing import DataPreprocessor
from src.features.feature_engineering import build_preprocessor
from src.models.model_training import ModelTrainer
from src.models.model_registry import ModelRegistry
from src.models.model_deployment import ModelDeployment


warnings.filterwarnings('ignore')


class NYCTaxiMLPipeline:
    """Main ML pipeline orchestrator."""
    
    def __init__(self, config: Config):
        """
        Initialize pipeline.
        
        Args:
            config: Pipeline configuration
        """
        self.config = config
        
        # Setup logging
        log_file = os.path.join(config.paths.log_dir, config.log.log_file)
        self.logger = setup_logger(
            name='nyc_taxi_pipeline',
            log_file=log_file,
            log_level=config.log.log_level,
            log_format=config.log.log_format,
            max_bytes=config.log.max_bytes,
            backup_count=config.log.backup_count
        )
        
        # Setup MLflow
        self._setup_mlflow()
        
        # Initialize components
        self.data_acquisition = DataAcquisition(config.data)
        self.data_preprocessor = DataPreprocessor(config.data)
        self.model_trainer = ModelTrainer(config.model, config.mlflow, self.mlflow_client)
        self.model_registry = ModelRegistry(config.mlflow, self.mlflow_client)
        self.model_deployment = ModelDeployment(config.paths.model_dir)
        
        # Storage for pipeline artifacts
        self.df_raw = None
        self.X = None
        self.y = None
        self.X_train = None
        self.X_val = None
        self.X_test = None
        self.y_train = None
        self.y_val = None
        self.y_test = None
        self.X_train_processed = None
        self.X_val_processed = None
        self.X_test_processed = None
        self.preprocessor = None
        self.feature_names = None
        self.best_model_name = None
        self.best_model = None
        self.best_run_id = None
        self.test_metrics = None
        self.cv_scores = None
    
    def _setup_mlflow(self):
        """Setup MLflow tracking and registry."""
        tracking_uri = f"sqlite:///{self.config.paths.mlflow_db_path}"
        mlflow.set_tracking_uri(tracking_uri)
        self.mlflow_client = MlflowClient()
        
        self.logger.info("🔍 MLflow Configuration")
        self.logger.info(f"   Version: {mlflow.__version__}")
        self.logger.info(f"   Tracking URI: {tracking_uri}")
        self.logger.info(f"   Database: {self.config.paths.mlflow_db_path}")
        
        # Create or get experiment
        try:
            experiment = mlflow.set_experiment(self.config.mlflow.experiment_name)
            self.logger.info(f"   Experiment: {self.config.mlflow.experiment_name}")
            self.logger.info(f"   Experiment ID: {experiment.experiment_id}")
            
            # Set experiment tags
            self.mlflow_client.set_experiment_tag(
                experiment.experiment_id, "project", self.config.mlflow.project_tag
            )
            self.mlflow_client.set_experiment_tag(
                experiment.experiment_id, "team", self.config.mlflow.team_tag
            )
            self.mlflow_client.set_experiment_tag(
                experiment.experiment_id, "framework", self.config.mlflow.framework_tag
            )
            
        except Exception as e:
            self.logger.warning(f"Could not setup experiment tags: {str(e)}")
    
    @retry_with_backoff(max_retries=3, delay=5)
    def step_1_data_acquisition(self):
        """Step 1: Acquire data from Kaggle."""
        log_section(self.logger, "STEP 1: DATA ACQUISITION")
        
        self.df_raw = self.data_acquisition.run()
        
        self.logger.info(f"✅ Data acquisition complete: {len(self.df_raw):,} rows")
    
    def step_2_data_preprocessing(self):
        """Step 2: Clean and preprocess data."""
        log_section(self.logger, "STEP 2: DATA PREPROCESSING")
        
        self.X, self.y = self.data_preprocessor.run(self.df_raw)
        
        stats = self.data_preprocessor.get_statistics()
        log_metrics(self.logger, stats, "Preprocessing Statistics")
        
        self.logger.info(f"✅ Data preprocessing complete")
    
    def step_3_data_splitting(self):
        """Step 3: Split data into train/val/test sets."""
        log_section(self.logger, "STEP 3: DATA SPLITTING")
        
        self.logger.info("🔒 Splitting data (before feature engineering)...")
        
        # Split train+val / test
        X_temp, self.X_test, y_temp, self.y_test = train_test_split(
            self.X,
            self.y,
            test_size=self.config.model.test_size,
            random_state=self.config.model.random_state
        )
        
        # Split train / val
        self.X_train, self.X_val, self.y_train, self.y_val = train_test_split(
            X_temp,
            y_temp,
            test_size=self.config.model.val_size,
            random_state=self.config.model.random_state
        )
        
        split_info = {
            'train_samples': len(self.X_train),
            'train_pct': len(self.X_train) / len(self.X) * 100,
            'val_samples': len(self.X_val),
            'val_pct': len(self.X_val) / len(self.X) * 100,
            'test_samples': len(self.X_test),
            'test_pct': len(self.X_test) / len(self.X) * 100
        }
        
        log_metrics(self.logger, split_info, "Data Split")
        self.logger.info("✅ Data splitting complete")
    
    def step_4_feature_engineering(self):
        """Step 4: Engineer features and build preprocessing pipeline."""
        log_section(self.logger, "STEP 4: FEATURE ENGINEERING")
        
        self.logger.info("🔧 Building preprocessing pipeline...")
        
        # Build and fit preprocessor
        self.preprocessor = build_preprocessor(
            iqr_factor=self.config.model.iqr_factor
        )
        
        self.logger.info("   Fitting on training data...")
        self.preprocessor.fit(self.X_train)
        
        # Transform all datasets
        self.logger.info("   Transforming train/val/test sets...")
        self.X_train_processed = self.preprocessor.transform(self.X_train)
        self.X_val_processed = self.preprocessor.transform(self.X_val)
        self.X_test_processed = self.preprocessor.transform(self.X_test)
        
        # Get feature names
        self.feature_names = self.preprocessor.named_steps['feature_engineer'].get_feature_names()
        
        self.logger.info(f"✅ Feature engineering complete")
        self.logger.info(f"   Engineered features: {len(self.feature_names)}")
        self.logger.info(f"   Train shape: {self.X_train_processed.shape}")
        self.logger.info(f"   Val shape: {self.X_val_processed.shape}")
        self.logger.info(f"   Test shape: {self.X_test_processed.shape}")
    
    def step_5_model_training(self):
        """Step 5: Train all models and select best."""
        log_section(self.logger, "STEP 5: MODEL TRAINING")
        
        # Train all models
        self.model_trainer.train_all_models(
            self.X_train_processed,
            self.y_train,
            self.X_val_processed,
            self.y_val
        )
        
        # Select best model
        self.best_model_name, self.best_model, self.best_run_id = \
            self.model_trainer.select_best_model()
        
        self.logger.info("✅ Model training complete")
    
    def step_6_model_tuning(self):
        """Step 6: Tune best model (if applicable)."""
        log_section(self.logger, "STEP 6: MODEL TUNING")
        
        if self.best_model_name not in self.config.model.tunable_models:
            self.logger.info(f"⚠️  {self.best_model_name} not tunable, skipping tuning")
            return
        
        original_score = self.model_trainer.results[self.best_model_name]['val_r2']
        
        tuned_model, tuned_run_id, best_score = self.model_trainer.tune_model(
            self.best_model_name,
            self.model_trainer.models[self.best_model_name],
            self.X_train_processed,
            self.y_train,
            original_score
        )
        
        # Validate on validation set
        y_val_pred = tuned_model.predict(self.X_val_processed)
        tuned_val_r2 = np.corrcoef(self.y_val, y_val_pred)[0, 1] ** 2
        
        # Update best model if improved
        if tuned_val_r2 > original_score:
            self.logger.info(f"🏆 Tuned model improved: {tuned_val_r2:.4f} > {original_score:.4f}")
            self.best_model = tuned_model
            self.best_run_id = tuned_run_id
        else:
            self.logger.info(f"   Tuned model did not improve, keeping original")
        
        self.logger.info("✅ Model tuning complete")
    
    def step_7_cross_validation(self):
        """Step 7: Cross-validate best model."""
        log_section(self.logger, "STEP 7: CROSS-VALIDATION")
        
        self.cv_scores = self.model_trainer.cross_validate_model(
            self.best_model,
            self.X_train_processed,
            self.y_train,
            self.best_run_id
        )
        
        self.logger.info("✅ Cross-validation complete")
    
    def step_8_test_evaluation(self):
        """Step 8: Evaluate on test set."""
        log_section(self.logger, "STEP 8: TEST EVALUATION")
        
        self.test_metrics = self.model_trainer.evaluate_on_test(
            self.best_model,
            self.X_test_processed,
            self.y_test,
            self.best_run_id
        )
        
        self.logger.info("✅ Test evaluation complete")
    
    def step_9_model_registry(self):
        """Step 9: Register model and transition to staging."""
        log_section(self.logger, "STEP 9: MODEL REGISTRY")
        
        # Prepare description
        description = (
            f"Best model: {self.best_model_name} | "
            f"Test R²: {self.test_metrics['test_r2']:.4f} | "
            f"Test MAE: {self.test_metrics['test_mae']:.2f} min | "
            f"Optimized Pipeline"
        )
        
        # Prepare tags
        tags = {
            'algorithm': self.best_model_name,
            'test_r2': str(self.test_metrics['test_r2']),
            'test_mae': str(self.test_metrics['test_mae']),
            'data_leakage': 'none',
            'optimization': 'production_pipeline'
        }
        
        # Transition to staging
        version = self.model_registry.transition_to_staging(
            self.best_run_id,
            description,
            tags
        )
        
        if version:
            self.logger.info(f"✅ Model registered: version {version}")
            self.model_registry.print_registry_status()
        else:
            self.logger.warning("⚠️  Could not register model")
    
    def step_10_save_deployment(self):
        """Step 10: Save deployment package."""
        log_section(self.logger, "STEP 10: DEPLOYMENT PACKAGE")
        
        cv_metrics = {
            'cv_r2_mean': float(self.cv_scores.mean()),
            'cv_r2_std': float(self.cv_scores.std())
        } if self.cv_scores is not None else None
        
        package_dir = self.model_deployment.save_deployment_package(
            model=self.best_model,
            preprocessor=self.preprocessor,
            model_name=self.best_model_name,
            mlflow_run_id=self.best_run_id,
            mlflow_model_name=self.config.mlflow.model_name,
            mlflow_experiment_name=self.config.mlflow.experiment_name,
            test_metrics=self.test_metrics,
            cv_metrics=cv_metrics,
            feature_names=self.feature_names,
            prediction_time_features=self.config.data.prediction_time_features
        )
        
        self.logger.info("✅ Deployment package saved")
        self.logger.info(f"   Location: {package_dir}")
    
    def run(self):
        """Execute complete pipeline."""
        log_section(self.logger, "NYC TAXI ML PIPELINE - START", "=", 80)
        
        self.logger.info("🚀 Starting ML pipeline...")
        self.logger.info(f"   Configuration: {self.config.__class__.__name__}")
        
        # Log configuration
        log_config(self.logger, self.config.to_dict())
        
        try:
            # Execute pipeline steps
            self.step_1_data_acquisition()
            self.step_2_data_preprocessing()
            self.step_3_data_splitting()
            self.step_4_feature_engineering()
            self.step_5_model_training()
            self.step_6_model_tuning()
            self.step_7_cross_validation()
            self.step_8_test_evaluation()
            self.step_9_model_registry()
            self.step_10_save_deployment()
            
            log_section(self.logger, "NYC TAXI ML PIPELINE - SUCCESS", "=", 80)
            self.logger.info("🎉 Pipeline completed successfully!")
            
            # Print summary
            self._print_summary()
            
        except Exception as e:
            log_section(self.logger, "NYC TAXI ML PIPELINE - FAILED", "=", 80)
            self.logger.error(f"❌ Pipeline failed: {str(e)}", exc_info=True)
            raise
    
    def _print_summary(self):
        """Print pipeline summary."""
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("PIPELINE SUMMARY".center(80))
        self.logger.info("=" * 80)
        
        self.logger.info(f"✅ Best Model: {self.best_model_name}")
        self.logger.info(f"   Run ID: {self.best_run_id[:8]}")
        self.logger.info(f"   Test R²: {self.test_metrics['test_r2']:.4f}")
        self.logger.info(f"   Test MAE: {self.test_metrics['test_mae']:.2f} minutes")
        
        if self.cv_scores is not None:
            self.logger.info(f"   CV R²: {self.cv_scores.mean():.4f} ± {self.cv_scores.std():.4f}")
        
        self.logger.info("")
        self.logger.info("📊 MLflow UI:")
        self.logger.info(f"   mlflow ui --backend-store-uri sqlite:///{self.config.paths.mlflow_db_path}")
        self.logger.info(f"   http://127.0.0.1:5000")
        
        self.logger.info("")
        self.logger.info("🔗 Model URI:")
        self.logger.info(f"   {self.model_registry.get_deployment_uri('Staging')}")
        
        self.logger.info("=" * 80)