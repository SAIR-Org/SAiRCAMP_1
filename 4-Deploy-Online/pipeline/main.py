#!/usr/bin/env python3
"""
main.py — Entry point for the Prefect-orchestrated Trip Duration Pipeline

Usage:
  python main.py                                  # full run, defaults
  python main.py --sample-size 50000 --no-tune   # quick test
  python main.py --sample-size 200000 --promote  # full run + promote to prod
  python main.py --experiment-name my_experiment # custom MLflow experiment

What happens when you run this:
  1. Imports and calls the @flow from flow.py
  2. Prefect creates a local FlowRun (stored in ~/.prefect/)
  3. Each @task inside the flow gets its own TaskRun with state tracking
  4. If you have the Prefect UI running (prefect server start), you can watch
     the pipeline execute in real time at http://127.0.0.1:4200
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flow import trip_duration_pipeline


def parse_args():
    parser = argparse.ArgumentParser(
        description="Trip Duration Pipeline — Prefect Orchestrated",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test run (small data, no tuning)
  python main.py --sample-size 50000 --no-tune

  # Full run with tuning
  python main.py --sample-size 200000 --tune

  # Full run with auto-promotion to production
  python main.py --sample-size 200000 --tune --promote

  # Custom experiment name in MLflow
  python main.py --experiment-name trip_duration_v2

  # Start Prefect UI first, then run
  prefect server start &
  python main.py --sample-size 100000
        """
    )

    parser.add_argument(
        '--sample-size', type=int, default=200000,
        help='Number of training samples (default: 200000)'
    )
    parser.add_argument(
        '--tune', action='store_true', default=True,
        help='Enable hyperparameter tuning (default: True)'
    )
    parser.add_argument(
        '--no-tune', action='store_false', dest='tune',
        help='Disable hyperparameter tuning'
    )
    parser.add_argument(
        '--promote', action='store_true', default=False,
        help='Auto-promote best model to Production in MLflow (default: False)'
    )
    parser.add_argument(
        '--experiment-name', type=str, default=None,
        help='Override MLflow experiment name'
    )

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    print("\n" + "=" * 60)
    print("TRIP DURATION PIPELINE — PREFECT ORCHESTRATED")
    print("=" * 60)
    print(f"  sample_size : {args.sample_size:,}")
    print(f"  tune        : {args.tune}")
    print(f"  promote     : {args.promote}")
    if args.experiment_name:
        print(f"  experiment  : {args.experiment_name}")
    print("=" * 60 + "\n")

    result = trip_duration_pipeline(
        sample_size=args.sample_size,
        tune=args.tune,
        promote_to_prod=args.promote,
        experiment_name=args.experiment_name
    )

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    for k, v in result.items():
        print(f"  {k}: {v}")
    print("=" * 60)
