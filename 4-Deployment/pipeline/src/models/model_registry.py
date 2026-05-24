"""MLflow model registry using aliases (MLflow 3.x — @champion/@challenger)."""
import logging
from typing import List, Optional, Dict
from mlflow import MlflowClient
from mlflow.entities.model_registry import ModelVersion

from config.config import MLflowConfig


logger = logging.getLogger(__name__)

CHAMPION   = "champion"    # replaces Production
CHALLENGER = "challenger"  # replaces Staging


class ModelRegistry:
    """Handle MLflow model registry operations using aliases (MLflow 3.x)."""

    def __init__(self, mlflow_config: MLflowConfig, client: MlflowClient):
        self.mlflow_config = mlflow_config
        self.client = client
        self.model_name = mlflow_config.model_name

    def get_all_versions(self) -> List[ModelVersion]:
        try:
            versions = self.client.search_model_versions(f"name='{self.model_name}'")
            return sorted(versions, key=lambda x: int(x.version))
        except Exception as e:
            logger.warning(f"Could not retrieve model versions: {e}")
            return []

    def find_version_by_run_id(self, run_id: str) -> Optional[str]:
        for v in self.get_all_versions():
            if v.run_id == run_id:
                return v.version
        return None

    def set_alias(self, version: str, alias: str) -> bool:
        """Assign an alias to a model version (replaces stage transition)."""
        try:
            self.client.set_registered_model_alias(self.model_name, alias, version)
            logger.info(f"   ✓ Version {version} → @{alias}")
            return True
        except Exception as e:
            logger.error(f"   ❌ Failed to set alias @{alias}: {e}")
            return False

    def remove_alias(self, alias: str) -> None:
        """Remove an alias if it exists (no-op if absent)."""
        try:
            self.client.delete_registered_model_alias(self.model_name, alias)
        except Exception:
            pass

    def transition_to_staging(
        self,
        run_id: str,
        description: str,
        tags: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """Tag the new model version as @challenger."""
        logger.info("🏛️  Registering model as @challenger...")

        version = self.find_version_by_run_id(run_id)
        if not version:
            # Tuning ran but didn't register a new version (improvement below threshold).
            # Fall back to the most recently registered version (highest version number).
            all_versions = self.get_all_versions()
            if all_versions:
                version = all_versions[-1].version
                logger.info(f"   ℹ️  run_id not found — using latest version v{version}")
            else:
                logger.error(f"   ❌ No model versions found for {self.model_name}")
                return None

        try:
            self.client.update_model_version(
                name=self.model_name,
                version=version,
                description=description
            )
            if tags:
                for key, value in tags.items():
                    self.client.set_model_version_tag(
                        self.model_name, version, key, str(value)
                    )
                logger.info(f"   ✓ Added {len(tags)} tags")

            self.remove_alias(CHALLENGER)
            self.set_alias(version, CHALLENGER)
            return version

        except Exception as e:
            logger.error(f"   ❌ Failed to register challenger: {e}")
            return None

    def transition_to_production(self, version: str) -> bool:
        """Promote @challenger to @champion (replaces Production stage)."""
        logger.info("🚀 Promoting model to @champion...")
        self.remove_alias(CHAMPION)
        return self.set_alias(version, CHAMPION)

    def get_model_by_alias(self, alias: str) -> Optional[ModelVersion]:
        """Get model version by alias."""
        try:
            return self.client.get_model_version_by_alias(self.model_name, alias)
        except Exception:
            return None

    def print_registry_status(self):
        logger.info("📊 Model Registry Status:")
        logger.info(f"   Model: {self.model_name}")

        all_versions = self.get_all_versions()
        logger.info(f"   Total versions: {len(all_versions)}")

        for alias in [CHAMPION, CHALLENGER]:
            v = self.get_model_by_alias(alias)
            if v:
                logger.info(f"   • @{alias:<12}: v{v.version} (Run: {v.run_id[:8]})")

    def get_deployment_uri(self, alias: str = CHAMPION) -> str:
        """Return the load URI for downstream components."""
        return f"models:/{self.model_name}@{alias}"
