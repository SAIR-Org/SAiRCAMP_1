# Prometheus + Grafana — Why and How

---

## Part 1 — The Problem with No Monitoring

### What we couldn't see in Modules 1-8

Before Module 9, we had a deployed system with:
- A working API serving predictions
- Batch scoring running monthly
- CI/CD deploying updates

But we couldn't answer basic questions:
- Is the API fast enough? (latency)
- Are predictions failing? (error rate)
- How many predictions are we serving? (traffic)
- Is the system overloaded? (saturation)

**The root cause:** No metrics collection or visualization.

We had logs, but logs are:
- Hard to aggregate
- Hard to visualize trends
- Not designed for real-time monitoring

We needed a system that:
1. Collects metrics automatically
2. Stores them over time
3. Visualizes trends
4. Alerts on problems

---

## Part 2 — The Solution: Prometheus + Grafana

### What each tool does

**Prometheus** = Metrics collection + storage
- Scrapes `/metrics` endpoints every 10 seconds
- Stores time-series data (timestamp + value)
- Queries data with PromQL

**Grafana** = Visualization + dashboards
- Queries Prometheus
- Displays graphs and panels
- Auto-loads dashboards from config

```
API → exposes /metrics → Prometheus scrapes → Grafana visualizes
```

### Why Prometheus pulls (not pushes)

| Pull model (Prometheus) | Push model (statsd, Datadog) |
|---|---|
| Services don't need to know where to send | Services must know collector address |
| Prometheus controls scraping schedule | Services control when to send |
| Easier to discover new services | Services must register themselves |
| Health checks built in | Health checks require separate system |

**In this project:** Prometheus pulls from `api:1078/metrics` every 10 seconds.

---

## Part 3 — What We Monitor

### The metrics from `api/metrics.py`

```python
# Counters - only increase
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

PREDICTION_COUNT = Counter(
    'predictions_total',
    'Total predictions made'
)

# Histograms - measure distribution
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
)

PREDICTION_LATENCY = Histogram(
    'prediction_duration_seconds',
    'Time to compute a single prediction',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1]
)

# Gauges - go up and down
PREDICTION_VALUE = Gauge(
    'prediction_value_minutes',
    'Last predicted trip duration'
)

ACTIVE_REQUESTS = Gauge(
    'active_requests',
    'Number of requests currently being processed'
)

# Info - static metadata
MODEL_INFO = Info(
    'model_info',
    'Information about the currently loaded model'
)
```

### What each metric type means

| Type | Behavior | Use case |
|---|---|---|
| **Counter** | Only increases | Request count, prediction count |
| **Histogram** | Measures distribution | Latency, response sizes |
| **Gauge** | Goes up and down | Active requests, current value |
| **Info** | Static metadata | Model version, alias |

### The middleware that collects everything

```python
# api/main.py - runs for EVERY request
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
```

This runs automatically. No manual logging needed.

---

## Part 4 — How It's Configured

### Prometheus config

From `monitoring/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'api'
    static_configs:
      - targets: ['api:1078']      # Docker service name
    metrics_path: '/metrics'
    scrape_interval: 10s           # Override for this job
```

**What this means:**
- `job_name` → Label added to every metric: `{job="api"}`
- `targets` → Where to find the service: `api:1078`
- `scrape_interval` → How often: every 10 seconds

**Inside Docker network:**
- Prometheus can reach `api:1078` (service name)
- From host, you reach `localhost:1082` (mapped port)

### Grafana datasource

From `monitoring/grafana/datasources/prometheus.yml`:

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090   # Docker service name
    isDefault: true
```

### Grafana dashboards

From `monitoring/grafana/dashboards/dashboards.yml`:

```yaml
apiVersion: 1
providers:
  - name: 'Default'
    folder: 'MLOps'
    type: file
    options:
      path: /etc/grafana/provisioning/dashboards
```

Grafana auto-loads any JSON dashboard from this directory.

---

## Part 5 — The Three Dashboards

### 1. Operational Dashboard (`dashboard_v1_operational.json`)

**What it shows:**
- Request rate (requests/second)
- Latency percentiles (p50, p95, p99)
- Error rate (5xx responses / total)
- Active requests

**When to check:** Daily

**Key queries:**
```promql
# Request rate
rate(http_requests_total[5m])

# p95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Error rate
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
```

---

### 2. Business Dashboard (`dashboard_v2_business.json`)

**What it shows:**
- Total predictions (cumulative)
- Prediction rate (per hour)
- Prediction distribution
- Model version in production

**When to check:** Weekly

**Key queries:**
```promql
# Total predictions
predictions_total

# Prediction rate
rate(predictions_total[1h])

# Average prediction value
avg(prediction_value_minutes)
```

---

### 3. Model Performance Dashboard (`dashboard_v3_model_performance.json`)

**What it shows:**
- MAE over time
- MAE ratio (vs training)
- Drift score over time
- Drift detection status

**When to check:** Monthly

**Note:** This uses batch scoring data, not Prometheus directly.
Batch results are stored in SQLite and MLflow.

---

## Part 6 — Accessing Prometheus and Grafana

### Local development

```bash
# Start services
docker compose up -d

# Access
http://localhost:9090  → Prometheus
http://localhost:3000  → Grafana
```

### VPS deployment

| Service | Local Port | VPS Port | Why |
|---|---|---|---|
| Prometheus | 9090 | **1082** | Avoid nginx conflict |
| Grafana | 3000 | **1083** | Avoid nginx conflict |

**Access via SSH tunnel (recommended):**

```bash
# Tunnel both
ssh -L 9090:localhost:1082 -L 3000:localhost:1083 user@vps-ip

# Open in browser
http://localhost:9090  → Prometheus
http://localhost:3000  → Grafana
```

**Why SSH tunnel?** Prometheus and Grafana contain sensitive system metrics.
Not exposing them to the public internet is a security best practice.

---

## Part 7 — What Changed in Module 9

### docker-compose.yml

Added two new services:

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "1082:9090"

  grafana:
    image: grafana/grafana:latest
    volumes:
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    ports:
      - "1083:3000"
    depends_on:
      - prometheus
```

### api/Dockerfile

Added `prometheus_client` to requirements.

### api/main.py

Added:
- Middleware for automatic metrics collection
- `/metrics` endpoint for Prometheus scraping
- Model info on startup

### api/metrics.py

New file defining all metrics.



### Grafana defaults

```
Username: admin
Password: admin
Data source: Prometheus (auto-configured)
Dashboards: Auto-loaded from monitoring/grafana/dashboards/
```

