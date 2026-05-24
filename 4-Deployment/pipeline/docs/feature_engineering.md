# Feature Engineering

**File:** `src/features/feature_engineering.py`  
**Classes:** `TripFeatureEngineer`, `OutlierHandler`  
**Function:** `build_preprocessor()`

---

## Overview

Transforms 8 raw input columns into 23 model-ready features. Fits only on training data (no leakage). Handles outliers with IQR clipping. Scales with RobustScaler (outlier-resistant).

```
Input (8 columns):
  tpep_pickup_datetime, PULocationID, DOLocationID,
  passenger_count, VendorID, RatecodeID, trip_distance, payment_type

Output (23 features):
  zone-based (8) + temporal (8) + categorical (2) + interaction (1) + efficiency (1) + centroid (3)
```

---

## The 23 Features

### Zone-Based (5 features)

These replace the lat/lon features from the 2016 pipeline.

| Feature | Formula | What it captures |
|---|---|---|
| `zone_pair` | `PULocationID * 1000 + DOLocationID` | Route identity. Zone 161→236 = Midtown→UES. Tree splits learn per-route timing. |
| `is_same_zone` | `PU == DO` | Very short trip — pickup and dropoff in the same TLC zone. |
| `is_airport_pickup` | `PU ∈ {1, 132, 138}` | EWR, JFK, or LGA pickup. Airport trips have predictable patterns. |
| `is_airport_dropoff` | `DO ∈ {1, 132, 138}` | EWR, JFK, or LGA dropoff. |
| `is_airport_trip` | `airport_pickup OR airport_dropoff` | Either end at an airport. |

**Airport zone IDs:** EWR=1, JFK=132, LGA=138. These are the official TLC zone numbers, stable since 2017.

**Why zone_pair as an integer?**  
Tree models split on thresholds, not categories. The integer `161234` for the route PU=161, DO=234 is just a number the tree can split on. With 263 zones there are up to 69,169 possible pairs — enough variety for the tree to learn per-route mean durations.

---

### Zone Centroid Features (3 features)

The 2016 pipeline had `haversine_distance` and `direction_sin/cos` computed from lat/lon. The 2019 data dropped lat/lon. These features recover that geometric signal using TLC's official zone shapefile.

**Centroid lookup:**  
All 263 zone centroids are precomputed from `taxi_zones.shp` and hardcoded as `ZONE_CENTROIDS` — a dict mapping `LocationID → (x, y)` in EPSG:2263 (NY State Plane, US survey feet). No runtime dependency.

| Feature | Formula | What it captures |
|---|---|---|
| `centroid_distance_miles` | `√((DO_cx - PU_cx)² + (DO_cy - PU_cy)²) / 5280` | Straight-line distance between zone centers in miles. Replaces `haversine_distance`. |
| `centroid_direction_sin` | `sin(atan2(dy, dx))` | Cyclical encoding of travel direction. |
| `centroid_direction_cos` | `cos(atan2(dy, dx))` | Same direction, orthogonal component. |

**Why direction matters:**  
A 2-mile trip northbound on 5th Ave at 8am (inbound commuter traffic) takes longer than the same 2-mile trip southbound. The direction feature lets the model capture this asymmetry when combined with `pickup_hour`.

**Why EPSG:2263 (projected) not WGS84 (lat/lon)?**  
EPSG:2263 is a projected CRS — distances are Euclidean and accurate within NYC. Using it avoids the haversine formula while giving the same result. The coordinate units are US survey feet, so dividing by 5280 gives miles.

---

### Efficiency Ratio (1 feature)

| Feature | Formula | What it captures |
|---|---|---|
| `efficiency_ratio` | `trip_distance / (centroid_distance_miles + 0.1)` | How much longer the actual trip was vs the zone-to-zone straight line. |

A ratio near 1 = direct route. A ratio of 3 = the driver went ~3× the straight-line distance (airport loops, traffic detours, wrong turns). The `+0.1` avoids division by zero on same-zone trips.

---

### Temporal Features (8 features)

Derived from `tpep_pickup_datetime`.

