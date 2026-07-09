# Module 9 — Monitoring & Observability

**Project:** NYC Yellow Taxi Trip Duration Prediction  
**New layer:** Monitoring — know when your model degrades in production

---

## What This Module Adds

Module 8 deployed the app with CI/CD and SSL. Module 9 makes the system **observable** — you can see what's happening, detect problems before users complain, and debug issues with data.

```
Module 8   deployed + automated
Module 9   deployed + automated + monitored  ← this module
```

**Before:** Model in production. No one knows if it's still good. Six months later: predictions are wrong, users complain, you scramble.

**With monitoring:** You know immediately when:
- Prediction latency spikes (API slowing down)
- Error rate increases (something is broken)
- Data distribution drifts (input data changed)
- Model performance degrades (MAE increases)

---

## The Three Layers of Monitoring

This module adds **three complementary monitoring systems**:

| Layer | Tool | What It Monitors | Dashboard |
|---|---|---|---|
| **Operational** | Prometheus + Grafana | API health: latency, errors, traffic, predictions | Real-time graphs |
| **Performance** | Batch + Evidently | Model quality: MAE, MAE ratio, volume | Drift reports |
| **Data Drift** | Evidently + Streamlit | Feature distributions: drift score, drift detection | Interactive dashboard |

**Why three layers?** Each answers a different question:
- Operational: "Is the API working?" → Prometheus
- Performance: "Is the model still accurate?" → Batch scoring
- Data drift: "Is the input data changing?" → Evidently

---

## Learning Path

Work through the files in this order:

```
Step 1   docker-compose up -d           Start the full monitoring stack locally
Step 2   http://localhost:9090          Explore Prometheus metrics locally
Step 3   http://localhost:3000          Explore Grafana dashboards locally
Step 4   POST /score                    Run batch scoring with drift detection
Step 5   http://localhost:1080          View drift in Streamlit dashboard locally
Step 6   Deploy to VPS                  Deploy monitoring to production
```

---

## Part 1 — Operational Monitoring (Prometheus + Grafana)

### What Gets Monitored

The API service exposes metrics at `/metrics` endpoint:

```python
# From api/metrics.py
REQUEST_COUNT        # Total HTTP requests (by method, endpoint, status)
REQUEST_LATENCY      # HTTP request latency (histogram)
PREDICTION_COUNT     # Total predictions made
PREDICTION_VALUE     # Last predicted duration (gauge)
PREDICTION_LATENCY   # Time to compute prediction (histogram)
MODEL_INFO           # Model version and alias (info)
ACTIVE_REQUESTS      # Concurrent requests being processed
```

### How Prometheus Collects

Prometheus scrapes `/metrics` every 10 seconds:

```yaml
# monitoring/prometheus/prometheus.yml
scrape_configs:
  - job_name: 'api'
    static_configs:
      - targets: ['api:1078']
    metrics_path: '/metrics'
    scrape_interval: 10s
```

### The Three Grafana Dashboards

| Dashboard | What It Shows | When To Use |
|---|---|---|
| **Operational** | Request rate, latency percentiles, error rate, active requests | Daily: "Is the API healthy?" |
| **Business** | Prediction volume, prediction distribution, model version | Weekly: "What are users asking?" |
| **Model Performance** | MAE over time, drift score, prediction vs actual | Monthly: "Is the model degrading?" |

---

## Part 2 — Performance Monitoring (Batch Scoring)

### What Gets Monitored

The batch service scores historical data and tracks model performance:

```python
# From batch/core.py
MAE                    # Mean Absolute Error on new data
MAE_RATIO              # MAE / training_MAE (alert if > 1.5)
TOTAL_ROWS             # Number of records scored (alert if < 500k)
DRIFT_SCORE            # Evidently drift score (0.0 - 1.0)
DRIFT_DETECTED         # Boolean: drift score >= 0.5
```

### How It Works

1. **Load champion model** from MLflow registry
2. **Score a month** of NYC taxi data
3. **Compute MAE** against actual trip durations
4. **Run drift detection** comparing features to reference (2019-01)
5. **Save results** to SQLite and MLflow
6. **Generate drift reports** (HTML + JSON)

### Trigger Batch Scoring

```bash
# Score a specific month
curl -X POST "https://your-domain.com/batch/score?year=2020&month=4"

# Score multiple months
curl -X POST "https://your-domain.com/batch/score-range?start=2020-01&end=2020-06"

# View all results
curl "https://your-domain.com/batch/results"
```

### Alert Conditions

