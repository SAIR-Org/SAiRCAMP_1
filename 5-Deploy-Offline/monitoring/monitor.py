"""
Model monitoring — reads batch_results.db and makes the drift story visible.

Three outputs:
  1. Health report  — printed summary of every scored period
  2. Drift chart    — MAE over time saved to drift_chart.png
  3. Alert summary  — actionable list of periods that need attention

Run after the batch scorer:
  python monitor.py

Or point at a custom DB:
  python monitor.py --db /path/to/batch_results.db
"""
import argparse
import sqlite3
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


# ── Config ────────────────────────────────────────────────────────────────────
_MONITORING_DIR = Path(__file__).parent
_BATCH_DIR      = _MONITORING_DIR.parent / "batch"

DEFAULT_DB      = _BATCH_DIR / "batch_results.db"
CHART_PATH      = _MONITORING_DIR / "drift_chart.png"

TRAIN_MAE       = 3.07   # 2019 training baseline
MAE_RATIO_ALERT = 1.5
VOLUME_ALERT    = 500_000


# ── Load data ─────────────────────────────────────────────────────────────────
def load_results(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(
            f"batch_results.db not found at {db_path}\n"
            "Run the batch scorer first: cd ../batch && python main.py"
        )
    conn = sqlite3.connect(db_path)
    df   = pd.read_sql("SELECT * FROM batch_results ORDER BY year, month", conn)
    conn.close()
    df["period"] = df["year"].astype(str) + "-" + df["month"].apply(lambda m: f"{m:02d}")
    return df


# ── Health report ─────────────────────────────────────────────────────────────
def print_health_report(df: pd.DataFrame):
    print()
    print("=" * 65)
    print("MODEL HEALTH REPORT — NYC Taxi Trip Duration")
    print("=" * 65)
    print(f"  Training baseline:  MAE = {TRAIN_MAE:.2f} min")
    print(f"  Alert thresholds:   MAE ratio > {MAE_RATIO_ALERT}x  |  volume < {VOLUME_ALERT:,}")
    print()
    print(f"  {'Period':<10} {'Volume':>10} {'MAE':>8} {'Ratio':>8} {'Status'}")
    print(f"  {'-'*10} {'-'*10} {'-'*8} {'-'*8} {'-'*20}")

    for _, row in df.iterrows():
        flag   = "⚠️  ALERT" if row["alert"] else "✅ OK"
        volume = f"{int(row['total_rows']):,}"
        print(
            f"  {row['period']:<10} {volume:>10} "
            f"{row['mae']:>8.2f} {row['mae_ratio']:>8.2f}x  {flag}"
        )

    print()
    n_alerts = int(df["alert"].sum())
    n_total  = len(df)

    if n_alerts == 0:
        print(f"  ✅ All {n_total} periods within acceptable range.")
    else:
        print(f"  ⚠️  {n_alerts}/{n_total} periods triggered alerts.")
        print()
        print("  Recommended actions:")
        for _, row in df[df["alert"] == 1].iterrows():
            reasons = []
            if row["mae_ratio"] > MAE_RATIO_ALERT:
                reasons.append(f"MAE {row['mae_ratio']:.1f}x training baseline")
            if row["total_rows"] < VOLUME_ALERT:
                reasons.append(f"volume collapsed to {int(row['total_rows']):,} trips")
            print(f"    {row['period']}: {', '.join(reasons)}")
            print(f"             → investigate data distribution shift")
            print(f"             → consider retraining on recent data")

    print("=" * 65)
    print()


# ── Drift chart ───────────────────────────────────────────────────────────────
def plot_drift_chart(df: pd.DataFrame, output_path: Path):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    alert_color  = "#e74c3c"
    ok_color     = "#2ecc71"
    colors       = [alert_color if a else ok_color for a in df["alert"]]

    # Panel 1 — MAE over time
    axes[0].bar(df["period"], df["mae"], color=colors)
    axes[0].axhline(TRAIN_MAE, color="steelblue", linestyle="--",
                    linewidth=2, label=f"Train MAE ({TRAIN_MAE:.2f} min)")
    axes[0].axhline(TRAIN_MAE * MAE_RATIO_ALERT, color=alert_color,
                    linestyle="--", linewidth=2,
                    label=f"Alert ({MAE_RATIO_ALERT}x = {TRAIN_MAE * MAE_RATIO_ALERT:.2f} min)")
    axes[0].set_title("MAE over time", fontweight="bold")
    axes[0].set_ylabel("MAE (minutes)")
    axes[0].tick_params(axis="x", rotation=15)
    axes[0].legend(fontsize=8)

    # Panel 2 — MAE ratio
    axes[1].bar(df["period"], df["mae_ratio"], color=colors)
    axes[1].axhline(1.0, color="steelblue", linestyle="--",
                    linewidth=2, label="Training baseline (1.0x)")
    axes[1].axhline(MAE_RATIO_ALERT, color=alert_color, linestyle="--",
                    linewidth=2, label=f"Alert threshold ({MAE_RATIO_ALERT}x)")
    axes[1].set_title("MAE ratio vs training", fontweight="bold")
    axes[1].set_ylabel("Ratio")
    axes[1].tick_params(axis="x", rotation=15)
    axes[1].legend(fontsize=8)

    # Panel 3 — Volume
    axes[2].bar(df["period"], df["total_rows"], color=colors)
    axes[2].axhline(VOLUME_ALERT, color=alert_color, linestyle="--",
                    linewidth=2, label=f"Volume alert ({VOLUME_ALERT:,})")
    axes[2].set_title("Monthly trip volume", fontweight="bold")
    axes[2].set_ylabel("Total trips")
    axes[2].tick_params(axis="x", rotation=15)
    axes[2].legend(fontsize=8)

    # Legend
    ok_patch    = mpatches.Patch(color=ok_color,    label="OK")
    alert_patch = mpatches.Patch(color=alert_color, label="Alert")
    fig.legend(handles=[ok_patch, alert_patch], loc="upper right",
               bbox_to_anchor=(1.0, 1.0), fontsize=9)

    plt.suptitle(
        "NYC Taxi Model Drift Monitor\n"
        "Train: 2019  |  Scored: batch periods",
        fontsize=13, fontweight="bold"
    )
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Drift chart saved → {output_path.name}")


# ── Per-period deep dive ──────────────────────────────────────────────────────
def print_deep_dive(df: pd.DataFrame):
    """Show per-period details including feature drift."""
    print("  PERIOD DETAILS")
    print(f"  {'-'*60}")
    for _, row in df.iterrows():
        flag = "⚠️ " if row["alert"] else "✅"
        print(f"\n  {flag} {row['period']}")
        print(f"     Volume:       {int(row['total_rows']):>10,} trips")
        print(f"     MAE:          {row['mae']:>10.2f} min  "
              f"(train: {TRAIN_MAE:.2f}  ratio: {row['mae_ratio']:.2f}x)")
        print(f"     Duration avg: {row['target_mean']:>10.2f} min")
        print(f"     Distance avg: {row['dist_mean']:>10.2f} miles")
        print(f"     Scored at:    {row['scored_at'][:19]}")


# ── Main ──────────────────────────────────────────────────────────────────────
def run(db_path: Path):
    print(f"\n  Loading results from: {db_path}")
    df = load_results(db_path)
    print(f"  Found {len(df)} scored periods\n")

    print_health_report(df)
    print_deep_dive(df)
    print()
    plot_drift_chart(df, CHART_PATH)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor batch scoring results")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help=f"Path to batch_results.db (default: {DEFAULT_DB})",
    )
    args = parser.parse_args()
    run(Path(args.db))
