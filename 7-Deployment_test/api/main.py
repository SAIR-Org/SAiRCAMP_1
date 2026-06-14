import os
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

from schema import TripRequest, PredictionResponse
from model_loader import load_model, get_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(
    title="NYC Taxi Trip Duration API",
    description="Predict trip duration from pickup/dropoff zone IDs (2019 TLC model)",
    version="1.0.0",
    lifespan=lifespan,
    root_path=os.getenv("ROOT_PATH", ""),  # ← reads /api from docker-compose env
)


@app.get("/health")
def health():
    s = get_state()
    return {"status": "ok", "model_version": s.version, "model_alias": s.alias}


@app.post("/predict", response_model=PredictionResponse)
def predict(trip: TripRequest):
    s = get_state()
    if s.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    df = pd.DataFrame([trip.model_dump()])
    X = s.preprocessor.transform(df)
    duration = float(s.model.predict(X)[0])

    return PredictionResponse(
        predicted_duration_minutes=round(duration, 2),
        model_version=s.version,
        model_alias=s.alias,
    )