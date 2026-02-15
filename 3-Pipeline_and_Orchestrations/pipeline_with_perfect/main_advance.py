"""
Advanced Parameterized Pipeline Example
Similar to Prefect's week3_duration-prediction.py pattern

This shows how to create a pipeline that:
1. Accepts year/month parameters
2. Downloads specific data files
3. Logs all parameters to MLflow
4. Can be scheduled with different configurations

Usage:
    python main_advanced.py --year 2023 --month 1 --sample-size 100000
    python main_advanced.py --year 2023 --month 2 --tune --promote
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).parent))

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
import mlflow

from config.config import config
from src.data_loader import load_data_chunks
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


@task(name="download_specific_data")
def download_specific_data(year: int, month: int) -> str:
    """
    Download specific year/month data.
    
    In a real scenario, this would download from S3/GCS based on year/month.
    For this example, we'll use the cached Kaggle data.
    
    Args:
        year: Data year
        month: Data month
        
    Returns:
        str: Path to data file
    """
    logger = get_run_logger()
    logger.info(f"📥 Fetching data for {year}-{month:02d}")
    
    # In production, this would be something like:
    # s3_path = f"s3://taxi-data/yellow_tripdata_{year}-{month:02d}.parquet"
    # local_path = download_from_s3(s3_path)
    
    # For now, use the cached Kaggle data
    import kagglehub
    path = kagglehub.dataset_download("elemento/nyc-yellow-taxi-trip-data")
    data_file = f"{path}/yellow_tripdata_2016-01.csv"
    
    logger.info(f"✅ Data ready: {data_file}")
    logger.info(f"   Note: Currently using 2016-01 data as placeholder")
    logger.info(f"   In production: Would load {year}-{month:02d} data")
    
    return data_file


@flow(
    name="nyc-taxi-ml-pipeline-advanced",
    description="Parameterized ML pipeline for NYC Taxi trip duration prediction",
    task_runner=ConcurrentTaskRunner(),
    log_prints=True
)
def nyc_taxi_ml_pipeline_advanced(
    year: int = 2016,
    month: int = 1,
    sample_size: int = 200000,
    tune_model: bool = True,
    promote_to_prod: bool = False,
    experiment_suffix: str = None
):
    """
    Main ML pipeline flow with year/month parameterization.
    
    Args:
        year: Data year to process
        month: Data month to process
        sample_size: Number of samples to use
        tune_model: Whether to perform hyperparameter tuning
        promote_to_prod: Whether to promote to production automatically
        experiment_suffix: Optional suffix for experiment name
    """
    logger = get_run_logger()
    
    # Create experiment name with parameters
    experiment_name = config.MLFLOW_EXPERIMENT_NAME
    if experiment_suffix:
        experiment_name = f"{experiment_name}_{experiment_suffix}"
    
    # Create run name with parameters
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = f"taxi_{year}_{month:02d}_{run_timestamp}"
    
    logger.info("=" * 70)
    logger.info("🚀 NYC TAXI ML PIPELINE - PARAMETERIZED")
    logger.info("=" * 70)
    logger.info(f"   Data period: {year}-{month:02d}")
    logger.info(f"   Sample size: {sample_size:,}")
    logger.info(f"   Tuning enabled: {tune_model}")
    logger.info(f"   Auto-promote: {promote_to_prod}")
    logger.info(f"   Run name: {run_name}")
    logger.info("=" * 70)
    
    # ============================================
    # STAGE 1: MLflow Setup
    # ============================================
    logger.info("\n📌 STAGE 1: MLflow Setup")
    logger.info("-" * 70)
    
    # Temporarily update experiment name
    original_experiment = config.MLFLOW_EXPERIMENT_NAME
    config.MLFLOW_EXPERIMENT_NAME = experiment_name
    client = setup_mlflow()
    
    # Log pipeline parameters to MLflow
    with mlflow.start_run(run_name=run_name) as parent_run:
        # Log all pipeline parameters
        mlflow.log_params({
            'data_year': year,
            'data_month': month,
            'sample_size': sample_size,
            'tune_model': tune_model,
            'promote_to_prod': promote_to_prod
        })
        
        # Log pipeline metadata
        mlflow.set_tag('pipeline_type', 'parameterized')
        mlflow.set_tag('data_period', f"{year}-{month:02d}")
        mlflow.set_tag('run_timestamp', run_timestamp)
        
        parent_run_id = parent_run.info.run_id
    
    # ============================================
    # STAGE 2: Data Loading
    # ============================================
    logger.info("\n📌 STAGE 2: Data Loading")
    logger.info("-" * 70)
    
    # Download specific year/month data
    data_file = download_specific_data(year, month)
    
    # Load data
    import pandas as pd
    logger.info(f"📊 Loading data from: {data_file}")
    chunks = pd.read_csv(data_file, chunksize=500_000, low_memory=False)
    df_raw = next(chunks)
    
    if sample_size and len(df_raw) > sample_size:
        df_raw = df_raw.sample(n=sample_size, random_state=config.RANDOM_STATE)
    
    logger.info(f"✅ Data loaded: {df_raw.shape[0]:,} rows, {df_raw.shape[1]} columns")
    
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
        
        best_result = compare_tuning_results(best_result, tuning_result)
    else:
        logger.info("\n⏭️  STAGE 6: Hyperparameter Tuning (SKIPPED)")
    
    # ============================================
    # STAGE 7: Model Evaluation
    # ============================================
    logger.info("\n📌 STAGE 7: Model Evaluation")
    logger.info("-" * 70)
    
    test_metrics = evaluate_on_test_set(
        best_result['model'],
        X_test_processed,
        y_test,
        best_result['run_id']
    )
    
    cv_metrics = cross_validate_model(
        best_result['model'],
        X_train_processed,
        y_train,
        best_result['run_id'],
        cv=config.CV_FOLDS
    )
    
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
    
    display_registry_status(client)
    
    # ============================================
    # Log final results to parent run
    # ============================================
    with mlflow.start_run(run_id=parent_run_id):
        mlflow.log_metrics({
            'final_test_r2': test_metrics['test_r2'],
            'final_test_mae': test_metrics['test_mae'],
            'final_test_rmse': test_metrics['test_rmse']
        })
        mlflow.set_tag('best_model', best_result['model_name'])
        mlflow.set_tag('model_version', str(model_version))
    
    # ============================================
    # PIPELINE SUMMARY
    # ============================================
    logger.info("\n" + "=" * 70)
    logger.info("✅ PIPELINE EXECUTION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"\n📅 DATA PERIOD: {year}-{month:02d}")
    logger.info(f"🏆 BEST MODEL: {best_result['model_name']}")
    logger.info(f"   • Test R²: {test_metrics['test_r2']:.4f}")
    logger.info(f"   • Test MAE: {test_metrics['test_mae']:.2f} minutes")
    logger.info(f"\n📦 MODEL REGISTRY:")
    logger.info(f"   • Version: {model_version}")
    logger.info(f"   • Stage: {'Production' if promote_to_prod else 'Staging'}")
    logger.info("\n🎉 SUCCESS!")
    logger.info("=" * 70)
    
    # Restore original experiment name
    config.MLFLOW_EXPERIMENT_NAME = original_experiment
    
    return {
        'data_year': year,
        'data_month': month,
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
        description='NYC Taxi ML Pipeline - Advanced Parameterized Version',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run for specific year/month
  python main_advanced.py --year 2023 --month 1
  
  # Quick test with small sample
  python main_advanced.py --year 2023 --month 2 --sample-size 50000 --no-tune
  
  # Full run with auto-promotion
  python main_advanced.py --year 2023 --month 3 --tune --promote
  
  # Process multiple months (in shell)
  for month in {1..12}; do
    python main_advanced.py --year 2023 --month $month
  done
        """
    )
    
    # Time period
    parser.add_argument(
        '--year',
        type=int,
        default=2016,
        help='Year of data to process (default: 2016)'
    )
    
    parser.add_argument(
        '--month',
        type=int,
        default=1,
        choices=range(1, 13),
        help='Month of data to process (default: 1)'
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
    
    # Experiment naming
    parser.add_argument(
        '--experiment-suffix',
        type=str,
        default=None,
        help='Suffix for experiment name (e.g., "monthly_runs")'
    )
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    print("\n" + "=" * 70)
    print("🚀 NYC TAXI ML PIPELINE - ADVANCED PARAMETERIZED")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  • Data period:      {args.year}-{args.month:02d}")
    print(f"  • Sample size:      {args.sample_size:,}")
    print(f"  • Tuning:           {'Enabled' if args.tune else 'Disabled'}")
    print(f"  • Auto-promote:     {'Yes' if args.promote else 'No'}")
    if args.experiment_suffix:
        print(f"  • Experiment:       {config.MLFLOW_EXPERIMENT_NAME}_{args.experiment_suffix}")
    print("=" * 70 + "\n")
    
    # Run the pipeline
    result = nyc_taxi_ml_pipeline_advanced(
        year=args.year,
        month=args.month,
        sample_size=args.sample_size,
        tune_model=args.tune,
        promote_to_prod=args.promote,
        experiment_suffix=args.experiment_suffix
    )
    
    print("\n" + "=" * 70)
    print("📊 PIPELINE RESULT:")
    print("=" * 70)
    for key, value in result.items():
        print(f"   {key}: {value}")
    print("=" * 70)