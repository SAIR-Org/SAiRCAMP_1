# NYC Taxi ML Pipeline v2 — TLC 2019 Data

Production pipeline for Module 4.
Built on top of `pipeline_with_prefect/` — same Prefect structure, same orchestration pattern.

**This pipeline differs from `pipeline_with_prefect/` in two ways:**
1. **Data source** — TLC 2019 parquet (zone IDs) instead of Kaggle 2016 CSV (lat/lon)
2. **Model improvements** — XGBoost added, centroid features added to recover geometric signal

---

## What Changed vs `pipeline_with_prefect/`

| File | What changed | Why |
|---|---|---|
| `config/config.py` | Kaggle params → TLC URL; XGBoost added; absolute MLflow URI | New data source; model upgrade; multi-component deployment |
| `src/data/data_acquisition.py` | kagglehub → HTTP parquet download; per-month sampling | TLC is direct, no credentials; memory efficiency |
| `src/data/data_preprocessing.py` | Removed lat/lon bounds filter (5 lines) | Zone IDs are always valid NYC zones |
| `src/features/feature_engineering.py` | lat/lon features → zone ID + centroid features | Schema changed; centroid features recover geometric signal |
| `src/models/model_training.py` | Added XGBoost; `artifact_path` → `name` | Better model; MLflow 3.x API change |
| `src/models/model_registry.py` | Stages → Aliases (`@champion`/`@challenger`) | MLflow 3.x removed stage-based transitions |
| `flow.py` | Feature importance task (Step 9); test metrics fix; alias labels | New logging; bug fix; MLflow 3.x |
| `main.py` | Identical | — |

---

## The Schema Change

NYC TLC updated their data format in 2017:

```
2016 format (pipeline_with_prefect)    2019 format (this pipeline)
──────────────────────────────────     ──────────────────────────────────
pickup_longitude     float64      →    PULocationID    int64  (1–265)
pickup_latitude      float64      →    DOLocationID    int64  (1–265)
dropoff_longitude    float64           (removed)
dropoff_latitude     float64           (removed)
tpep_pickup_datetime    ✅             tpep_pickup_datetime    ✅
passenger_count         ✅             passenger_count         ✅
trip_distance           ✅             trip_distance           ✅
VendorID                ✅             VendorID                ✅
RatecodeID              ✅             RatecodeID              ✅
payment_type            ✅             payment_type            ✅
```

---

## Feature Changes

```
REMOVED (lat/lon-based — columns no longer exist in 2019 data):
  haversine_distance        computed from lat/lon
  manhattan_distance        computed from lat/lon
  direction_sin / cos       computed from lat/lon delta
  pickup_from_jfk           distance to JFK GPS coords
  pickup_from_lga           distance to LGA GPS coords
  is_jfk_trip               based on pickup_from_jfk < 2
  is_lga_trip               based on pickup_from_lga < 2
  efficiency_ratio          haversine / trip_distance  (old lat/lon version)

ADDED (zone ID-based — schema migration fix + signal recovery):
  zone_pair                 PULocationID * 1000 + DOLocationID  (route identity)
  is_same_zone              pickup == dropoff zone
  is_airport_pickup         PULocationID in {1, 132, 138}  (EWR/JFK/LGA)
  is_airport_dropoff        DOLocationID in {1, 132, 138}
  is_airport_trip           either end is an airport

  centroid_distance_miles   Euclidean distance between zone centroids
                            Replaces haversine_distance. Centroids precomputed
                            from TLC official shapefile (taxi_zones.shp).

  centroid_direction_sin    Cyclical direction between centroids
  centroid_direction_cos    Replaces direction_sin/cos. Captures rush-hour
                            asymmetry: same corridor, opposite direction →
                            different duration.

  efficiency_ratio          trip_distance / (centroid_distance_miles + 0.1)
                            Detour factor. High = driver took a longer route
                            than the straight-line distance suggests.

UNCHANGED:
  pickup_hour, pickup_dayofweek, pickup_month
  hour_sin, hour_cos, dayofweek_sin, dayofweek_cos
  is_rush_hour, is_weekend
  is_vendor_2, is_credit_card
  distance_times_passengers

TOTAL: 19 features (pipeline_with_prefect) → 23 features (this pipeline)
```

---

## Model Results

| Pipeline | Best model | Test R² | MAE |
|---|---|---|---|
| `pipeline_with_prefect` (2016, lat/lon) | Gradient Boosting | 0.838 | 2.26 min |
| This pipeline — zone IDs only | Random Forest | 0.783 | 3.35 min |
| This pipeline — + centroid features | Random Forest | 0.812 | 3.11 min |
| **This pipeline — + XGBoost** | **XGBoost** | **0.817** | **3.07 min** |

The remaining gap vs 2016 (~0.02 R²) is structural: centroid features are zone-level
approximations, whereas 2016 had trip-level lat/lon. That's an acceptable trade-off.

### XGBoost Feature Importance (top 10 from v22)

| Feature | Importance | What it captures |
|---|---|---|
| `trip_distance` | 0.582 | Actual metered miles — strongest single predictor |
| `hour_cos` | 0.072 | Time of day (cyclical) |
| `distance_times_passengers` | 0.070 | Interaction feature |
| `centroid_distance_miles` | 0.047 | Geometric distance between zones |
| `pickup_hour` | 0.033 | Raw hour |
| `pickup_dayofweek` | 0.032 | Day of week |
| `passenger_count` | 0.027 | Group size |
| `dayofweek_cos` | 0.022 | Day of week (cyclical) |
| `hour_sin` | 0.020 | Time of day (cyclical) |
| `pickup_month` | 0.019 | Seasonality |