| Condition | Threshold | What It Means |
|---|---|---|
| MAE Ratio | > 1.5 | Model is performing worse than training |
| Total Rows | < 500,000 | Data volume is suspiciously low |
| Drift Score | > 0.5 | Input data distribution has changed significantly |

---

## Part 3 — Data Drift Monitoring (Evidently)

### What Drift Detection Does

Evidently compares current data to a **reference dataset** (2019-01):

```python
# From batch/core.py
reference = load_reference_data()  # 2019-01 data
current = df[DRIFT_FEATURE_COLS]   # Current month's features

report = Report([
    DataDriftPreset(drift_share=0.5),
    DriftedColumnsCount(drift_share=0.5),
])
report.run(current_data=current, reference_data=reference)
```

### Features Monitored for Drift

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

### Understanding Drift Score

| Score | Status | What To Do |
|---|---|---|
| 0.0 - 0.3 | ✅ Stable | Data similar to training |
| 0.3 - 0.5 | ⚠️ Warning | Some features changing — investigate |
| 0.5 - 1.0 | 🚨 Drift | Significant changes — consider retraining |

### View Drift Reports

The Streamlit dashboard provides:

1. **Drift Score Over Time** (bar chart with threshold line)
2. **Drift Summary Table** (period, score, status, MAE, alert)
3. **Full HTML Reports** (detailed Evidently analysis)
4. **Drift Detection Alerts** (red/green indicators)

---

## Part 4 — Docker Compose with Monitoring

### Local Development `docker-compose.yml`

```yaml
services:
  # ─────────────────────────────────────────────────────────────
  # MLflow Tracking Server
  # ─────────────────────────────────────────────────────────────
  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    container_name: mlflow-server
    command: >
      mlflow server
      --host 0.0.0.0
      --port 1081
      --backend-store-uri sqlite:////mlflow/mlflow.db
      --default-artifact-root mlflow-artifacts:/
      --artifacts-destination /mlruns
      --serve-artifacts
      --uvicorn-opts "--forwarded-allow-ips=*"
      --allowed-hosts "*"
    environment:
      - MLFLOW_TRACKING_URI=http://mlflow:1081
    ports:
      - "1081:1081"
    volumes:
      - ./mlflow:/mlflow
      - ./mlruns:/mlruns
    restart: unless-stopped

  # ─────────────────────────────────────────────────────────────
  # Prometheus Metrics Server
  # ─────────────────────────────────────────────────────────────
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"  
    restart: unless-stopped
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.enable-lifecycle'

  # ─────────────────────────────────────────────────────────────
  # Grafana
  # ─────────────────────────────────────────────────────────────
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    volumes:
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
      # SMTP for email alerts (optional)
      - GF_SMTP_ENABLED=true
      - GF_SMTP_HOST=smtp.gmail.com:587
      - GF_SMTP_USER=your-email@gmail.com
      - GF_SMTP_PASSWORD=your-app-password
      - GF_SMTP_FROM_ADDRESS=your-email@gmail.com
      - GF_SMTP_FROM_NAME=MLOps API Dashboard
      - GF_SMTP_SKIP_VERIFY=true
    ports:
      - "3000:3000"
    restart: unless-stopped
    depends_on:
      - prometheus

  # ─────────────────────────────────────────────────────────────
  # Online Serving (FastAPI) - WITH METRICS
  # ─────────────────────────────────────────────────────────────
  api:
    build:
      context: .
      dockerfile: api/Dockerfile
    container_name: api-server
    volumes:
      - ./pipeline:/app/pipeline
    environment:
      - MLFLOW_TRACKING_URI=http://mlflow:1081
      - ROOT_PATH=/api
    depends_on:
      - mlflow
      - prometheus
    ports:
      - "1078:1078"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:1078/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # ─────────────────────────────────────────────────────────────
  # Offline Batch Scoring
  # ─────────────────────────────────────────────────────────────
  batch:
    build:
      context: .
      dockerfile: batch/Dockerfile
    container_name: batch-server
    volumes:
      - ./pipeline:/app/pipeline
      - ./batch:/app/data
    environment:
      - MLFLOW_TRACKING_URI=http://mlflow:1081
      - BATCH_DATA_DIR=/app/data
      - ROOT_PATH=/batch
    depends_on:
      - mlflow
    ports:
      - "1079:1079"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:1079/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  # ─────────────────────────────────────────────────────────────
  # Dashboard (Streamlit)
  # ─────────────────────────────────────────────────────────────
  dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
    container_name: dashboard
    volumes:
      - ./batch:/app/data
    environment:
      - ONLINE_API_URL=http://api:1078
      - BATCH_API_URL=http://batch:1079
      - BATCH_DATA_DIR=/app/data
      - STREAMLIT_SERVER_HEADLESS=true
      - STREAMLIT_SERVER_ENABLE_CORS=false
      - STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false
      - STREAMLIT_SERVER_PORT=1080
      - STREAMLIT_SERVER_ADDRESS=0.0.0.0
    depends_on:
      - api
      - batch
    ports:
      - "1080:1080"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:1080/_stcore/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

volumes:
  prometheus_data:
  grafana_data:
```

