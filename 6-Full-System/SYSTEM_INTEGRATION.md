# System Integration — Mental Model, Concepts & Reference

---

## Part 1 — What Is System Integration? (The Mental Model)

### Start with a restaurant kitchen

A restaurant has multiple stations — prep, grill, sauce, plating, expeditor.
Each station does one job well. But the meal only reaches the customer if the stations
talk to each other in the right order.

The **expeditor** stands at the pass. They know what every station is doing,
call out orders, coordinate timing, and make sure the whole system works together.

**In software, integration is the expeditor.**

You've built:
- A training pipeline (chef who cooks the model)
- An online API (waiter who serves predictions instantly)
- A batch scorer (kitchen that preps in advance)
- A monitoring system (inspector who checks quality)
- A dashboard (menu board showing everything)

Each works alone. Integration makes them work as a restaurant.

---

### Why integration is hard

Individual components are easy to reason about:
- The API receives a request and returns a prediction
- The batch scorer downloads data and writes results
- The monitoring script reads a database and draws a chart

Integration is hard because components have **dependencies on each other**:

```
Dashboard needs:   API (for predictions) + Batch API (for results) + DB (for drift chart)
Batch API needs:   MLflow registry (for the model) + filesystem (to write results)
Online API needs:  MLflow registry (for the model) + preprocessor (from same run)
```

If any dependency is missing or misconfigured, the whole system breaks —
often silently, often with confusing error messages.

---

## Part 2 — Docker Networking (How Services Talk)

### The problem with localhost

Locally, you run three terminals:
```
Terminal 1: uvicorn main:app --port 8000      ← online API
Terminal 2: uvicorn api:app --port 8001       ← batch API
Terminal 3: streamlit run app.py --port 8501  ← dashboard
```

The dashboard calls `http://localhost:8000` and it works — all three are on the same machine.

In Docker, each container has its **own localhost**. When the dashboard container calls
`http://localhost:8000`, it's calling port 8000 on itself — not on the API container.

**Docker Compose creates a private network** where containers reach each other by name:

```
# docker-compose.yml
services:
  api:      ← service name = "api"
  batch:    ← service name = "batch"
  dashboard:
    environment:
      - ONLINE_API_URL=http://api:8000     ← container name, not localhost
      - BATCH_API_URL=http://batch:8001
```

Inside the Docker network:
- `http://api:8000` → reaches the api container ✅
- `http://localhost:8000` → reaches the dashboard container itself ❌

Outside Docker (from your browser):
- `http://localhost:8000` → reaches the api container via port mapping ✅
- `http://api:8000` → nothing (api is a Docker-internal name) ❌

This is why the dashboard uses **environment variables** for URLs:

```python
# dashboard/app.py
ONLINE_API = os.getenv("ONLINE_API_URL", "http://localhost:8000")
BATCH_API  = os.getenv("BATCH_API_URL",  "http://localhost:8001")
```

Locally: env vars not set → defaults to `localhost` → works.
In Docker: env vars set to service names → works.
Same code. Different config. No rebuild needed.

---

### Port mapping — inside vs outside

```yaml
services:
  api:
    ports:
      - "8000:8000"   # host_port:container_port
```

```
Outside Docker (your browser):   http://localhost:8000  → api container port 8000
Inside Docker (other containers): http://api:8000       → api container port 8000
```

Both reach the same container, but via different paths. The port mapping (`8000:8000`)
only matters for external access. Internal service-to-service communication
uses the service name directly.

---

## Part 3 — Shared State (How Services Share Data)

### The MLflow registry — shared read

All three services read from the same MLflow registry (the SQLite DB):

```
Online API:   loads @champion model at startup
Batch API:    loads @champion model for each scoring job
Dashboard:    — (doesn't load the model, reads batch_results.db instead)
```

In Module 6, the registry is accessed via **bind mount**:

```yaml
services:
  api:
    volumes:
      - ./pipeline:/app/pipeline  ← host path → container path
    environment:
      - MLFLOW_ARTIFACTS_ROOT=/app/pipeline        ← remap absolute paths
```

Both `api` and `batch` mount the same host directory. They read the same model.

**Why bind mount and not a named volume?**

The MLflow registry was written by the pipeline running locally. Its artifact paths
contain host absolute paths (e.g., `/home/silva/.../pipeline/mlruns/...`).
A named volume would be separate storage — the containers wouldn't see those files.
A bind mount maps the actual local directory into the container — they see the same files.

See `4-Deploy-Online/docs/DOCKER_DEBUGGING.md (in the main repo)` for the full path-remapping story.

---

### Batch results — shared write/read

The batch scorer writes results. The dashboard reads them.
They share state via a bind mount on the **batch data directory**:

```yaml
services:
  batch:
    volumes:
      - ./batch:/app/data   ← batch writes here
  dashboard:
    volumes:
      - ./batch:/app/data   ← dashboard reads here
```

Same host directory. Both containers see the same files.

```
Batch API writes:   /app/data/batch_results.db
                    /app/data/predictions/2020_04.parquet

Dashboard reads:    /app/data/batch_results.db  ← drift chart data
                    /app/data/predictions/*.parquet ← file inventory
```

This is straightforward here because one writes and one reads. If both wrote,
you'd need a coordination mechanism (a database, a lock, a message queue).
For this system: batch is the writer, dashboard is the reader. No conflict.

---

## Part 4 — Startup Order and Health Checks

### Why startup order matters

The dashboard needs the API and batch API to be running before it can show status.
If the dashboard starts before them, it shows "Offline" — which is correct behavior,
but less clean than starting in the right order.

Docker Compose `depends_on` controls startup order:

```yaml
dashboard:
  depends_on:
    - api
    - batch
```

