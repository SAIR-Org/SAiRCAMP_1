"""CLI entry point for the batch scoring flow."""
import argparse
from flow import batch_score_flow


def parse_periods(s: str) -> list:
    """Parse '2020-04,2022-01,2024-01' into [(2020,4),(2022,1),(2024,1)]."""
    result = []
    for p in s.split(","):
        year, month = p.strip().split("-")
        result.append((int(year), int(month)))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch score NYC taxi trip duration model")
    parser.add_argument(
        "--periods",
        default="2020-04,2022-01,2024-01",
        help="Comma-separated YYYY-MM periods (default: drift story periods)",
    )
    parser.add_argument(
        "--experiment",
        default="batch_scoring",
        help="MLflow experiment name",
    )
    args = parser.parse_args()

    batch_score_flow(
        periods=parse_periods(args.periods),
        experiment_name=args.experiment,
    )
