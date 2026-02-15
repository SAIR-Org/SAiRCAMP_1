#!/usr/bin/env python3
"""
NYC Taxi ML Pipeline - Command Line Interface
Production-ready ML pipeline with MLflow integration
"""
import argparse
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.config import Config, load_config
from src.pipeline import NYCTaxiMLPipeline


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="NYC Taxi Trip Duration Prediction ML Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Data configuration
    data_group = parser.add_argument_group('Data Configuration')
    data_group.add_argument(
        '--sample-size',
        type=int,
        default=200000,
        help='Number of samples to use for training'
    )
    data_group.add_argument(
        '--chunk-size',
        type=int,
        default=500000,
        help='Chunk size for reading CSV'
    )
    data_group.add_argument(
        '--num-chunks',
        type=int,
        default=2,
        help='Number of chunks to load'
    )
    
    # Model configuration
    model_group = parser.add_argument_group('Model Configuration')
    model_group.add_argument(
        '--random-state',
        type=int,
        default=42,
        help='Random state for reproducibility'
    )
    model_group.add_argument(
        '--test-size',
        type=float,
        default=0.2,
        help='Test set size (fraction)'
    )
    model_group.add_argument(
        '--val-size',
        type=float,
        default=0.2,
        help='Validation set size (fraction)'
    )
    model_group.add_argument(
        '--cv-folds',
        type=int,
        default=5,
        help='Number of cross-validation folds'
    )
    model_group.add_argument(
        '--models',
        nargs='+',
        default=None,
        choices=['Linear Regression', 'Ridge', 'Lasso', 'Random Forest', 'Gradient Boosting'],
        help='Models to train (default: all)'
    )
    model_group.add_argument(
        '--skip-tuning',
        action='store_true',
        help='Skip hyperparameter tuning'
    )
    model_group.add_argument(
        '--skip-cv',
        action='store_true',
        help='Skip cross-validation'
    )
    
    # MLflow configuration
    mlflow_group = parser.add_argument_group('MLflow Configuration')
    mlflow_group.add_argument(
        '--experiment-name',
        type=str,
        default='nyc_taxi_production_pipeline',
        help='MLflow experiment name'
    )
    mlflow_group.add_argument(
        '--model-name',
        type=str,
        default='nyc_taxi_predictor',
        help='MLflow registered model name'
    )
    
    # Path configuration
    path_group = parser.add_argument_group('Path Configuration')
    path_group.add_argument(
        '--model-dir',
        type=str,
        default='models',
        help='Directory for saving models'
    )
    path_group.add_argument(
        '--data-dir',
        type=str,
        default='data',
        help='Directory for data'
    )
    path_group.add_argument(
        '--log-dir',
        type=str,
        default='logs',
        help='Directory for logs'
    )
    
    # Logging configuration
    log_group = parser.add_argument_group('Logging Configuration')
    log_group.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level'
    )
    log_group.add_argument(
        '--log-file',
        type=str,
        default='pipeline.log',
        help='Log file name'
    )
    
    # Retry configuration
    retry_group = parser.add_argument_group('Retry Configuration')
    retry_group.add_argument(
        '--max-retries',
        type=int,
        default=3,
        help='Maximum number of retries for failed operations'
    )
    retry_group.add_argument(
        '--retry-delay',
        type=int,
        default=5,
        help='Initial delay between retries (seconds)'
    )
    
    # Pipeline control
    control_group = parser.add_argument_group('Pipeline Control')
    control_group.add_argument(
        '--steps',
        nargs='+',
        type=int,
        default=None,
        help='Specific steps to run (1-10, default: all)'
    )
    control_group.add_argument(
        '--dry-run',
        action='store_true',
        help='Print configuration and exit without running'
    )
    
    return parser.parse_args()


def apply_args_to_config(args, config: Config) -> Config:
    """
    Apply command line arguments to configuration.
    
    Args:
        args: Parsed arguments
        config: Base configuration
        
    Returns:
        Updated configuration
    """
    # Data configuration
    if args.sample_size:
        config.data.sample_size = args.sample_size
    if args.chunk_size:
        config.data.chunk_size = args.chunk_size
    if args.num_chunks:
        config.data.num_chunks = args.num_chunks
    
    # Model configuration
    if args.random_state:
        config.model.random_state = args.random_state
    if args.test_size:
        config.model.test_size = args.test_size
    if args.val_size:
        config.model.val_size = args.val_size
    if args.cv_folds:
        config.model.cv_folds = args.cv_folds
    if args.models:
        config.model.models_to_train = args.models
    
    # MLflow configuration
    if args.experiment_name:
        config.mlflow.experiment_name = args.experiment_name
    if args.model_name:
        config.mlflow.model_name = args.model_name
    
    # Path configuration
    if args.model_dir:
        config.paths.model_dir = args.model_dir
    if args.data_dir:
        config.paths.data_dir = args.data_dir
    if args.log_dir:
        config.paths.log_dir = args.log_dir
    
    # Logging configuration
    if args.log_level:
        config.log.log_level = args.log_level
    if args.log_file:
        config.log.log_file = args.log_file
    
    # Retry configuration
    if args.max_retries:
        config.retry.max_retries = args.max_retries
    if args.retry_delay:
        config.retry.retry_delay = args.retry_delay
    
    return config


def print_config(config: Config):
    """Print configuration."""
    print("\n" + "=" * 80)
    print("PIPELINE CONFIGURATION".center(80))
    print("=" * 80)
    
    config_dict = config.to_dict()
    for section, params in config_dict.items():
        print(f"\n[{section.upper()}]")
        if isinstance(params, dict):
            for key, value in params.items():
                if isinstance(value, list):
                    print(f"  {key}: [{len(value)} items]")
                else:
                    print(f"  {key}: {value}")
        else:
            print(f"  {params}")
    
    print("\n" + "=" * 80)


def main():
    """Main entry point."""
    # Parse arguments
    args = parse_args()
    
    # Load base configuration
    config = load_config()
    
    # Apply command line arguments
    config = apply_args_to_config(args, config)
    
    # Print configuration
    print_config(config)
    
    # Dry run check
    if args.dry_run:
        print("\n✅ Dry run complete. Configuration validated.")
        return 0
    
    # Create and run pipeline
    try:
        pipeline = NYCTaxiMLPipeline(config)
        
        # Run specific steps or full pipeline
        if args.steps:
            print(f"\n🎯 Running steps: {args.steps}")
            step_methods = {
                1: pipeline.step_1_data_acquisition,
                2: pipeline.step_2_data_preprocessing,
                3: pipeline.step_3_data_splitting,
                4: pipeline.step_4_feature_engineering,
                5: pipeline.step_5_model_training,
                6: pipeline.step_6_model_tuning if not args.skip_tuning else None,
                7: pipeline.step_7_cross_validation if not args.skip_cv else None,
                8: pipeline.step_8_test_evaluation,
                9: pipeline.step_9_model_registry,
                10: pipeline.step_10_save_deployment
            }
            
            for step in sorted(args.steps):
                if step in step_methods and step_methods[step]:
                    print(f"\n▶️  Executing step {step}...")
                    step_methods[step]()
        else:
            # Run full pipeline
            pipeline.run()
        
        print("\n✅ Pipeline completed successfully!")
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        return 130
        
    except Exception as e:
        print(f"\n\n❌ Pipeline failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())