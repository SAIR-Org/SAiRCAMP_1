"""
Batch scoring API — HTTP interface to the batch scorer.

Endpoints:
  GET  /health                    service health + summary
  POST /score?year=2020&month=4   trigger scoring in background
  GET  /results                   all scored periods
  GET  /results/{year}/{month}    one period
  GET  /predictions               list available parquet files
  GET  /running                   jobs currently in progress
  GET  /drift/summary             drift summary for dashboard
  GET  /drift/report/{year}/{month}  full drift report
"""
import os
import json
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
    root_path=os.getenv("ROOT_PATH", ""),
)


# ── Background job ────────────────────────────────────────────────────────────
def _run_score_job(year: int, month: int):
    try:
        champion = core.load_champion()
        result = core.score_month(year, month, champion)
        core.save_result(result, champion)
    finally:
        _running_jobs.discard((year, month))


# ── Schemas ───────────────────────────────────────────────────────────────────
class ScoreResponse(BaseModel):
    status: str
    year: int
    month: int
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    results = core.get_all_results()
    return {
        "status": "ok",
        "periods_scored": len(results),
        "alerts": sum(r["alert"] for r in results),
        "drift_detected": sum(1 for r in results if r.get("drift_detected", 0) == 1),
        "running_jobs": len(_running_jobs),
        "db": str(core.DB_PATH),
        "predictions_dir": str(core.PREDICTIONS_DIR),
    }


@app.post("/score", response_model=ScoreResponse)
async def trigger_score(year: int, month: int, background_tasks: BackgroundTasks):
    key = (year, month)

    if key in _running_jobs:
        return ScoreResponse(
            status="already_running",
            year=year,
            month=month,
            message=f"Scoring {year}-{month:02d} is already in progress."
        )

    _running_jobs.add(key)
    background_tasks.add_task(_run_score_job, year, month)

    return ScoreResponse(
        status="started",
        year=year,
        month=month,
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
            detail=f"{year}-{month:02d} has not been scored yet. "
                   f"POST /score?year={year}&month={month} to trigger."
        )
    return result


@app.get("/predictions")
def list_predictions():
    if not core.PREDICTIONS_DIR.exists():
        return []
    return [
        {
            "filename": f.name,
            "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
            "year": int(f.stem.split("_")[0]),
            "month": int(f.stem.split("_")[1]),
        }
        for f in sorted(core.PREDICTIONS_DIR.glob("*.parquet"))
    ]


@app.get("/running")
def get_running():
    return [{"year": y, "month": m} for y, m in _running_jobs]


# ── DRIFT ENDPOINTS ────────────────────────────────────────────────────────────

@app.get("/drift/summary")
def get_drift_summary():
    """Get drift summary for dashboard."""
    results = core.get_all_results()
    
    summary = [
        {
            "year": r["year"],
            "month": r["month"],
            "drift_score": r.get("drift_score", 0.0),
            "drift_detected": r.get("drift_detected", 0),
            "mae": r["mae"],
            "alert": r["alert"]
        }
        for r in results
        if "drift_score" in r and r["drift_score"] is not None
    ]
    
    return {"summary": summary}


@app.get("/drift/report/{year}/{month}")
def get_drift_report(year: int, month: int):
    """Get full drift report for a specific period."""
    report_path = core.DRIFT_REPORTS_DIR / f"drift_{year}_{month:02d}.json"
    
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No drift report found for {year}-{month:02d}."
        )
    
    with open(report_path, 'r') as f:
        return json.load(f)


@app.get("/drift/html/{year}/{month}")
def get_drift_html(year: int, month: int):
    """Get HTML drift report for viewing in browser."""
    html_path = core.DRIFT_REPORTS_DIR / f"drift_{year}_{month:02d}.html"
    
    if not html_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No HTML report found for {year}-{month:02d}."
        )
    
    from fastapi.responses import FileResponse
    return FileResponse(html_path, media_type="text/html")
