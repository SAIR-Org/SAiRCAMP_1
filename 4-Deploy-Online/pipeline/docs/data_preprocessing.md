# Data Preprocessing

**File:** `src/data/data_preprocessing.py`
**Class:** `DataPreprocessor`

---

## What it does

Cleans raw NYC TLC data and prepares the supervised learning dataset.

The component:

* Computes trip duration from pickup and dropoff timestamps
* Removes invalid or physically impossible trips
* Enforces the prediction-time feature contract
* Separates features (`X`) from target (`y`)
* Produces a clean dataset for downstream feature engineering and model training

Typical retention on 2019 TLC data is approximately **96%**.

---

## No Data Leakage Contract

The split between `prediction_time_features` and the target is strictly enforced:

```text
At prediction time you know:          You do NOT know:
  tpep_pickup_datetime                tpep_dropoff_datetime
  PULocationID                        trip_duration_minutes  ← target
  DOLocationID                        fare_amount
  passenger_count                     tip_amount
  VendorID                            total_amount
  RatecodeID
  trip_distance
  payment_type
```

`trip_distance` is treated as a prediction-time feature in this project.

`fare_amount`, `tip_amount`, and `total_amount` are explicitly excluded because they are functions of the completed trip and are unavailable when making a prediction.

---

## Filters Applied

### 1. Trip Duration Filter

```python
min_trip_duration = 60    # seconds (1 minute)
max_trip_duration = 7200  # seconds (2 hours)
```

Removes:

* Trips under 1 minute (meter tests, sensor errors)
* Trips over 2 hours (left-on meters, data entry errors)

---

### 2. Trip Distance Filter

```python
min_trip_distance = 0.1   # miles
max_trip_distance = 50.0  # miles
```

Removes:

* Zero-distance trips
* Extreme outliers outside normal NYC taxi operations

Most airport trips fall within 20–30 miles.

---

### 3. Passenger Count Filter

```python
min_passenger_count = 1
max_passenger_count = 6
```

Removes:

* Zero-passenger records
* Passenger counts exceeding vehicle capacity

---

### 4. Missing Values

Rows with missing values in any `prediction_time_features` column are removed.

In practice, this typically affects less than 0.5% of records and is primarily caused by missing `passenger_count` values.

---

## What Is Not Filtered

The earlier 2016 pipeline used geographic coordinate validation:

```python
df_clean = df_clean[
    df_clean["pickup_latitude"].between(*config.nyc_lat_range)
    & ...
]
```

This filter is intentionally omitted in the current pipeline.

The dataset uses NYC Taxi Zone IDs (`PULocationID`, `DOLocationID`) rather than raw latitude and longitude coordinates. Since zone IDs already represent valid taxi zones, geographic boundary checks are unnecessary.

---

## Target Variable

```python
trip_duration_minutes = (
    tpep_dropoff_datetime - tpep_pickup_datetime
).total_seconds() / 60
```

### Why minutes instead of seconds?

Model evaluation becomes easier to interpret:

* MAE = 3 minutes
* Instead of MAE = 180 seconds

The prediction output is immediately understandable by end users and stakeholders.

---

## Typical Retention Statistics (2019 Data)

| Filter                        | Rows Removed | Reason                                |
| ----------------------------- | -----------: | ------------------------------------- |
| Duration < 1 min or > 2 hrs   |        ~2.5% | Test runs, broken meters              |
| Distance < 0.1 mi or > 50 mi  |        ~0.5% | Zero-distance trips, extreme outliers |
| Passenger count outside range |        ~1.0% | Invalid sensor readings               |
| Missing values                |        ~0.3% | Null feature values                   |
| **Total retained**            |     **~96%** | Clean training data                   |

---

## Output

`run()` returns two objects:

```python
X: pd.DataFrame   # prediction-time features
y: np.ndarray     # trip_duration_minutes
```

At this stage, `X` still contains raw columns.

Feature engineering—including temporal features, zone interactions, centroid features, and derived attributes—is performed downstream by `TripFeatureEngineer`.