### Local Testing URLs

```
http://localhost:1080/  → Streamlit dashboard
http://localhost:1078/health  → Online API health
http://localhost:1079/health  → Batch API health
http://localhost:1081/  → MLflow tracking UI
http://localhost:9090/  → Prometheus metrics
http://localhost:3000/  → Grafana dashboards
```

---

## Part 5 — VPS Deployment with Monitoring

### Production Port Changes

| Service | Local Port | VPS Port | Why |
|---|---|---|---|
| Prometheus | 9090 | **1082** | Avoid nginx port conflict |
| Grafana | 3000 | **1083** | Avoid nginx port conflict |
| API | 1078 | 1078 | Unchanged |
| Batch | 1079 | 1079 | Unchanged |
| Dashboard | 1080 | 1080 | Unchanged |
| MLflow | 1081 | 1081 | Unchanged |

### Production Note: Batch Chunk Size

In production we noticed that the batch API crashed and restarted due to the huge data load. We fixed this by configuring the batch API with a chunk size of 50,000 rows.

**Add this environment variable to the batch service:**

```yaml
batch:
  environment:
    - BATCH_CHUNK_SIZE=50000  # ← Process data in chunks of 50k rows
```

### Complete VPS `docker-compose.yml`

```yaml
services:
  # ─────────────────────────────────────────────────────────────
  # MLflow Tracking Server - NO CHANGES
  # ─────────────────────────────────────────────────────────────
  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    container_name: mlflow-server
    command: >
      mlflow server
      --host 0.0.0.0
      --port 1081
      --backend-store-uri sqlite:////mlflow/mlflow.db
      --default-artifact-root mlflow-artifacts:/
      --artifacts-destination /mlruns
      --serve-artifacts
      --uvicorn-opts "--forwarded-allow-ips=*"
      --allowed-hosts "*"
    environment:
      - MLFLOW_TRACKING_URI=http://mlflow:1081
    ports:
      - "1081:1081"
    volumes:
      - ./mlflow:/mlflow
      - ./mlruns:/mlruns
    restart: unless-stopped

  # ─────────────────────────────────────────────────────────────
  # Prometheus Metrics Server
  # ─────────────────────────────────────────────────────────────
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "1082:9090"  # ← VPS PORT
    restart: unless-stopped
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.enable-lifecycle'

  # ─────────────────────────────────────────────────────────────
  # Grafana
  # ─────────────────────────────────────────────────────────────
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    volumes:
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
      # SMTP for email alerts (optional - replace with your credentials)
      - GF_SMTP_ENABLED=true
      - GF_SMTP_HOST=smtp.gmail.com:587
      - GF_SMTP_USER=your-email@gmail.com
      - GF_SMTP_PASSWORD=your-app-password
      - GF_SMTP_FROM_ADDRESS=your-email@gmail.com
      - GF_SMTP_FROM_NAME=MLOps API Dashboard
      - GF_SMTP_SKIP_VERIFY=true
    ports:
      - "1083:3000"  # ← VPS PORT
    restart: unless-stopped
    depends_on:
      - prometheus

  # ─────────────────────────────────────────────────────────────
  # Online Serving (FastAPI) - WITH METRICS
  # ─────────────────────────────────────────────────────────────
  api:
    build:
      context: .
      dockerfile: api/Dockerfile
    container_name: api-server
    volumes:
      - ./pipeline:/app/pipeline
    environment:
      - MLFLOW_TRACKING_URI=http://mlflow:1081
      - ROOT_PATH=/api
    depends_on:
      - mlflow
      - prometheus
    ports:
      - "1078:1078"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:1078/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # ─────────────────────────────────────────────────────────────
  # Offline Batch Scoring - WITH CHUNK SIZE
  # ─────────────────────────────────────────────────────────────
  batch:
    build:
      context: .
      dockerfile: batch/Dockerfile
    container_name: batch-server
    volumes:
      - ./pipeline:/app/pipeline
      - ./batch:/app/data
    environment:
      - MLFLOW_TRACKING_URI=http://mlflow:1081
      - BATCH_DATA_DIR=/app/data
      - ROOT_PATH=/batch
      - BATCH_CHUNK_SIZE=50000  # ← ADDED: Process in chunks of 50k
    depends_on:
      - mlflow
    ports:
      - "1079:1079"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:1079/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  # ─────────────────────────────────────────────────────────────
  # Dashboard (Streamlit)
  # ─────────────────────────────────────────────────────────────
  dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
    container_name: dashboard
    volumes:
      - ./batch:/app/data
    environment:
      - ONLINE_API_URL=http://api:1078
      - BATCH_API_URL=http://batch:1079
      - BATCH_DATA_DIR=/app/data
      - STREAMLIT_SERVER_HEADLESS=true
      - STREAMLIT_SERVER_ENABLE_CORS=false
      - STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false
      - STREAMLIT_SERVER_PORT=1080
      - STREAMLIT_SERVER_ADDRESS=0.0.0.0
    depends_on:
      - api
      - batch
    ports:
      - "1080:1080"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:1080/_stcore/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

volumes:
  prometheus_data:
  grafana_data:
```

