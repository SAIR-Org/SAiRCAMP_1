
# Evidently Drift Detection — Why and How

---

## Part 1 — The Problem with Static Models

### Why models degrade over time

A model trained on 2019 NYC taxi data makes predictions in 2024.
But the world changed:
- Pickup locations shifted (new neighborhoods, population changes)
- Trip distances changed (Uber/Lyft competition)
- Passenger patterns changed (post-COVID work from home)

**The model doesn't know this.** It's frozen in time.

**Data drift** = the distribution of input data changes over time.

If we don't detect drift:
- Predictions become less accurate
- Users notice before we do
- We scramble to fix it

**We need to detect drift automatically.** Evidently does this.

---

## Part 2 — How Evidently Works

### Reference vs Current comparison

Evidently compares two datasets:

```
Reference (2019-01)    Current (2024-06)
──────────────────     ────────────────
Known "good" data      New data to check
Baseline for drift     Could be drifted
```

### The drift detection process

```python
# From batch/core.py
reference = load_reference_data()  # 2019-01 data
current = df[DRIFT_FEATURE_COLS]   # Current month's features

report = Report([
    DataDriftPreset(drift_share=0.5),
])
report.run(current_data=current, reference_data=reference)
```

**Step by step:**
1. Load reference data (2019-01)
2. Load current data (e.g., 2024-06)
3. For each feature, compare distributions
4. Statistical tests detect if distributions differ
5. Compute drift_score (0.0 - 1.0)
6. If drift_score >= 0.5 → drift detected

### Statistical tests

| Feature type | Test | Threshold |
|---|---|---|
| Numerical | Kolmogorov-Smirnov | p < 0.05 |
| Categorical | Chi-squared | p < 0.05 |

---

## Part 3 — What Features We Monitor

From `batch/core.py`:

```python
DRIFT_FEATURE_COLS = [
    "PULocationID",     # Pickup zone
    "DOLocationID",     # Dropoff zone
    "trip_distance",    # Trip distance
    "passenger_count",  # Number of passengers
    "VendorID",         # Vendor
    "RatecodeID",       # Rate code
]
```

### Why these features?

| Feature | Drift means |
|---|---|
| PULocationID | People taking trips from different areas |
| DOLocationID | Destinations shifting |
| trip_distance | Trip lengths changing |
| passenger_count | Group sizes changing |
| VendorID | Market share shifts |
| RatecodeID | Pricing patterns shift |

---

## Part 4 — Understanding Drift Scores

### Score interpretation

| Score | Status | Meaning |
|---|---|---|
| 0.0 - 0.3 | ✅ Stable | Data similar to training |
| 0.3 - 0.5 | ⚠️ Warning | Some features changing |
| 0.5 - 1.0 | 🚨 Drift | Significant changes |

### Example: Drift in PULocationID

```
Reference (2019):    Current (2024):
PULocationID 161: 5%  PULocationID 161: 2%
PULocationID 237: 3%  PULocationID 237: 8%
PULocationID 132: 2%  PULocationID 132: 6%

Drift Score: 0.72 → 🚨 Drift detected
```

**What to do:**
1. Check if drift is expected (new neighborhoods)
2. If yes → retrain with newer data
3. If no → investigate data quality issues

### Example: Drift in trip_distance

```
Reference (2019):    Current (2024):
Mean: 2.1 miles     Mean: 3.8 miles
Std: 1.5 miles      Std: 2.4 miles

Drift Score: 0.68 → 🚨 Drift detected
```

**What to do:**
1. Check if trips are actually longer
2. If yes → retrain with newer data
3. If no → investigate data quality issues

---

## Part 5 — How Drift Detection Runs

### The batch scoring flow

```python
# From batch/core.py
def score_month(year: int, month: int, champion: dict) -> dict:
    # 1. Load and clean data
    df = pd.read_parquet(url)
    df = clean_data(df)
    
    # 2. Make predictions
    X = champion["preprocessor"].transform(df[FEATURE_COLS])
    y_pred = champion["model"].predict(X)
    y_true = df["trip_duration_minutes"]
    
    # 3. Compute metrics
    mae = mean_absolute_error(y_true, y_pred)
    mae_ratio = mae / champion["train_mae"]
    
    # 4. Run drift detection
    reference = load_reference_data()  # 2019-01
    current_features = df[DRIFT_FEATURE_COLS]
    drift = run_drift_report(current_features, reference, year, month)
    
    # 5. Save results
    return {
        "mae": mae,
        "mae_ratio": mae_ratio,
        "drift_score": drift["drift_score"],
        "drift_detected": drift["drift_detected"],
    }
```

### What gets stored

**SQLite database** (`batch/batch_results.db`):

```sql
CREATE TABLE batch_results (
    year, month, mae, mae_ratio,
    drift_score, drift_detected,
    drift_report_html, drift_report_json,
    alert
);
```

**Drift reports** (`batch/drift_reports/`):

```
drift_2020_04.html   # Full Evidently report
drift_2020_04.json   # Machine-readable
```

**MLflow** logs drift metrics:

```python
mlflow.log_metrics({
    "drift_score": 0.72,
    "drift_detected": 1.0,
    "mae": 3.42,
    "mae_ratio": 1.52,
})
```

---

## Part 6 — The Drift Dashboard

### Streamlit drift tab

From `dashboard/drift_tab.py`:

```python
def render_drift_tab():
    # Get drift data from batch API
    response = requests.get(f"{BATCH_API}/drift/summary")
    data = response.json()
    df = pd.DataFrame(data['summary'])
    
    # Display metrics
    col1.metric("Periods Analyzed", len(df))
    col2.metric("Drift Detected", df['drift_detected'].sum())
    col3.metric("Avg Drift Score", f"{df['drift_score'].mean():.3f}")
    
    # Plot drift over time
    fig = px.bar(
        df,
        x='period',
        y='drift_score',
        color='drift_detected',
        color_discrete_map={0: '#2ecc71', 1: '#e74c3c'}
    )
    fig.add_hline(y=0.5, line_dash="dash", line_color="red")
```

### What the dashboard shows

1. **Drift Score Over Time** (bar chart)
   - Green: No drift (score < 0.5)
   - Red: Drift detected (score >= 0.5)
   - Red dashed line: Threshold at 0.5

2. **Drift Summary Table**
   - Period, drift score, drift status, MAE, alert status

3. **Full HTML Reports**
   - Detailed feature-level analysis
   - Interactive visualizations

---

## Part 7 — What Changed in Module 9

### Added to batch service

**Drift detection** in `batch/core.py`:
- `run_drift_report()` - Evidently drift analysis
- `load_reference_data()` - 2019-01 baseline
- `DRIFT_FEATURE_COLS` - Features to monitor
- `DRIFT_SHARE_THRESHOLD` - 0.5 threshold

**Storage**:
- `batch_results` table with drift columns
- `drift_reports/` directory for HTML/JSON

### Added to dashboard

**Drift tab** in `dashboard/drift_tab.py`:
- Fetches drift data from batch API
- Displays bar chart with threshold
- Shows drift summary table
- Links to full HTML reports

### Added to batch API

**New endpoints**:
- `/drift/summary` - Summary of all drift results
- `/drift/html/{year}/{month}` - HTML report
- `/drift/json/{year}/{month}` - JSON report



### Alert thresholds

| Metric | Threshold | Meaning |
|---|---|---|
| Drift Score | >= 0.5 | Significant data drift |
| MAE Ratio | > 1.5 | Model degrading |
| Total Rows | < 500,000 | Suspiciously low volume |

