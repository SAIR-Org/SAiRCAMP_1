"""
Model deployment module for NYC Taxi ML Pipeline
Handles local model saving and deployment artifacts
"""
import os
import json
import joblib
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


logger = logging.getLogger(__name__)


class ModelDeployment:
    """Handle model deployment artifacts."""
    
    def __init__(self, model_dir: str):
        """
        Initialize model deployment.
        
        Args:
            model_dir: Directory for saving models
        """
        self.model_dir = model_dir
        Path(model_dir).mkdir(parents=True, exist_ok=True)
    
    def save_deployment_package(
        self,
        model,
        preprocessor,
        model_name: str,
        mlflow_run_id: str,
        mlflow_model_name: str,
        mlflow_experiment_name: str,
        test_metrics: Dict[str, float],
        cv_metrics: Optional[Dict[str, float]] = None,
        feature_names: Optional[list] = None,
        prediction_time_features: Optional[list] = None
    ) -> str:
        """
        Save complete deployment package.
        
        Args:
            model: Trained model
            preprocessor: Fitted preprocessor pipeline
            model_name: Model algorithm name
            mlflow_run_id: MLflow run ID
            mlflow_model_name: MLflow registered model name
            mlflow_experiment_name: MLflow experiment name
            test_metrics: Test set metrics
            cv_metrics: Cross-validation metrics
            feature_names: Engineered feature names
            prediction_time_features: Original prediction-time features
            
        Returns:
            Path to deployment package
        """
        logger.info("💾 Saving deployment package...")
        
        # Create versioned directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_version = f"nyc_taxi_{model_name.lower().replace(' ', '_')}_{timestamp}"
        model_save_dir = os.path.join(self.model_dir, model_version)
        os.makedirs(model_save_dir, exist_ok=True)
        
        logger.info(f"   Package: {model_version}")
        
        # Save model
        model_path = os.path.join(model_save_dir, 'model.pkl')
        joblib.dump(model, model_path)
        logger.info(f"   ✓ Model saved: {os.path.basename(model_path)}")
        
        # Save preprocessor
        preprocessor_path = os.path.join(model_save_dir, 'preprocessor.pkl')
        joblib.dump(preprocessor, preprocessor_path)
        logger.info(f"   ✓ Preprocessor saved: {os.path.basename(preprocessor_path)}")
        
        # Create model card
        model_card = {
            'model_info': {
                'model_name': model_name,
                'model_version': model_version,
                'created_at': timestamp,
                'framework': 'scikit-learn'
            },
            'mlflow': {
                'run_id': mlflow_run_id,
                'registered_model': mlflow_model_name,
                'experiment': mlflow_experiment_name,
                'tracking_uri': f"models:/{mlflow_model_name}/Staging"
            },
            'performance': {
                'test_metrics': test_metrics,
                'cv_metrics': cv_metrics or {}
            },
            'features': {
                'prediction_time_features': prediction_time_features or [],
                'engineered_features': len(feature_names) if feature_names else 0,
                'feature_names': feature_names or []
            },
            'deployment': {
                'local_path': model_save_dir,
                'model_file': 'model.pkl',
                'preprocessor_file': 'preprocessor.pkl',
                'model_card_file': 'model_card.json'
            }
        }
        
        # Save model card
        model_card_path = os.path.join(model_save_dir, 'model_card.json')
        with open(model_card_path, 'w') as f:
            json.dump(model_card, f, indent=2)
        logger.info(f"   ✓ Model card saved: {os.path.basename(model_card_path)}")
        
        # Create README
        readme_content = self._generate_readme(model_card)
        readme_path = os.path.join(model_save_dir, 'README.md')
        with open(readme_path, 'w') as f:
            f.write(readme_content)
        logger.info(f"   ✓ README saved: {os.path.basename(readme_path)}")
        
        logger.info(f"✅ Deployment package saved: {model_save_dir}")
        
        return model_save_dir
    
    def _generate_readme(self, model_card: Dict[str, Any]) -> str:
        """
        Generate README for deployment package.
        
        Args:
            model_card: Model card dictionary
            
        Returns:
            README content
        """
        test_metrics = model_card['performance']['test_metrics']
        cv_metrics = model_card['performance']['cv_metrics']
        
        readme = f"""# NYC Taxi Trip Duration Prediction Model

## Model Information
- **Model**: {model_card['model_info']['model_name']}
- **Version**: {model_card['model_info']['model_version']}
- **Created**: {model_card['model_info']['created_at']}
- **Framework**: {model_card['model_info']['framework']}

## Performance Metrics

### Test Set Performance
- **R² Score**: {test_metrics.get('test_r2', 'N/A'):.4f}
- **RMSE**: {test_metrics.get('test_rmse', 'N/A'):.2f} minutes
- **MAE**: {test_metrics.get('test_mae', 'N/A'):.2f} minutes

### Cross-Validation Performance
- **CV R² Mean**: {cv_metrics.get('cv_r2_mean', 'N/A'):.4f}
- **CV R² Std**: {cv_metrics.get('cv_r2_std', 'N/A'):.4f}

## Features
- **Prediction-time features**: {len(model_card['features']['prediction_time_features'])}
- **Engineered features**: {model_card['features']['engineered_features']}

## Deployment

### Files
- `model.pkl`: Trained model
- `preprocessor.pkl`: Fitted preprocessing pipeline
- `model_card.json`: Complete model metadata
- `README.md`: This file

### Usage Example

```python
import joblib
import pandas as pd

# Load model and preprocessor
model = joblib.load('model.pkl')
preprocessor = joblib.load('preprocessor.pkl')

# Prepare input data (prediction-time features only)
input_data = pd.DataFrame({{
    'tpep_pickup_datetime': ['2016-01-01 12:00:00'],
    'pickup_longitude': [-73.98],
    'pickup_latitude': [40.75],
    'dropoff_longitude': [-73.95],
    'dropoff_latitude': [40.78],
    'passenger_count': [1],
    'VendorID': [2],
    'RatecodeID': [1],
    'trip_distance': [3.5],
    'payment_type': [1]
}})

# Preprocess and predict
input_processed = preprocessor.transform(input_data)
prediction = model.predict(input_processed)

print(f"Predicted trip duration: {{prediction[0]:.2f}} minutes")
```

### MLflow Integration
- **Run ID**: {model_card['mlflow']['run_id']}
- **Registered Model**: {model_card['mlflow']['registered_model']}
- **Tracking URI**: {model_card['mlflow']['tracking_uri']}

### Load from MLflow

```python
import mlflow

# Load from MLflow registry (recommended for production)
model_uri = "models:/{model_card['mlflow']['registered_model']}/Production"
model = mlflow.sklearn.load_model(model_uri)
```

## Data Leakage Prevention
This model uses ONLY prediction-time features (available at trip pickup):
- Temporal features (pickup datetime)
- Geographic features (pickup/dropoff coordinates)
- Trip metadata (passenger count, vendor, payment type)

Post-trip features (fare, tip, duration) are EXCLUDED to prevent data leakage.
"""
        return readme
    
    def load_deployment_package(self, package_dir: str) -> Dict[str, Any]:
        """
        Load deployment package.
        
        Args:
            package_dir: Path to deployment package
            
        Returns:
            Dictionary with model, preprocessor, and metadata
        """
        logger.info(f"📥 Loading deployment package: {package_dir}")
        
        # Load model
        model_path = os.path.join(package_dir, 'model.pkl')
        model = joblib.load(model_path)
        logger.info("   ✓ Model loaded")
        
        # Load preprocessor
        preprocessor_path = os.path.join(package_dir, 'preprocessor.pkl')
        preprocessor = joblib.load(preprocessor_path)
        logger.info("   ✓ Preprocessor loaded")
        
        # Load model card
        model_card_path = os.path.join(package_dir, 'model_card.json')
        with open(model_card_path, 'r') as f:
            model_card = json.load(f)
        logger.info("   ✓ Model card loaded")
        
        return {
            'model': model,
            'preprocessor': preprocessor,
            'model_card': model_card
        }