### Firewall Configuration

```bash
# On VPS, allow the monitoring ports
sudo ufw allow 1082/tcp  # Prometheus
sudo ufw allow 1083/tcp  # Grafana

# For better security, restrict to specific IPs
sudo ufw allow from YOUR_IP to any port 1082
sudo ufw allow from YOUR_IP to any port 1083

# Verify firewall rules
sudo ufw status
```

### Access Monitoring via SSH Tunnel

Since Prometheus and Grafana dashboards are **not exposed to the public** for security reasons, use SSH tunneling:

```bash
# Create SSH tunnel to access Prometheus and Grafana
ssh -L 9090:localhost:1082 -L 3000:localhost:1083 user@your-vps-ip

# Then open in browser:
# http://localhost:9090  → Prometheus (maps to VPS port 1082)
# http://localhost:3000  → Grafana (maps to VPS port 1083)

# Or tunnel each individually:
ssh -L 9090:localhost:1082 user@your-vps-ip     # Prometheus only
ssh -L 3000:localhost:1083 user@your-vps-ip     # Grafana only
```

### Verify Deployment

```bash
# Check all services are running
docker compose ps

# Test each service
curl http://localhost:1078/health              # API
curl http://localhost:1079/health              # Batch API
curl http://localhost:1082/api/v1/targets      # Prometheus
curl http://localhost:1083/api/health          # Grafana
```

### Generate Drift Data

```bash
# Score recent months to populate dashboards
curl -X POST "https://your-domain.com/batch/score-range?start=2020-01&end=2024-06"

# Check results
curl "https://your-domain.com/batch/results"
```

---

## Part 6 — Production URLs

### Public Endpoints (Accessible via HTTPS)

| URL | Service | Description |
|---|---|---|
| `https://your-domain.com/` | Streamlit Dashboard | View drift reports and model performance |
| `https://your-domain.com/api/health` | Online API Health | Check API status |
| `https://your-domain.com/api/predict` | Prediction Endpoint | Make real-time predictions |
| `https://your-domain.com/api/docs` | API Documentation | FastAPI Swagger UI |
| `https://your-domain.com/batch/health` | Batch API Health | Check batch service status |
| `https://your-domain.com/batch/score` | Batch Scoring | Trigger batch scoring for a month |
| `https://your-domain.com/batch/score-range` | Batch Scoring Range | Score multiple months |
| `https://your-domain.com/batch/results` | Batch Results | View all scoring results |
| `https://your-domain.com/batch/docs` | Batch API Docs | FastAPI Swagger UI |
| `https://your-domain.com/mlflow/` | MLflow UI | View experiments and model registry |

### Private Monitoring Endpoints (SSH Tunnel Only)

| Service | VPS Port | Local Tunnel | Access URL |
|---|---|---|---|
| **Prometheus** | `1082` | `ssh -L 9090:localhost:1082 user@vps` | `http://localhost:9090` |
| **Grafana** | `1083` | `ssh -L 3000:localhost:1083 user@vps` | `http://localhost:3000` |

**Why private?** Prometheus and Grafana contain sensitive system metrics and are not exposed to the public internet for security reasons.

### Example API Calls

