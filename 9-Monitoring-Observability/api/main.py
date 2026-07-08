
import os
import time
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import logging

from schema import TripRequest, PredictionResponse

from model_loader import load_model, get_state

from metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    PREDICTION_COUNT,
    PREDICTION_VALUE,
    PREDICTION_LATENCY,
    ACTIVE_REQUESTS,
    MODEL_INFO,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup and set model info"""
    logger.info("Starting API server...")
    load_model()
    
    # Set model info in Prometheus
    s = get_state()
    MODEL_INFO.info({
        'version': s.version,
        'alias': s.alias,
    })
    logger.info(f"Model loaded: {s.version} ({s.alias})")
    
    yield
    logger.info("Shutting down API server...")


app = FastAPI(
    title="NYC Taxi Trip Duration API",
    description="Predict trip duration from pickup/dropoff zone IDs (2019 TLC model)",
    version="1.0.0",
    lifespan=lifespan,
    root_path=os.getenv("ROOT_PATH", ""),  # ← reads /api from docker-compose env
)


# ──────────────────────────────────────────────────────────────
# Prometheus Metrics Middleware (THE NEW ADDITION)
# ──────────────────────────────────────────────────────────────
@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    
    return response


# ──────────────────────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    s = get_state()
    return {
        "status": "ok",
        "model_version": s.version,
        "model_alias": s.alias,
        "service": "api"
    }


# ──────────────────────────────────────────────────────────────
# Metrics Endpoint (for Prometheus scraping)
# ──────────────────────────────────────────────────────────────
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# ──────────────────────────────────────────────────────────────
# Prediction Endpoint
# ──────────────────────────────────────────────────────────────
@app.post("/predict", response_model=PredictionResponse)
def predict(trip: TripRequest):
    s = get_state()
    if s.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    # Track prediction count
    PREDICTION_COUNT.inc()
    
    # Prepare input
    df = pd.DataFrame([trip.model_dump()])
    X = s.preprocessor.transform(df)
    
    # Predict with timing
    start_time = time.time()
    duration = float(s.model.predict(X)[0])
    prediction_time = time.time() - start_time
    
    # Record prediction metrics
    PREDICTION_VALUE.set(duration)
    PREDICTION_LATENCY.observe(prediction_time)
    
    logger.info(f"Prediction: {duration:.2f} min (took {prediction_time:.3f}s)")
    
    return PredictionResponse(
        predicted_duration_minutes=round(duration, 2),
        model_version=s.version,
        model_alias=s.alias,
        prediction_time_ms=round(prediction_time * 1000, 2)
    )
