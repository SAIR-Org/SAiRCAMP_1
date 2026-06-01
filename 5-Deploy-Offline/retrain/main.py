"""CLI entry point for the retrain flow."""
import argparse
from flow import retrain_flow


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrain with champion/challenger gate")
    parser.add_argument(
        "--train-years", default="2019,2020",
        help="Comma-separated years to train on (default: 2019,2020)"
    )
    parser.add_argument(
        "--sample-size", type=int, default=200_000,
        help="Total rows across all training periods (default: 200000)"
    )
    parser.add_argument(
        "--eval-year", type=int, default=2020,
        help="Holdout evaluation year (default: 2020)"
    )
    parser.add_argument(
        "--eval-month", type=int, default=6,
        help="Holdout evaluation month (default: 6 = June 2020)"
    )
    parser.add_argument(
        "--min-improvement", type=float, default=0.1,
        help="Min MAE improvement in minutes to promote challenger (default: 0.1)"
    )
    args = parser.parse_args()

    train_years = [int(y) for y in args.train_years.split(",")]

    retrain_flow(
        train_years=train_years,
        sample_size=args.sample_size,
        eval_year=args.eval_year,
        eval_month=args.eval_month,
        min_improvement=args.min_improvement,
    )