```bash
# Health check
curl https://your-domain.com/api/health

# Make a prediction
curl -X POST https://your-domain.com/api/predict \
  -H "Content-Type: application/json" \
  -d '{
    "tpep_pickup_datetime": "2020-04-15T14:30:00",
    "PULocationID": 161,
    "DOLocationID": 237,
    "passenger_count": 1,
    "trip_distance": 2.5,
    "VendorID": 1,
    "RatecodeID": 1,
    "payment_type": 1
  }'

# Trigger batch scoring
curl -X POST "https://your-domain.com/batch/score?year=2024&month=6"

# View batch results
curl "https://your-domain.com/batch/results"

# View drift reports
curl "https://your-domain.com/batch/drift/summary"
```

---

## Setup

### Local Development

```bash
# From 9-Monitoring-Observability/
docker compose up -d

# Check all services are running
docker compose ps

# View logs
docker compose logs -f
```

### VPS Deployment

```bash
# On VPS
cd /path/to/9-Monitoring-Observability

# Pull latest code (if using CI/CD)
git pull origin main

# Start monitoring stack
docker compose -f docker-compose.vps.yml up -d

# Verify services
docker compose ps
```

### Initial Setup for Grafana

1. Open Grafana via SSH tunnel: `http://localhost:3000`
2. Login: admin / admin
3. Change password when prompted
4. Data source should be auto-configured (Prometheus)
5. Dashboards should be auto-loaded from `monitoring/grafana/dashboards/`

---

## What You Can Do After This Module

### Monitor API Health
- See request latency trends in Grafana
- Detect error rate spikes
- Track prediction volume over time

### Detect Model Degradation
- Run batch scoring on recent data
- Compare MAE to training MAE
- Alert when MAE ratio exceeds threshold

### Detect Data Drift
- View drift scores over time
- See which features are drifting
- Generate Evidently reports

### Debug Production Issues
- "Why are predictions suddenly slower?" → Check latency dashboard
- "Why are predictions wrong?" → Check MAE and drift reports
- "Is it the model or the data?" → Compare drift vs MAE trends

---

## Reference Files

| File | What It Covers |
|---|---|
| `MONITORING_CONCEPTS.md` | Mental model: what monitoring is and why |
| `PROMETHEUS_GRAFANA.md` | Prometheus + Grafana setup and usage |
| `EVIDENTLY_DRIFT.md` | Evidently drift detection concepts |
| `METRICS_REFERENCE.md` | All metrics and alert thresholds |

---

## Troubleshooting

### Grafana Shows "No Data"

```bash
# Check Prometheus is scraping
curl http://localhost:1082/api/v1/targets

# Check API metrics endpoint
curl http://localhost:1078/metrics

# Check Prometheus config
docker compose logs prometheus
```

### Batch Scoring Fails

```bash
# Check MLflow connection
curl http://localhost:1081

# Check model is registered
mlflow models list

# Check database
sqlite3 batch/batch_results.db "SELECT * FROM batch_results;"

# Check batch logs
docker compose logs batch
```

### Drift Dashboard Shows No Data

```bash
# Run batch scoring first
curl -X POST "https://your-domain.com/batch/score?year=2024&month=6"

# Check drift reports exist
ls batch/drift_reports/

# Check dashboard is connecting to batch API
docker compose logs dashboard
```

### SSH Tunnel Connection Issues

```bash
# Test SSH connection first
ssh user@your-vps-ip

# Check ports are listening on VPS
curl http://localhost:1082/api/v1/targets   # From VPS
curl http://localhost:1083/api/health        # From VPS

# Check firewall
sudo ufw status

# Check services are running
docker compose ps
```

---

## The Numbers to Remember

| Metric | Healthy | Warning | Alert |
|---|---|---|---|
| API Latency (p95) | < 100ms | 100-500ms | > 500ms |
| Error Rate | < 0.1% | 0.1-1% | > 1% |
| MAE Ratio | < 1.2 | 1.2-1.5 | > 1.5 |
| Drift Score | < 0.3 | 0.3-0.5 | > 0.5 |
| Prediction Volume | > 500k | 300-500k | < 300k |

---

## What Comes Next

Module 9 completes the MLOps pipeline. You now have:

- ✅ Model training with experiment tracking (Module 1-2)
- ✅ Orchestrated pipeline (Module 3)
- ✅ Online and offline deployment (Module 4-5)
- ✅ Full system integration (Module 6)
- ✅ Deployment testing (Module 7)
- ✅ CI/CD and SSL (Module 8)
- ✅ Monitoring and observability (Module 9) ← you are here

The system is now **production-ready**: deployed, automated, and observable.