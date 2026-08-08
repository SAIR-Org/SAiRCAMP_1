from contextlib import asynccontextmanager 
from fastapi import FastAPI , HTTPException, BackgroundTasks
from pydantic import BaseModel 

import core2 


_running_jobs: set = set() 


@asynccontextmanager 
async def lifespan(app:FastAPI):
    core2.init_db() 
    yield 

app = FastAPI(
    title="NYC Taxi Batch API", 
    description="Trigger API using batch scoring", 
    version="1.0.0",
    lifespan=lifespan,
) 

# background job 

def _run_score_job(year:int , month:int):
    try : 
        champion = core2.load_champion() 
        result = core2.score_month(year , month , champion) 
        core2.save_result(result , champion) 
    finally:
        _running_jobs.discard((year, month)) 



@app.get("/health")
def health():

    return {
        "status": "ok" , 
    }


class ScoreResponse(BaseModel): 
    status : str 
    year : int 
    month : int 
    message : str

@app.post("/score", response_model=ScoreResponse)
async def trigger_score(year: int , month:int, background_tasks:BackgroundTasks):

    key = (year , month) 

    if key in _running_jobs:
        return ScoreResponse(
            status="already_running" ,
            year= year ,
            month=month ,
            message= f"Scoring {year}-{month:0.2d} is already running" 
        ) 


    _running_jobs.add(key) 
    background_tasks.add_task(_run_score_job,year , month) 

    return ScoreResponse(
       status="started",
        year=year, month=month,
        message=(
            f"Scoring {year}-{month:02d} started in background (~2 min). "
            f"Poll GET /results/{year}/{month} to check when complete."
        ) 
    )

@app.get("/results")
def get_results():
    # get all the scored jobs 
    return  core2.get_all_results() 

@app.get("/results/{year}/{month}")
def get_result(year:int , month:int): 

    result = core2.get_result() 

    if not result:
        raise HTTPException(
            status_code=404,
            detail= (
                f"{year}-{month:02d} has not been scored yet. "
                f"POST /score?year={year}&month={month} to trigger."
            )
        ) 

@app.get("/predictions")
def list_predictions():

    if not core2.PREDICTION_DIR.exist():
        return [] 

    return [
        {
            "filename": f.name,
            "size": round(f.stat().st_size / 1024 / 1024, 1),
            "year": int(f.stem.split("_")[0]),
            "month": int(f.stem.split("_")[1]), 
        } 
        for f in sorted(core2.PREDICTION_DIR.glob("*.parquet"))
    ] 

@app.get("/running")
def get_running():

    return [
        {"year":y , "month": m} for y , m in _running_jobs
    ]







