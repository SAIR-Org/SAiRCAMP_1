# Monitoring Concepts — Mental Model, Concepts & Reference

---

## Part 1 — What Is Monitoring? (The Mental Model)

### Start with a car dashboard

You're driving. The speedometer shows speed. The fuel gauge shows fuel.
The temperature gauge shows engine heat. The check engine light comes on when something's wrong.

Without the dashboard, you'd feel the car vibrating weirdly or smell something burning —
but you wouldn't know until it's too late. The dashboard translates the car's internal
state into signals you can see and act on.

**Monitoring is your ML system's dashboard.**

Without monitoring, your model is a black box. It's either working or not.
When it breaks, users complain, and you scramble to figure out what happened.

With monitoring, you see:
- How many predictions per minute (volume)
- How fast they're served (latency)
- How often they fail (error rate)
- What distribution of predictions (model output)
- What distribution of inputs (data drift)

---

### The three types of monitoring in this project

| Type | What it monitors | Tool | When to check |
|---|---|---|---|
| **Operational** | Is the API running? | Prometheus + Grafana | Every minute |
| **Performance** | Is the model still accurate? | Batch scoring + Evidently | Every month |
| **Data Drift** | Is the input data changing? | Evidently + Streamlit | Every month |

**Why three types?** Each answers a different question:
- Operational: "Is the API working?" → You need this every day
- Performance: "Is the model still accurate?" → You need this every month
- Data drift: "Is the input data changing?" → You need this every month

---

## Part 2 — What We Monitor in This Project

### Operational Metrics (Prometheus)

From `api/metrics.py`:

```python
# HTTP Request Metrics
REQUEST_COUNT        # Total requests (method, endpoint, status)
REQUEST_LATENCY      # How long requests take (histogram)

# Prediction Metrics
PREDICTION_COUNT     # Total predictions made
PREDICTION_VALUE     # Last predicted duration (gauge)
PREDICTION_LATENCY   # Time to compute prediction (histogram)

# Model Metrics
MODEL_INFO           # Model version and alias

# System Metrics
ACTIVE_REQUESTS      # Concurrent requests being processed
```

These metrics tell us:
- **Traffic:** How many predictions are being made?
- **Latency:** Is the API slowing down?
- **Errors:** Are requests failing?
- **Saturation:** Is the system overloaded?

These are the **Four Golden Signals** from Google SRE — the four metrics every system should monitor.

---

### Performance Metrics (Batch Scoring)

From `batch/core.py`:

```python
MAE                    # Mean Absolute Error on new data
MAE_RATIO              # MAE / training_MAE (alert if > 1.5)
TOTAL_ROWS             # Number of records scored (alert if < 500k)
DRIFT_SCORE            # Evidently drift score (0.0 - 1.0)
DRIFT_DETECTED         # Boolean: drift score >= 0.5
```

These metrics tell us:
- **MAE:** Is the model still accurate?
- **MAE Ratio:** Is accuracy degrading compared to training?
- **Total Rows:** Is data volume suspiciously low?
- **Drift Score:** Is the input data changing?

---

### Data Drift Metrics (Evidently)

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

Evidently compares each feature's distribution to a reference dataset (2019-01):

```
Reference Distribution    Current Distribution    Drift Detected?
────────────────────      ──────────────────      ────────────────
PULocationID: 161=5%      PULocationID: 161=5.2%  ✅ No drift
trip_distance: mean=2.1   trip_distance: mean=3.8  🚨 Drift detected!
```

---

## Part 3 — How Monitoring Works in This Project

### The data flow

```
1. API receives prediction request
   ├── Logs: REQUEST_COUNT, REQUEST_LATENCY
   ├── Computes prediction
   └── Logs: PREDICTION_COUNT, PREDICTION_VALUE, PREDICTION_LATENCY

2. Prometheus scrapes /metrics every 10 seconds
   └── Stores time-series data

3. Grafana queries Prometheus
   └── Displays dashboards

4. Batch service runs monthly
   ├── Scores historical data
   ├── Computes MAE and MAE_RATIO
   ├── Runs Evidently drift detection
   └── Logs to MLflow and SQLite

5. Streamlit dashboard reads batch_results.db
   └── Displays drift reports
```

---

### The three dashboards

| Dashboard | Source | What it shows |
|---|---|---|
| **Operational** | Prometheus | Request rate, latency, errors, active requests |
| **Business** | Prometheus | Prediction volume, prediction distribution, model version |
| **Model Performance** | Batch + Evidently | MAE, MAE ratio, drift score, drift detection |

