# Module 4 — Deploy Online

Production ML system for NYC Yellow Taxi trip duration prediction.
Teaches: schema migration, MLflow registry, online serving with FastAPI, Docker for ML.

---

## Concept Guides

| Guide | Covers |
|-------|--------|
| [MLFLOW_REGISTRY.md](MLFLOW_REGISTRY.md) | Registry vs tracking, aliases, loading by URI, preprocessor artifact, training-serving skew |
| [DOCKER_FOR_ML.md](DOCKER_FOR_ML.md) | Images vs containers, volumes, shared state, build context, profiles |
| [FASTAPI.md](FASTAPI.md) | Online vs batch serving, lifespan, Pydantic validation, global state, health checks |

---

## Architecture

```
4-Deploy-Online/
├── shared/      Feature engineering — single source of truth for pipeline and api
├── pipeline/    Train on 2019 TLC data, register @champion in MLflow              ✅
└── api/         FastAPI online serving, load @champion from registry               ✅
```

Each component shares nothing except the MLflow model URI:
```
models:/trip_duration_model@champion
```

**What comes next:** `5-Deploy-Offline/` — batch scoring, drift monitoring,
champion/challenger retraining, Streamlit dashboard.

---

## Why This Module Uses Different Data

Modules 1–3 use a static Kaggle snapshot of 2016 NYC taxi data. That works for learning
the tools. Module 4 deliberately breaks from it — and that break is the first lesson.

**The schema changed:**

```
Modules 1–3 (2016 Kaggle)              Module 4 (2019 TLC)
──────────────────────────────         ──────────────────────────────
pickup_longitude    float64      →     PULocationID    int64  (1–265)
pickup_latitude     float64      →     DOLocationID    int64  (1–265)
dropoff_longitude   float64            (removed)
dropoff_latitude    float64            (removed)
tpep_pickup_datetime   ✅             tpep_pickup_datetime   ✅
passenger_count        ✅             passenger_count        ✅
trip_distance          ✅             trip_distance          ✅
VendorID               ✅             VendorID               ✅
RatecodeID             ✅             RatecodeID             ✅
payment_type           ✅             payment_type           ✅
```

NYC TLC replaced GPS coordinates with zone IDs in 2017. There are 265 zones covering
all NYC boroughs. Zone IDs are better features for tree models — they encode
neighborhood semantics directly instead of requiring the model to learn them from coordinates.

**The feature engineering changed too:**

```
REMOVED (lat/lon no longer exists):       ADDED (zone ID equivalents):
  haversine_distance                  →     centroid_distance_miles
  manhattan_distance                  →     zone_pair  (PU * 1000 + DO)
  direction_sin / cos                 →     centroid_direction_sin / cos
  is_jfk_trip, is_lga_trip            →     is_airport_pickup / dropoff / trip
  efficiency_ratio (lat/lon version)  →     efficiency_ratio (centroid version)

TOTAL: 19 features (Modules 1–3)  →  23 features (Module 4)
```

**The point:** data sources change in production. A model trained on 2016 data
cannot be deployed against 2019 data without a migration. Module 4 shows how to handle
that — new data source, new features, same problem, same pipeline structure.

Modules 1–3 are left untouched. Students can see both versions side by side.

---

## Data Source

NYC TLC official parquet — direct download, no credentials:
```
https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month:02d}.parquet
```

Training data: 2019, quarterly sample (Jan/Apr/Jul/Oct), 500k rows.

---

## Shared Code

`shared/feature_engineering.py` is the single source of truth for feature engineering —
used by both `pipeline/` at training time and `api/` at serving time.

- `TripFeatureEngineer` — zone ID features, centroid distances, temporal features (23 total)
- `OutlierHandler` — IQR-based clipping fitted on training data
- `build_preprocessor()` — assembles the full sklearn preprocessing Pipeline

The fitted preprocessor is saved as an MLflow artifact alongside the model so the API
loads the exact same transformation used during training.