---

## Data Source

**Old:** Kaggle snapshot `elemento/nyc-yellow-taxi-trip-data` (static, 2016-01 only)

**New:** NYC TLC official data, direct parquet download, any year/month:
```
https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month:02d}.parquet
```

No Kaggle account needed. No local file.

**Training data:** 2019, quarterly sample (Jan/Apr/Jul/Oct = seasonal coverage)
```python
train_year   = 2019
train_months = [1, 4, 7, 10]   # change to list(range(1,13)) for full year
sample_size  = 500000           # ~125k per month
```

**Raw data volume:** ~7.7M rows/month → 28.7M total across 4 months → 500k sampled (1.7%).
500k is sufficient for XGBoost on this feature set; R² does not improve past ~1M samples.

---

## MLflow Registry

This pipeline uses **separate MLflow database and model name** from Module 3:

```
pipeline_with_prefect:  mlflow_nyc_taxi.db     model: nyc_taxi_predictor
this pipeline:          mlflow_nyc_taxi_v2.db   model: nyc_taxi_v2
```

**MLflow 3.x alias convention** (replaces deprecated stage transitions):

```python
# Load champion (what api/, batch/, monitoring/ use):
mlflow.sklearn.load_model("models:/nyc_taxi_v2@champion")

# Load challenger (what retrain/ compares against):
mlflow.sklearn.load_model("models:/nyc_taxi_v2@challenger")
```

The tracking URI is absolute and anchored to this directory:
```python
from config.config import MLFLOW_TRACKING_URI  # import this in all downstream components
```

---

## How to Run

### 1. Setup (first time only)

```bash
# From the repo root
uv sync
source .venv/bin/activate

cd 4-Deployment/pipeline
```

### 2. Run the pipeline

```bash
# Quick smoke test — 50k rows, no tuning (~5 min)
python main.py --sample-size 50000 --no-tune

# Standard run — 500k rows with tuning, registers @challenger (~25 min)
python main.py --sample-size 500000 --tune

# Full run + promote winner to @champion
python main.py --sample-size 500000 --tune --promote
```

Expected output (abridged):

```
Step 1  ✅ Loaded 500,000 rows
Step 2  ✅ 480,899 rows retained (96.2%)
Step 3  ✅ Train 307k / Val 77k / Test 96k
Step 4  ✅ 23 engineered features
Step 5  ✅ 6 models trained
        🏆 Best: XGBoost | Val R²: 0.8156
Step 6  ✅ Tuning complete
Step 7  ✅ Test R²: 0.817 | MAE: 3.07 min
Step 8  ✅ Model v28 → @challenger
Step 9  ✅ Feature importances logged
```

### 3. View results in MLflow

```bash
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi_v2.db
# Open http://127.0.0.1:5000
```

What you'll see: all 6 model runs per pipeline execution, sortable by any metric.
The registered model `nyc_taxi_v2` shows version history with `@champion`/`@challenger` aliases.

### 4. Optional — watch the pipeline live in Prefect UI

```bash
# Terminal 1
prefect server start
# Open http://127.0.0.1:4200

# Terminal 2
python main.py --sample-size 500000 --tune --promote
```

Each of the 9 steps appears as a node in the flow graph with timing, logs, and retry state.

### 5. Load the registered model

```python
import mlflow
from config.config import MLFLOW_TRACKING_URI

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
model = mlflow.sklearn.load_model("models:/nyc_taxi_v2@champion")
```

This is the exact pattern used by `api/`, `batch/`, and `monitoring/`.

---

## Project Structure

```
pipeline/
├── flow.py          Prefect @flow + @tasks (9 steps)
├── main.py          CLI entry point
├── requirements.txt
├── config/
│   └── config.py    DataConfig, ModelConfig, MLflowConfig, load_config()
└── src/
    ├── data/
    │   ├── data_acquisition.py      TLC parquet download, per-month sampling
    │   └── data_preprocessing.py   Duration filter, distance filter, feature/target split
    ├── features/
    │   └── feature_engineering.py  23 features: zone + centroid + temporal + categorical
    ├── models/
    │   ├── model_training.py       6 models, MLflow tracking, HalvingRandomSearchCV
    │   └── model_registry.py       @champion/@challenger aliases (MLflow 3.x)
    └── utils/
        └── (empty — Prefect handles logging and retries)
```

---

## Why This Pipeline Exists

Modules 1–3 use a static Kaggle snapshot from 2016. That works for learning tools.
Module 4 needs real production data to tell the drift story:

```
Train here:   2019 → model learns pre-COVID NYC taxi patterns
Batch score:  2020 → COVID collapse, model breaks          (volume drift)
              2022 → new normal, trip patterns changed     (feature drift)
              2024 → fares 45% higher, world changed again (label drift)
```

The drift story only works because this pipeline uses real production data.
The batch scorer (`../batch/`) and monitoring (`../monitoring/`) consume the
model registered by this pipeline.

---

## What's Next

```
pipeline/    ← you are here — trains and registers the model
api/         ← loads the model, serves /predict (online deployment)
batch/       ← loads the model, scores 2020/2022/2024 (offline deployment)
monitoring/  ← reads batch results, detects drift, fires alerts
retrain/     ← triggered by monitoring, runs champion/challenger comparison
dashboard/   ← Streamlit UI tying everything together
```
