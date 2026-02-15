"""
NYC Taxi ML Pipeline - Main Prefect Flow
Production-ready ML pipeline with Prefect orchestration

Usage:
    python main.py --sample-size 200000 --tune --promote
    python main.py --sample-size 100000 --no-tune
    python main.py --help
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.append(str(Path(__file__).parent))

from prefect import flow, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from config.config import config
from src.data_loader import download_dataset, load_data_chunks
from src.data_preprocessing import clean_data, validate_no_leakage, split_data
from src.feature_engineering import (
    build_preprocessing_pipeline,
    fit_transform_pipeline
)
from src.training import train_all_models, select_best_model
from src.evaluation import (
    evaluate_on_test_set,
    cross_validate_model,
    generate_evaluation_report
)
from src.tuning import tune_best_model, compare_tuning_results
from src.registry import (
    setup_mlflow,
    tag_best_model,
    promote_to_staging,
    promote_to_production,
    display_registry_status
)


@flow(
    name="nyc-taxi-ml-pipeline",
    description="End-to-end ML pipeline for NYC Taxi trip duration prediction",
    task_runner=ConcurrentTaskRunner(),
    log_prints=True
)
def nyc_taxi_ml_pipeline(
    sample_size: int = 200000,
    tune_model: bool = True,
    promote_to_prod: bool = False
):
    """
    Main ML pipeline flow.
    
    Args:
        sample_size: Number of samples to use
        tune_model: Whether to perform hyperparameter tuning
        promote_to_prod: Whether to promote to production automatically
    """
    logger = get_run_logger()
    
    logger.info("=" * 70)
    logger.info("🚀 NYC TAXI ML PIPELINE - PREFECT ORCHESTRATED")
    logger.info("=" * 70)
    logger.info(f"   Sample size: {sample_size:,}")
    logger.info(f"   Tuning enabled: {tune_model}")
    logger.info(f"   Auto-promote: {promote_to_prod}")
    logger.info("=" * 70)
    
    # ============================================
    # STAGE 1: MLflow Setup
    # ============================================
    logger.info("\n📌 STAGE 1: MLflow Setup")
    logger.info("-" * 70)
    client = setup_mlflow()
    
    # ============================================
    # STAGE 2: Data Loading
    # ============================================
    logger.info("\n📌 STAGE 2: Data Loading")
    logger.info("-" * 70)
    dataset_path = download_dataset()
    df_raw = load_data_chunks(dataset_path, sample_size=sample_size)
    
    # ============================================
    # STAGE 3: Data Preprocessing
    # ============================================
    logger.info("\n📌 STAGE 3: Data Preprocessing")
    logger.info("-" * 70)
    df_clean = clean_data(df_raw)
    validate_no_leakage(df_clean)
    X_train, X_val, X_test, y_train, y_val, y_test = split_data(df_clean)
    
    # ============================================
    # STAGE 4: Feature Engineering
    # ============================================
    logger.info("\n📌 STAGE 4: Feature Engineering")
    logger.info("-" * 70)
    preprocessor = build_preprocessing_pipeline()
    X_train_processed, X_val_processed, X_test_processed, feature_names = fit_transform_pipeline(
        preprocessor, X_train, X_val, X_test
    )
    
    # ============================================
    # STAGE 5: Model Training
    # ============================================
    logger.info("\n📌 STAGE 5: Model Training")
    logger.info("-" * 70)
    training_results = train_all_models(
        X_train_processed, y_train,
        X_val_processed, y_val,
        feature_names
    )
    
    best_result = select_best_model(training_results)
    tag_best_model(client, best_result['run_id'])
    
    # ============================================
    # STAGE 6: Hyperparameter Tuning (Optional)
    # ============================================
    if tune_model:
        logger.info("\n📌 STAGE 6: Hyperparameter Tuning")
        logger.info("-" * 70)
        
        tuning_result = tune_best_model(
            best_result,
            X_train_processed, y_train,
            X_val_processed, y_val
        )
        
        # Compare and select best
        best_result = compare_tuning_results(best_result, tuning_result)
    else:
        logger.info("\n⏭️  STAGE 6: Hyperparameter Tuning (SKIPPED)")
    
    # ============================================
    # STAGE 7: Model Evaluation
    # ============================================
    logger.info("\n📌 STAGE 7: Model Evaluation")
    logger.info("-" * 70)
    
    # Test set evaluation
    test_metrics = evaluate_on_test_set(
        best_result['model'],
        X_test_processed,
        y_test,
        best_result['run_id']
    )
    
    # Cross-validation
    cv_metrics = cross_validate_model(
        best_result['model'],
        X_train_processed,
        y_train,
        best_result['run_id'],
        cv=config.CV_FOLDS
    )
    
    # Generate report
    report = generate_evaluation_report(
        best_result['model_name'],
        best_result['metrics'],
        test_metrics,
        cv_metrics
    )
    
    # ============================================
    # STAGE 8: Model Registry
    # ============================================
    logger.info("\n📌 STAGE 8: Model Registry")
    logger.info("-" * 70)
    
    model_version = promote_to_staging(
        client,
        best_result['run_id'],
        best_result['model_name'],
        test_metrics
    )
    
    if promote_to_prod and model_version:
        promote_to_production(client, model_version)
    else:
        logger.info("\n📋 Manual promotion required:")
        logger.info(f"   client.transition_model_version_stage(")
        logger.info(f"       name='{config.MLFLOW_MODEL_NAME}',")
        logger.info(f"       version='{model_version}',")
        logger.info(f"       stage='Production'")
        logger.info(f"   )")
    
    display_registry_status(client)
    
    # ============================================
    # PIPELINE SUMMARY
    # ============================================
    logger.info("\n" + "=" * 70)
    logger.info("✅ PIPELINE EXECUTION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"\n🏆 BEST MODEL: {best_result['model_name']}")
    logger.info(f"   • Run ID: {best_result['run_id'][:8]}...")
    logger.info(f"   • Val R²: {best_result['metrics']['val_r2']:.4f}")
    logger.info(f"   • Test R²: {test_metrics['test_r2']:.4f}")
    logger.info(f"   • Test MAE: {test_metrics['test_mae']:.2f} minutes")
    
    if model_version:
        logger.info(f"\n📦 MODEL REGISTRY:")
        logger.info(f"   • Model: {config.MLFLOW_MODEL_NAME}")
        logger.info(f"   • Version: {model_version}")
        logger.info(f"   • Stage: {'Production' if promote_to_prod else 'Staging'}")
        logger.info(f"\n🔗 Load model:")
        logger.info(f"   model = mlflow.sklearn.load_model('models:/{config.MLFLOW_MODEL_NAME}/Staging')")
    
    logger.info("\n🎉 SUCCESS!")
    logger.info("=" * 70)
    
    return {
        'model_name': best_result['model_name'],
        'run_id': best_result['run_id'],
        'model_version': model_version,
        'test_r2': test_metrics['test_r2'],
        'test_mae': test_metrics['test_mae'],
        'status': 'success'
    }



def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='NYC Taxi ML Pipeline - Prefect Orchestrated',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings
  python main.py
  
  # Smaller sample for quick testing
  python main.py --sample-size 50000 --no-tune
  
  # Full run with tuning and auto-promotion
  python main.py --sample-size 200000 --tune --promote
  
  # Custom configuration
  python main.py --sample-size 100000 --tune --experiment-name "my_experiment"
        """
    )
    
    # Data parameters
    parser.add_argument(
        '--sample-size',
        type=int,
        default=200000,
        help='Number of samples to use (default: 200000)'
    )
    
    # Model parameters
    parser.add_argument(
        '--tune',
        action='store_true',
        default=True,
        help='Enable hyperparameter tuning (default: True)'
    )
    
    parser.add_argument(
        '--no-tune',
        action='store_false',
        dest='tune',
        help='Disable hyperparameter tuning'
    )
    
    # Deployment parameters
    parser.add_argument(
        '--promote',
        action='store_true',
        default=False,
        help='Automatically promote to production (default: False)'
    )
    
    # MLflow parameters
    parser.add_argument(
        '--experiment-name',
        type=str,
        default=None,
        help='MLflow experiment name (default: from config)'
    )
    
    parser.add_argument(
        '--run-name',
        type=str,
        default=None,
        help='Custom run name for MLflow (default: auto-generated)'
    )
    
    # Additional parameters for future enhancements
    parser.add_argument(
        '--data-year',
        type=int,
        default=2016,
        help='Year of data to use (default: 2016)'
    )
    
    parser.add_argument(
        '--data-month',
        type=int,
        default=1,
        choices=range(1, 13),
        help='Month of data to use (default: 1)'
    )
    
    # Debug options
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    
    parser.add_argument(
        '--skip-download',
        action='store_true',
        help='Skip data download (use cached data)'
    )
    
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Update config if custom experiment name provided
    if args.experiment_name:
        config.MLFLOW_EXPERIMENT_NAME = args.experiment_name
    
    # Print configuration
    print("\n" + "=" * 70)
    print("🚀 NYC TAXI ML PIPELINE")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  • Sample size:      {args.sample_size:,}")
    print(f"  • Tuning:           {'Enabled' if args.tune else 'Disabled'}")
    print(f"  • Auto-promote:     {'Yes' if args.promote else 'No'}")
    print(f"  • Data period:      {args.data_year}-{args.data_month:02d}")
    print(f"  • Experiment:       {config.MLFLOW_EXPERIMENT_NAME}")
    if args.run_name:
        print(f"  • Run name:         {args.run_name}")
    print("=" * 70 + "\n")
    
    # Run the pipeline
    result = nyc_taxi_ml_pipeline(
        sample_size=args.sample_size,
        tune_model=args.tune,
        promote_to_prod=args.promote
    )
    
    print("\n" + "=" * 70)
    print("📊 PIPELINE RESULT:")
    print("=" * 70)
    for key, value in result.items():
        print(f"   {key}: {value}")
    print("=" * 70)