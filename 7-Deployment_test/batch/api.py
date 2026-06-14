"""
Batch scoring API — HTTP interface to the batch scorer.

Endpoints:
  GET  /health                    service health + summary
  POST /score?year=2020&month=4   trigger scoring in background
  GET  /results                   all scored periods
  GET  /results/{year}/{month}    one period
  GET  /predictions               list available parquet files
  GET  /running                   jobs currently in progress

The key teaching point:
  Online API  → synchronous  → returns prediction in milliseconds
  Batch API   → async        → triggers job, returns immediately, poll for result
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

import core


_running_jobs: set = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.init_db()
    yield


app = FastAPI(
    title="NYC Taxi Batch Scoring API",
    description="Trigger batch scoring jobs and retrieve drift metrics",
    version="1.0.0",
    lifespan=lifespan,
    root_path=os.getenv("ROOT_PATH", ""),  # ← reads /batch from docker-compose env
)


# ── Background job ────────────────────────────────────────────────────────────
def _run_score_job(year: int, month: int):
    try:
        champion = core.load_champion()
        result   = core.score_month(year, month, champion)
        core.save_result(result, champion)
    finally:
        _running_jobs.discard((year, month))


# ── Schemas ───────────────────────────────────────────────────────────────────
class ScoreResponse(BaseModel):
    status:  str
    year:    int
    month:   int
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    results = core.get_all_results()
    return {
        "status":          "ok",
        "periods_scored":  len(results),
        "alerts":          sum(r["alert"] for r in results),
        "running_jobs":    len(_running_jobs),
        "db":              str(core.DB_PATH),
        "predictions_dir": str(core.PREDICTIONS_DIR),
    }


@app.post("/score", response_model=ScoreResponse)
async def trigger_score(year: int, month: int, background_tasks: BackgroundTasks):
    key = (year, month)

    if key in _running_jobs:
        return ScoreResponse(
            status="already_running", year=year, month=month,
            message=f"Scoring {year}-{month:02d} is already in progress."
        )

    _running_jobs.add(key)
    background_tasks.add_task(_run_score_job, year, month)

    return ScoreResponse(
        status="started", year=year, month=month,
        message=(
            f"Scoring {year}-{month:02d} started in background (~2 min). "
            f"Poll GET /results/{year}/{month} to check when complete."
        )
    )


@app.get("/results")
def get_results():
    return core.get_all_results()


@app.get("/results/{year}/{month}")
def get_result(year: int, month: int):
    result = core.get_result(year, month)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=(
                f"{year}-{month:02d} has not been scored yet. "
                f"POST /score?year={year}&month={month} to trigger."
            )
        )
    return result


@app.get("/predictions")
def list_predictions():
    if not core.PREDICTIONS_DIR.exists():
        return []
    return [
        {
            "filename": f.name,
            "size_mb":  round(f.stat().st_size / 1024 / 1024, 1),
            "year":     int(f.stem.split("_")[0]),
            "month":    int(f.stem.split("_")[1]),
        }
        for f in sorted(core.PREDICTIONS_DIR.glob("*.parquet"))
    ]


@app.get("/running")
def get_running():
    return [{"year": y, "month": m} for y, m in _running_jobs]