---

## Part 4 — What the Numbers Mean

### Latency (API speed)

```
Healthy:   p95 < 100ms     → API is fast
Warning:   p95 100-500ms   → API is slowing down
Alert:     p95 > 500ms     → API is too slow, investigate
```

**What to check when latency spikes:**
- Is CPU usage high?
- Is memory full?
- Is the model too complex?
- Is the database slow?

---

### Error Rate (API failures)

```
Healthy:   < 0.1%    → Almost no failures
Warning:   0.1-1%    → Some failures, investigate
Alert:     > 1%      → Too many failures, urgent
```

**What to check when error rate spikes:**
- Is the model loaded?
- Is the preprocessor working?
- Are inputs valid?
- Is the service crashing?

---

### MAE Ratio (Model accuracy)

```
Healthy:   < 1.2    → Model is as good as training
Warning:   1.2-1.5  → Model is degrading
Alert:     > 1.5    → Model is much worse, retrain needed
```

**What to check when MAE ratio increases:**
- Is data drift detected?
- Has the model been updated?
- Is the data different from training?
- Is the reference data still valid?

---

### Drift Score (Data distribution)

```
Healthy:   < 0.3    → Data is stable
Warning:   0.3-0.5  → Some features are changing
Alert:     > 0.5    → Significant drift detected
```

**What to check when drift score increases:**
- Which features are drifting?
- Is the drift expected (seasonal)?
- Should we retrain?
- Is the reference data outdated?

---

## Part 5 — Alert Conditions in This Project

### Alert thresholds from `batch/core.py`

```python
MAE_RATIO_THRESHOLD = 1.5        # MAE / training_MAE
VOLUME_THRESHOLD = 500_000       # Minimum rows per month
DRIFT_SHARE_THRESHOLD = 0.5      # Evidently drift score
```

**When alerts trigger:**

| Condition | Alert | Action |
|---|---|---|
| MAE Ratio > 1.5 | 🚨 Model degrading | Retrain model |
| Total Rows < 500k | ⚠️ Low data volume | Check data source |
| Drift Score > 0.5 | 🚨 Data drift | Investigate features |
| Drift + MAE Ratio | 🔴 Both degrading | Retrain with new data |

---

## Part 6 — The Alert Flow

```
1. Batch scoring runs for a month
   ├── Computes MAE and MAE_RATIO
   ├── Computes DRIFT_SCORE
   └── Saves results to SQLite

2. Alert logic checks:
   ├── MAE_RATIO > 1.5 → alert = 1
   ├── TOTAL_ROWS < 500k → alert = 1
   └── DRIFT_SCORE > 0.5 → drift_detected = 1

3. Alert stored in batch_results.db
   └── Query later to find problematic months

4. Streamlit dashboard shows:
   ├── Red bars for drifted months
   ├── Alert status column
   └── Recommendation: "Retrain with new data"
```

---

## Part 7 — What We Don't Monitor (Yet)

### Natural next steps for production

| Missing | Why it matters | How to add |
|---|---|---|
| **Model performance drift** | R², RMSE trending down | Log during batch scoring |
| **Feature importance drift** | Which features matter | Evidently drift report |
| **Prediction distribution** | Model outputs changing | Log prediction values |
| **Data quality** | Missing values, outliers | Evidently data quality |
| **Alerting** | Send notifications | Grafana alerts, PagerDuty |
| **SLAs/SLOs** | Service level targets | Define and track |

---

## Quick Reference

### Key metrics to watch daily

```bash
# Check API health
curl https://your-domain.com/api/health

# Check batch health
curl https://your-domain.com/batch/health

# Check latest batch results
curl https://your-domain.com/batch/results

# Check drift summary
curl https://your-domain.com/batch/drift/summary
```

### Key dashboards

```
Operational Dashboard     → http://localhost:3000/d/operational
Business Dashboard        → http://localhost:3000/d/business
Model Performance         → http://localhost:3000/d/model-performance
Streamlit Dashboard       → http://localhost:1080
```

### Alert thresholds

| Metric | Healthy | Warning | Alert |
|---|---|---|---|
| API Latency (p95) | < 100ms | 100-500ms | > 500ms |
| Error Rate | < 0.1% | 0.1-1% | > 1% |
| MAE Ratio | < 1.2 | 1.2-1.5 | > 1.5 |
| Drift Score | < 0.3 | 0.3-0.5 | > 0.5 |
| Prediction Volume | > 500k | 300-500k | < 300k |