This means Docker starts `api` and `batch` first, then `dashboard`.
But "started" ≠ "ready". Docker starts the container process — it doesn't
wait for the app inside to finish loading.

**`service_healthy`** waits for the healthcheck to pass:

```yaml
dashboard:
  depends_on:
    api:
      condition: service_healthy   ← wait until api returns 200 on /health
    batch:
      condition: service_healthy
```

This is more robust — dashboard only starts after API and batch are genuinely ready.
We removed this in Module 6 because the API takes ~60s to load (MLflow migrations).
The dashboard is designed to handle offline services gracefully.

---

### Health checks — how Docker knows a service is ready

```yaml
api:
  healthcheck:
    test: ["CMD", "python", "-c",
           "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
    interval: 30s      # check every 30s
    timeout: 10s       # fail if check takes > 10s
    retries: 3         # mark unhealthy after 3 consecutive failures
    start_period: 60s  # don't check for the first 60s (model loading time)
```

The `start_period` is critical for ML services — loading a model from disk takes time.
Without it, Docker marks the container unhealthy before it's finished starting.

---

## Part 5 — Configuration Management

### Environment variables — the right way to configure services

Every configurable value in this system is set via environment variable:

| Service | Env var | Default | What it does |
|---------|---------|---------|--------------|
| api | `MLFLOW_TRACKING_URI` | local SQLite path | where to find the registry |
| api | `MLFLOW_ARTIFACTS_ROOT` | none | remap host paths to container paths |
| api | `MODEL_NAME` | `trip_duration_model` | which registered model to serve |
| api | `MODEL_ALIAS` | `champion` | which alias to load |
| batch | `MLFLOW_TRACKING_URI` | local SQLite path | same registry as api |
| batch | `BATCH_DATA_DIR` | local batch/ dir | where to write results |
| dashboard | `ONLINE_API_URL` | `http://localhost:8000` | which api to call |
| dashboard | `BATCH_API_URL` | `http://localhost:8001` | which batch api to call |
| dashboard | `BATCH_DATA_DIR` | local batch/ dir | where to read results from |

**The pattern:**
```python
VALUE = os.getenv("MY_ENV_VAR", "local_default")
```

Local: env var not set → uses default → works.
Docker: env var set in docker-compose.yml → overrides default → works.
Production: env var set in cloud config → works everywhere.

Same code. Zero code changes between environments. This is the 12-Factor App principle.

---

## Part 6 — Connecting Concepts to Code

### The full startup sequence

```
docker compose up

1. Docker creates a private network: 6-full-system_default

2. Starts api container:
   - Mounts ./pipeline → /app/pipeline
   - Sets MLFLOW_ARTIFACTS_ROOT=/app/pipeline
   - Runs: uvicorn main:app --host 0.0.0.0 --port 8000
   - lifespan: loads @champion model + preprocessor from MLflow
   - Healthcheck starts after 60s

3. Starts batch container:
   - Mounts ./pipeline → /app/pipeline
   - Mounts ./batch → /app/data
   - Runs: uvicorn api:app --host 0.0.0.0 --port 8001
   - lifespan: initializes batch_results.db
   - Healthcheck starts after 30s

4. Starts dashboard container:
   - Mounts ./batch → /app/data
   - Sets ONLINE_API_URL=http://api:8000
   - Sets BATCH_API_URL=http://batch:8001
   - Runs: streamlit run app.py --port 8501

5. All three running, connected via Docker network
```

### A prediction request through the full system

```
Browser → http://localhost:8000/predict
  ↓
Docker port mapping → api container port 8000
  ↓
FastAPI predict() function
  ↓
s.preprocessor.transform(df)   ← loaded at startup from MLflow
s.model.predict(X)             ← XGBoost @champion
  ↓
{"predicted_duration_minutes": 18.74, "model_version": "v12"}
  ↓
Browser ← response in ~5ms
```

### A batch scoring request through the full system

```
Dashboard → POST http://batch:8001/score?year=2021&month=6
  ↓
FastAPI trigger_score() → background_tasks.add_task(_run_score_job, 2021, 6)
  ↓ returns immediately
{"status": "started", "message": "Poll /results/2021/6 when ready"}

Background: _run_score_job running
  ↓
core.load_champion() → loads from /app/pipeline (bind mount = same as api's registry)
  ↓
core.score_month(2021, 6) → downloads TLC parquet, scores all trips
  ↓
/app/data/predictions/2021_06.parquet   ← written (bind mount = host filesystem)
/app/data/batch_results.db              ← updated (bind mount = host filesystem)

Dashboard → GET http://batch:8001/results/2021/6
  ↓
{"mae": 2.95, "mae_ratio": 0.96, "alert": 0}
```

---

## Quick Reference

```bash
# Start full system
cd 6-Full-System
docker compose up -d

# Check all services
curl http://localhost:8000/health   # api
curl http://localhost:8001/health   # batch
curl http://localhost:8501          # dashboard (HTML)

# Check logs
docker compose logs api
docker compose logs batch
docker compose logs dashboard

# Restart one service (e.g. after retrain)
docker compose restart api

# Stop everything
docker compose down

# Rebuild after code changes
docker compose build api && docker compose restart api
```

### Service-to-service URLs (inside Docker)

| From | To | URL |
|------|----|-----|
| dashboard | api | `http://api:8000` |
| dashboard | batch | `http://batch:8001` |
| batch | mlflow | `sqlite:////app/pipeline/mlflow_trip_duration.db` |
| api | mlflow | `sqlite:////app/pipeline/mlflow_trip_duration.db` |

### External URLs (from your browser)

| Service | URL |
|---------|-----|
| Online API | `http://localhost:8000/docs` |
| Batch API | `http://localhost:8001/docs` |
| Dashboard | `http://localhost:8501` |