---

## Quick Start

### Option A — Docker (recommended)

```bash
cd 4-Deploy-Online

# Step 1: train and register the model (runs once, exits when done)
docker compose --profile train run --rm pipeline

# Step 2: start the API
docker compose up api
```

Swagger UI: `http://localhost:8000/docs`

MLflow data (DB + artifacts) is stored in a named Docker volume `mlflow_store`,
shared between the pipeline and API containers.

---

### Option B — Local

```bash
# From repo root
uv sync
source .venv/bin/activate

# Step 1: train
cd 4-Deploy-Online/pipeline
python main.py --sample-size 500000 --tune --promote

# Step 2: serve
cd ../api
uvicorn main:app --port 8000
```

---

### Test a prediction

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "tpep_pickup_datetime": "2019-01-15T14:30:00",
    "PULocationID": 161,
    "DOLocationID": 237,
    "passenger_count": 1,
    "VendorID": 1,
    "RatecodeID": 1,
    "trip_distance": 2.5,
    "payment_type": 1
  }'
```

```json
{
  "predicted_duration_minutes": 19.93,
  "model_version": "v6",
  "model_alias": "champion"
}
```

---

## Pipeline

Prefect-orchestrated training pipeline — 9 steps, 6 models, MLflow tracking.

| Step | What it does |
|------|-------------|
| 1 | Download 2019 TLC parquet, sample 500k rows |
| 2 | Clean data, compute `trip_duration_minutes` target |
| 3 | Train/val/test split before feature engineering (no leakage) |
| 4 | Fit preprocessor on train, transform all sets |
| 5 | Train 6 models (Linear, Ridge, Lasso, RF, GBM, XGBoost) |
| 6 | Tune best model with HalvingRandomSearchCV |
| 7 | Evaluate on held-out test set |
| 8 | Register in MLflow, promote to `@champion`, save preprocessor |
| 9 | Log feature importances |

**Best model:** XGBoost — Test R² **0.817**, MAE **3.07 min**

**Top features:**

| Feature | Importance |
|---------|-----------|
| `trip_distance` | 0.582 |
| `hour_cos` | 0.072 |
| `distance_times_passengers` | 0.070 |
| `centroid_distance_miles` | 0.047 |
| `pickup_hour` | 0.033 |

Run options:
```bash
python main.py --sample-size 50000 --no-tune          # quick smoke test (~3 min)
python main.py --sample-size 500000 --tune --promote  # full run (~25 min)
```

View in MLflow UI:
```bash
cd 4-Deploy-Online/pipeline
mlflow ui --backend-store-uri sqlite:///mlflow_trip_duration.db
# http://127.0.0.1:5000
```

---

## API

FastAPI service — loads `@champion` model + preprocessor from MLflow at startup.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Model version and alias |
| POST | `/predict` | Predict trip duration |

**Request fields:**

| Field | Type | Required |
|-------|------|----------|
| `tpep_pickup_datetime` | string (ISO) | ✅ |
| `PULocationID` | int (1–265) | ✅ |
| `DOLocationID` | int (1–265) | ✅ |
| `trip_distance` | float | ✅ |
| `passenger_count` | int (1–6) | default 1 |
| `VendorID` | int (1–2) | default 1 |
| `RatecodeID` | int (1–6) | default 1 |
| `payment_type` | int (1–6) | default 1 |

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `MLFLOW_TRACKING_URI` | `sqlite:///../pipeline/mlflow_trip_duration.db` | MLflow backend |
| `MODEL_NAME` | `trip_duration_model` | Registered model name |
| `MODEL_ALIAS` | `champion` | Alias to serve |

---

## MLflow Registry

```python
import mlflow
from config.config import MLFLOW_TRACKING_URI

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

# Load champion (used by api/)
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")

# Load challenger (used by retrain/ in Module 5)
model = mlflow.sklearn.load_model("models:/trip_duration_model@challenger")
```
