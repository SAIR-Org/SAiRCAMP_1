# Data Acquisition

**File:** `src/data/data_acquisition.py`  
**Class:** `DataAcquisition`

---

## What it does

Downloads NYC TLC yellow taxi trip data directly from the official source as Parquet files, samples each month independently, and returns a combined DataFrame ready for preprocessing.

---

## Data Source

```
URL template:
  https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month:02d}.parquet

Example:
  https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2019-01.parquet
```

No credentials needed. Any year from 2017 onward. The TLC updates this monthly.

**Why not Kaggle?**  
Modules 1–3 use a static Kaggle snapshot of 2016 data. Module 4 needs live, time-stamped data so that batch scoring on 2020/2022/2024 produces real drift — not synthetic drift.

---

## Training Data Configuration

```python
train_year   = 2019
train_months = [1, 4, 7, 10]   # Jan, Apr, Jul, Oct = seasonal coverage
sample_size  = 500_000          # total rows across all months
```

**Why 2019?**  
The model trains on pre-COVID NYC patterns. Scoring on 2020 (COVID collapse), 2022 (recovery), and 2024 (new normal) produces three distinct types of drift — the core teaching narrative of Module 4.

**Why quarterly, not all 12 months?**  
Each 2019 month has ~7.7M rows. All 12 months = ~90M rows before sampling. Quarterly covers all four seasons with only 4 downloads (~30M rows total).

**Why 500k rows?**  
XGBoost on this feature set does not improve past ~500k samples. R² is stable from 200k onward. Downloading more data takes longer for zero gain.

---

## Memory Strategy

Peak memory is kept under 1GB by sampling each month before combining:

```
for each month:
  download full month  (~740 MB in RAM)
  sample 125k rows
  free the full month  (del df_month)

combine 4 × 125k = 500k rows  (~48 MB)
```

If all 4 months were kept before sampling, peak RAM would be ~3GB. This approach keeps peak RAM at ~800MB: one full month + accumulated samples.

---

## Columns Fetched

Only 12 of the 20+ columns in the parquet file are downloaded. Parquet is columnar — fetching 12 of 20 columns downloads ~60% of the file size.

```python
raw_columns = [
    'tpep_pickup_datetime',    # → trip duration target
    'tpep_dropoff_datetime',   # → trip duration target
    'PULocationID',            # → zone-based features
    'DOLocationID',            # → zone-based features
    'passenger_count',         # → feature
    'trip_distance',           # → feature (strongest predictor)
    'VendorID',                # → is_vendor_2 feature
    'RatecodeID',              # → feature
    'payment_type',            # → is_credit_card feature
    'fare_amount',             # → kept for future drift monitoring
    'tip_amount',              # → kept for future drift monitoring
    'total_amount',            # → kept for future drift monitoring
]
```

`fare_amount`, `tip_amount`, `total_amount` are **not used as model features** (they're only known after the trip ends — using them would be data leakage). They're fetched for drift monitoring in `../monitoring/`.

---

## Retry Logic

Retries are **not** handled in this class. They live in `flow.py`:

```python
@task(name="acquire-data", retries=3, retry_delay_seconds=10)
def acquire_data(config): ...
```

Why here and not in the class? The Prefect `@task` retry is visible in the UI — you can see which month failed and how many retries happened. A retry decorator buried inside a class method is invisible.

---

## Validation

After combining all months, `validate_data()` checks that all required columns are present:

```python
required = prediction_time_features + ['tpep_dropoff_datetime']
```

If any column is missing, the pipeline raises `ValueError` immediately rather than failing silently later during feature engineering.
