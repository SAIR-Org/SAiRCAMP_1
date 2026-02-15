"""
Quick validation script to test pipeline components
Run this to verify the setup before running the full pipeline
"""

import sys
from pathlib import Path

# Add project to path
sys.path.append(str(Path(__file__).parent))

def test_imports():
    """Test that all modules can be imported."""
    print("🧪 Testing imports...")
    
    try:
        from config.config import config, PREDICTION_TIME_FEATURES, LEAKAGE_FEATURES
        print("   ✓ config")
        
        from src.data_loader import download_dataset, load_data_chunks
        print("   ✓ data_loader")
        
        from src.data_preprocessing import clean_data, validate_no_leakage, split_data
        print("   ✓ data_preprocessing")
        
        from src.feature_engineering import (
            NYCTaxiFeatureEngineer,
            OutlierHandler,
            build_preprocessing_pipeline
        )
        print("   ✓ feature_engineering")
        
        from src.training import get_model_portfolio, train_single_model
        print("   ✓ training")
        
        from src.evaluation import evaluate_on_test_set, cross_validate_model
        print("   ✓ evaluation")
        
        from src.tuning import tune_model
        print("   ✓ tuning")
        
        from src.registry import setup_mlflow, promote_to_staging
        print("   ✓ registry")
        
        print("\n✅ All imports successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        return False


def test_dependencies():
    """Test that required dependencies are installed."""
    print("\n🧪 Testing dependencies...")
    
    required = [
        'numpy',
        'pandas',
        'sklearn',
        'mlflow',
        'prefect',
        'kagglehub'
    ]
    
    missing = []
    
    for package in required:
        try:
            __import__(package)
            print(f"   ✓ {package}")
        except ImportError:
            print(f"   ✗ {package} (missing)")
            missing.append(package)
    
    if missing:
        print(f"\n❌ Missing dependencies: {', '.join(missing)}")
        print("   Run: pip install -r requirements.txt")
        return False
    else:
        print("\n✅ All dependencies installed!")
        return True


def test_configuration():
    """Test configuration settings."""
    print("\n🧪 Testing configuration...")
    
    try:
        from config.config import config
        
        print(f"   • Project root: {config.PROJECT_ROOT}")
        print(f"   • Data dir: {config.DATA_DIR}")
        print(f"   • Model dir: {config.MODEL_DIR}")
        print(f"   • MLflow DB: {config.MLFLOW_DB_PATH}")
        print(f"   • Sample size: {config.SAMPLE_SIZE:,}")
        print(f"   • Random state: {config.RANDOM_STATE}")
        
        # Check directories exist
        assert config.DATA_DIR.exists(), "Data directory not created"
        assert config.MODEL_DIR.exists(), "Model directory not created"
        assert config.LOG_DIR.exists(), "Log directory not created"
        
        print("\n✅ Configuration valid!")
        return True
        
    except Exception as e:
        print(f"\n❌ Configuration error: {e}")
        return False


def test_mlflow_setup():
    """Test MLflow setup."""
    print("\n🧪 Testing MLflow...")
    
    try:
        import mlflow
        from config.config import config
        
        # Set tracking URI
        mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
        
        # Try to create a test experiment
        test_exp = mlflow.set_experiment("pipeline_validation_test")
        
        print(f"   • Tracking URI: {mlflow.get_tracking_uri()}")
        print(f"   • Test experiment ID: {test_exp.experiment_id}")
        
        # Quick test run
        with mlflow.start_run(run_name="validation_test") as run:
            mlflow.log_param("test_param", "test_value")
            mlflow.log_metric("test_metric", 0.99)
            print(f"   • Test run ID: {run.info.run_id[:8]}...")
        
        print("\n✅ MLflow working!")
        return True
        
    except Exception as e:
        print(f"\n❌ MLflow error: {e}")
        return False


def test_prefect():
    """Test Prefect setup."""
    print("\n🧪 Testing Prefect...")
    
    try:
        from prefect import task, flow
        
        @task
        def test_task():
            return "Hello from Prefect!"
        
        @flow
        def test_flow():
            result = test_task()
            return result
        
        result = test_flow()
        print(f"   • Test flow result: {result}")
        
        print("\n✅ Prefect working!")
        return True
        
    except Exception as e:
        print(f"\n❌ Prefect error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("🔧 NYC TAXI ML PIPELINE - VALIDATION")
    print("=" * 70)
    
    results = []
    
    # Run tests
    results.append(("Dependencies", test_dependencies()))
    results.append(("Imports", test_imports()))
    results.append(("Configuration", test_configuration()))
    results.append(("MLflow", test_mlflow_setup()))
    results.append(("Prefect", test_prefect()))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 VALIDATION SUMMARY")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {name:<20} {status}")
    
    all_passed = all(result[1] for result in results)
    
    print("=" * 70)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nYou're ready to run the pipeline:")
        print("   python main.py")
    else:
        print("\n⚠️  SOME TESTS FAILED")
        print("\nPlease fix the issues above before running the pipeline.")
    
    print("=" * 70)
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)