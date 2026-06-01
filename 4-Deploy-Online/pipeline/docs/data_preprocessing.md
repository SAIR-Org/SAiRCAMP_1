# Data Preprocessing

**File:** `src/data/data_preprocessing.py`  
**Class:** `DataPreprocessor`

---

## What it does

Cleans the raw TLC data and prepares features and target. Applies filters to remove physically impossible trips. Computes the target variable (`trip_duration_minutes`) from pickup and dropoff timestamps.

Produces ~96% row retention on typical 2019 data.

---

## No Data Leakage Contract

The split between `prediction_time_features` and target is strictly enforced:

```
At prediction time you know:          You do NOT know:
  tpep_pickup_datetime                  tpep_dropoff_datetime
  PULocationID                          trip_duration_minutes  ← this is the target
  DOLocationID                          fare_amount
  passenger_count                       tip_amount
  VendorID                              total_amount
  RatecodeID
  trip_distance
  payment_type
```

`trip_distance` is the odometer reading recorded *during* the trip. It is available at trip end — but in a real system it would be known at prediction time from GPS. It's included as a feature.

`fare_amount` and `tip_amount` are explicitly excluded from features — they are a function of duration and cannot be known before the trip ends.

---

## Filters Applied

### 1. Trip Duration Filter

```python
min_trip_duration = 60    # seconds (1 minute)
max_trip_duration = 7200  # seconds (2 hours)
```

Removes:
- Trips under 1 min — meter test runs, sensor errors
- Trips over 2 hours — left-on meters, data entry errors

### 2. Trip Distance Filter

```python
min_trip_distance = 0.1   # miles
max_trip_distance = 50.0  # miles
```

Removes:
- Zero-distance trips — meter ran but car didn't move
- Trips over 50 miles — outside normal NYC taxi range (airport runs are 20–30 miles max)

### 3. Passenger Count Filter

```python
min_passenger_count = 1
max_passenger_count = 6
```

Removes zero passengers (sensor default when not set) and 7+ passengers (exceeds vehicle capacity).

### 4. Missing Values

Drops rows with missing values in any `prediction_time_features` column. In practice this removes <0.5% of rows — mostly `passenger_count` nulls.

### What's NOT filtered (vs 2016 pipeline)

The 2016 pipeline had a geographic coordinate bounds filter:
```python
# REMOVED in this pipeline — not needed for zone IDs
df_clean = df_clean[
    df_clean['pickup_latitude'].between(*config.nyc_lat_range) & ...
]
```

Zone IDs (1–265) are by definition valid NYC zones. There are no out-of-bounds coordinates to filter.

---

## Target Variable

```python
trip_duration_minutes = (tpep_dropoff_datetime - tpep_pickup_datetime).total_seconds() / 60
```

**Why minutes, not seconds?**  
MAE of 3 minutes is more interpretable than MAE of 180 seconds. The model output is directly usable as a human-readable estimate.

---

## Typical Retention Stats (2019 data)

| Filter | Rows removed | Reason |
|---|---|---|
| Duration < 1 min or > 2 hrs | ~2.5% | Test runs, broken meters |
| Distance < 0.1 or > 50 mi | ~0.5% | Zero-distance, extreme outliers |
| Passenger count out of range | ~1.0% | Missing/invalid sensor readings |
| Missing values | ~0.3% | Null passenger_count |
| **Total retained** | **~96%** | |

---

## Output

`run()` returns two objects:

```python
X: pd.DataFrame   # prediction_time_features only, shape (N, 8)
y: np.ndarray     # trip_duration_minutes, shape (N,)
```

The DataFrame `X` still contains raw columns at this stage — feature engineering (zone pair, centroids, temporal features) happens downstream in `TripFeatureEngineer`.
