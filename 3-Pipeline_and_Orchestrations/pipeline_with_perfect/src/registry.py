"""
Model Registry Module
Handles MLflow model registry operations and stage transitions
"""

from typing import Optional
from prefect import task, get_run_logger
import mlflow
from mlflow import MlflowClient

from config.config import config


@task(name="setup_mlflow")
def setup_mlflow() -> MlflowClient:
    """
    Setup MLflow tracking and return client.
    
    Returns:
        MlflowClient: MLflow client instance
    """
    logger = get_run_logger()
    logger.info("🔧 Setting up MLflow...")
    
    # Set tracking URI
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    client = MlflowClient()
    
    # Set experiment
    experiment = mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)
    
    # Update experiment tags
    client.set_experiment_tag(experiment.experiment_id, "project", "nyc_taxi")
    client.set_experiment_tag(experiment.experiment_id, "team", "data_science")
    client.set_experiment_tag(experiment.experiment_id, "data_leakage", "none")
    client.set_experiment_tag(experiment.experiment_id, "framework", "scikit-learn")
    client.set_experiment_tag(experiment.experiment_id, "pipeline", "prefect")
    
    logger.info(f"✅ MLflow configured")
    logger.info(f"   Tracking URI: {config.MLFLOW_TRACKING_URI}")
    logger.info(f"   Experiment: {config.MLFLOW_EXPERIMENT_NAME}")
    logger.info(f"   Experiment ID: {experiment.experiment_id}")
    
    return client


@task(name="tag_best_model")
def tag_best_model(client: MlflowClient, run_id: str) -> None:
    """
    Tag the best model run.
    
    Args:
        client: MLflow client
        run_id: Run ID to tag
    """
    logger = get_run_logger()
    logger.info(f"🏷️  Tagging best model run: {run_id[:8]}...")
    
    client.set_tag(run_id, "best_model", "true")
    client.set_tag(run_id, "selection_criteria", "val_r2")
    
    logger.info("✅ Best model tagged")


@task(name="promote_to_staging")
def promote_to_staging(
    client: MlflowClient,
    run_id: str,
    model_name: str,
    test_metrics: dict
) -> Optional[str]:
    """
    Promote model to Staging stage.
    
    Args:
        client: MLflow client
        run_id: Run ID of the model
        model_name: Name of the model algorithm
        test_metrics: Test metrics dictionary
        
    Returns:
        str: Model version or None
    """
    logger = get_run_logger()
    logger.info("🏛️  Promoting model to Staging...")
    
    try:
        # Get all versions of the registered model
        all_versions = client.search_model_versions(f"name='{config.MLFLOW_MODEL_NAME}'")
        
        # Find version for this run
        model_version = None
        for v in all_versions:
            if v.run_id == run_id:
                model_version = v.version
                break
        
        if model_version is None:
            logger.warning(f"⚠️  Model version not found for run {run_id[:8]}")
            return None
        
        logger.info(f"   Found version: {model_version}")
        
        # Transition to Staging
        client.transition_model_version_stage(
            name=config.MLFLOW_MODEL_NAME,
            version=model_version,
            stage="Staging"
        )
        logger.info(f"   ✓ Version {model_version} → Staging")
        
        # Update description
        description = (
            f"Best model: {model_name} | "
            f"Test R²: {test_metrics['test_r2']:.4f} | "
            f"Test MAE: {test_metrics['test_mae']:.2f} min | "
            f"Pipeline: Prefect Orchestrated"
        )
        client.update_model_version(
            name=config.MLFLOW_MODEL_NAME,
            version=model_version,
            description=description
        )
        
        # Add tags
        client.set_model_version_tag(config.MLFLOW_MODEL_NAME, model_version, "algorithm", model_name)
        client.set_model_version_tag(config.MLFLOW_MODEL_NAME, model_version, "test_r2", str(test_metrics['test_r2']))
        client.set_model_version_tag(config.MLFLOW_MODEL_NAME, model_version, "test_mae", str(test_metrics['test_mae']))
        client.set_model_version_tag(config.MLFLOW_MODEL_NAME, model_version, "data_leakage", "none")
        client.set_model_version_tag(config.MLFLOW_MODEL_NAME, model_version, "pipeline", "prefect_orchestrated")
        
        logger.info(f"✅ Model promoted to Staging (version {model_version})")
        
        return model_version
        
    except Exception as e:
        logger.error(f"❌ Error promoting to staging: {str(e)}")
        return None


@task(name="archive_old_production")
def archive_old_production(client: MlflowClient) -> None:
    """
    Archive old production models.
    
    Args:
        client: MLflow client
    """
    logger = get_run_logger()
    logger.info("📦 Archiving old production models...")
    
    try:
        production_versions = client.get_latest_versions(
            config.MLFLOW_MODEL_NAME,
            stages=["Production"]
        )
        
        for prod_v in production_versions:
            client.transition_model_version_stage(
                name=config.MLFLOW_MODEL_NAME,
                version=prod_v.version,
                stage="Archived"
            )
            logger.info(f"   ✓ Version {prod_v.version} → Archived")
        
        if not production_versions:
            logger.info("   No production models to archive")
        else:
            logger.info(f"✅ Archived {len(production_versions)} production model(s)")
            
    except Exception as e:
        logger.warning(f"⚠️  Could not archive old models: {str(e)}")


@task(name="promote_to_production")
def promote_to_production(
    client: MlflowClient,
    model_version: Optional[str]
) -> None:
    """
    Promote staging model to production.
    
    Args:
        client: MLflow client
        model_version: Version to promote
    """
    logger = get_run_logger()
    
    if model_version is None:
        logger.warning("⚠️  No model version to promote")
        return
    
    logger.info(f"🚀 Promoting version {model_version} to Production...")
    
    try:
        # Archive current production
        archive_old_production(client)
        
        # Promote to production
        client.transition_model_version_stage(
            name=config.MLFLOW_MODEL_NAME,
            version=model_version,
            stage="Production"
        )
        
        logger.info(f"✅ Version {model_version} promoted to Production")
        logger.info(f"\n🎉 MODEL DEPLOYMENT COMPLETE!")
        logger.info(f"   Load with: mlflow.sklearn.load_model('models:/{config.MLFLOW_MODEL_NAME}/Production')")
        
    except Exception as e:
        logger.error(f"❌ Error promoting to production: {str(e)}")


@task(name="display_registry_status")
def display_registry_status(client: MlflowClient) -> None:
    """
    Display current model registry status.
    
    Args:
        client: MLflow client
    """
    logger = get_run_logger()
    logger.info("\n" + "=" * 70)
    logger.info("📊 MODEL REGISTRY STATUS")
    logger.info("=" * 70)
    
    try:
        for stage in ["None", "Staging", "Production", "Archived"]:
            try:
                versions = client.get_latest_versions(config.MLFLOW_MODEL_NAME, stages=[stage])
                if versions:
                    v = versions[0]
                    logger.info(f"   {stage:<12}: v{v.version} (Run: {v.run_id[:8]}...)")
            except:
                pass
        
        logger.info("=" * 70)
        
    except Exception as e:
        logger.warning(f"⚠️  Could not display registry status: {str(e)}")