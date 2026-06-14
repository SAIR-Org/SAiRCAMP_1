"""
Prefect-orchestrated batch scoring flow.
Wraps core.py with @task/@flow for local development observability.
For Docker deployment use api.py instead.
"""
from typing import Optional

import mlflow
from prefect import flow, task, get_run_logger
import core


@task(name="load-champion", retries=2, retry_delay_seconds=10)
def load_champion_task() -> dict:
    logger   = get_run_logger()
    champion = core.load_champion()
    logger.info(f"Champion: v{champion['version']}  run: {champion['run_id'][:8]}")
    logger.info(f"Model: {type(champion['model']).__name__}")
    logger.info(f"Baseline — MAE: {champion['train_mae']:.2f} min  "
                f"mean: {champion['train_mean']:.2f} min")
    logger.info(f"Alert if MAE > {champion['train_mae'] * core.MAE_RATIO_THRESHOLD:.2f} min "
                f"or volume < {core.VOLUME_THRESHOLD:,}")
    return champion


@task(name="score-month", retries=1, retry_delay_seconds=30)
def score_month_task(year: int, month: int, champion: dict) -> dict:
    logger = get_run_logger()
    logger.info(f"Scoring {year}-{month:02d} — downloading all trips...")
    result = core.score_month(year, month, champion)
    import os
    logger.info(f"  {result['total_rows']:,} trips → "
                f"{os.path.basename(result['predictions_path'])}  "
                f"({os.path.getsize(result['predictions_path']) / 1024 / 1024:.1f} MB)")
    logger.info(f"  MAE: {result['mae']:.2f} min  ratio={result['mae_ratio']:.2f}x")
    flag = "⚠️  ALERT" if result["alert"] else "✅ OK"
    logger.info(f"  {flag}")
    return result


@task(name="save-result")
def save_result_task(result: dict, champion: dict):
    logger = get_run_logger()
    core.save_result(result, champion)
    logger.info(f"Saved {result['year']}-{result['month']:02d} → "
                f"batch_results.db + MLflow")


@flow(name="batch-score", log_prints=True)
def batch_score_flow(
    periods: Optional[list] = None,
    experiment_name: str = "batch_scoring",
):
    """
    Batch scoring flow — two outputs per period:
      predictions/YYYY_MM.parquet  per-trip predictions (batch deployment)
      batch_results.db             aggregate drift metrics (monitoring)

    Default periods tell the drift story:
      (2020, 4) — COVID: ALERT
      (2022, 1) — new normal: OK
      (2024, 1) — stable: OK
    """
    logger = get_run_logger()

    if periods is None:
        periods = [(2020, 4), (2022, 1), (2024, 1)]

    mlflow.set_tracking_uri(core.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experiment_name)
    core.init_db()

    logger.info("=" * 55)
    logger.info("BATCH SCORING — NYC TAXI TRIP DURATION")
    logger.info(f"  Periods: {periods}")
    logger.info(f"  DB:      {core.DB_PATH.name}")
    logger.info(f"  Output:  predictions/ + batch_results.db")
    logger.info("=" * 55)

    champion = load_champion_task()

    results = []
    for year, month in periods:
        result = score_month_task(year, month, champion)
        save_result_task(result, champion)
        results.append(result)

    logger.info("")
    logger.info("=" * 55)
    logger.info("SUMMARY")
    logger.info("=" * 55)
    for r in results:
        flag = "⚠️ " if r["alert"] else "✅"
        logger.info(
            f"  {flag} {r['year']}-{r['month']:02d}  "
            f"MAE={r['mae']:.2f}  ratio={r['mae_ratio']:.2f}x  "
            f"vol={r['total_rows']:,}"
        )
    alerts = sum(r["alert"] for r in results)
    logger.info(f"\n  {alerts}/{len(results)} periods triggered alerts")

    return results