| Feature | Formula | What it captures |
|---|---|---|
| `pickup_hour` | `dt.hour` | Raw hour (0–23) |
| `pickup_dayofweek` | `dt.dayofweek` | Raw day (0=Mon, 6=Sun) |
| `pickup_month` | `dt.month` | Raw month (1–12) |
| `hour_sin` | `sin(2π × hour / 24)` | Cyclical — midnight connects to 23:00 |
| `hour_cos` | `cos(2π × hour / 24)` | Cyclical — orthogonal component |
| `dayofweek_sin` | `sin(2π × dow / 7)` | Cyclical — Sunday connects to Monday |
| `dayofweek_cos` | `cos(2π × dow / 7)` | Cyclical — orthogonal component |
| `is_rush_hour` | `hour ∈ [7,9] ∪ [16,18]` | Binary: AM or PM rush |
| `is_weekend` | `dayofweek ∈ {5, 6}` | Binary: Saturday or Sunday |

**Why both raw and cyclical encoding?**  
Raw integers let the tree split at exact thresholds (e.g., hour > 16 for PM rush). Cyclical sin/cos let the model learn patterns that wrap around midnight or Sunday→Monday.

---

### Categorical Features (2 features)

| Feature | Formula | What it captures |
|---|---|---|
| `is_vendor_2` | `VendorID == 2` | Vendor 2 (VeriFone) vs Vendor 1 (Creative Mobile). Mild duration difference. |
| `is_credit_card` | `payment_type == 1` | Credit card vs cash. Credit card trips tend to have slightly different patterns. |

---

### Interaction Feature (1 feature)

| Feature | Formula | What it captures |
|---|---|---|
| `distance_times_passengers` | `trip_distance × passenger_count` | Longer trips with more passengers. Captures fare-influenced route selection. |

---

## Feature Importance (XGBoost v22)

```
trip_distance              0.582  ███████████████████████  ← dominant
hour_cos                   0.072  ██
distance_times_passengers  0.070  ██
centroid_distance_miles    0.047  █
pickup_hour                0.033  █
pickup_dayofweek           0.032  █
passenger_count            0.027  █
dayofweek_cos              0.022
hour_sin                   0.020
pickup_month               0.019
centroid_direction_sin     0.014
centroid_direction_cos     0.013
zone_pair                  0.012
dayofweek_sin              0.012
is_rush_hour               0.008
efficiency_ratio           0.007
is_vendor_2                0.007
is_credit_card             0.003
is_same_zone               0.000
is_airport_pickup          0.000
is_airport_dropoff         0.000
is_airport_trip            0.000
is_weekend                 0.000
```

**Key observation:** `trip_distance` alone accounts for 58% of the model's decisions. The temporal and centroid features together contribute ~30%. The binary indicators (airports, same zone, weekend) register near zero — the tree learns those patterns through `zone_pair` and `trip_distance` instead.

---

## Preprocessing Pipeline

```python
build_preprocessor() returns sklearn.Pipeline([
    ('feature_engineer', TripFeatureEngineer()),       # raw → 23 features
    ('outlier_handler',  OutlierHandler(factor=1.5)), # IQR clipping
    ('scaler',           RobustScaler()),              # median/IQR scaling
])
```

**OutlierHandler:** IQR-based clipping with `factor=1.5`. Fits lower/upper bounds on training data, applies them to val and test. Does not remove rows — clips values to bounds in place.

**RobustScaler:** Centers on median, scales by IQR. Resistant to outliers in `trip_distance` and `zone_pair` (which has a wide range: 1001–264263).

**No leakage:** The pipeline is `.fit()` on training data only. `.transform()` is applied separately to val and test.

---

## How Drift Affects Features

When this model is applied to 2020/2022/2024 data:

| Year | What changes |
|---|---|
| 2020 (COVID) | `trip_distance` distribution shifts up (fewer short trips), `pickup_hour` patterns collapse, `is_airport_trip` near zero |
| 2022 (recovery) | `zone_pair` distribution changes — Uber took back short trips, taxis only get long ones |
| 2024 | Fares ~45% higher — the model underestimates duration (trained on 2019 when trips were cheaper and shorter) |

This feature set was deliberately designed to make drift visible. See `../monitoring/` for drift detection.
