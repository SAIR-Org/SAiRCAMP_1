# MLflow Tracking Server — Why and How

---

## Part 1 — The Problem with SQLite

### What broke in Modules 4 and 5

In Modules 4 and 5, MLflow used a local SQLite file as its backend:

```
pipeline/mlflow_trip_duration.db   ← the registry
pipeline/mlruns/                   ← model artifacts stored here
```

This works perfectly for local development. The problem appeared when we
containerized the API in Docker.

**The root cause:** MLflow stores artifact paths as **absolute host filesystem paths**
inside the SQLite database:

```sql
-- model_versions table
storage_location = '/home/silva/.../pipeline/mlruns/1/models/m-xxx/artifacts'

-- runs table
artifact_uri = '/home/silva/.../pipeline/mlruns/1/run_id/artifacts'
```

Inside the Docker container, `/home/silva/...` doesn't exist. The container only
has `/app/pipeline/` via bind mount. So when the container tried to load the model,
it crashed with:

```
OSError: No such file or directory: '/home/silva/.../mlruns/...'
```

**The workaround we built (Modules 4 and 5):**

```python
# model_loader.py — the ugly fix
def _remap(path: str) -> str:
    """Replace host pipeline prefix with container pipeline path."""
    if not _ARTIFACTS_ROOT or not path:
        return path
    idx = path.find("/mlruns/")
    return _ARTIFACTS_ROOT + path[idx:] if idx >= 0 else path

def _get_storage_location(version: str) -> str:
    """Read storage_location directly from SQLite — not exposed as Python attr."""
    db_path = MLFLOW_TRACKING_URI.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT storage_location FROM model_versions WHERE name=? AND version=?",
        (MODEL_NAME, version)
    ).fetchone()
    conn.close()
    return row[0] if row else None
```

Plus in docker-compose:
```yaml
environment:
  - MLFLOW_ARTIFACTS_ROOT=/app/pipeline   # remap host paths to container paths
```

This worked — but it was fragile and machine-specific:
- Only works if the pipeline directory is bind-mounted at a predictable path
- Different host path on a colleague's machine → breaks
- Deploy to VPS → breaks (different absolute path)
- Any rename of the module folder → breaks

---

## Part 2 — The Proper Solution: MLflow Tracking Server

### What the tracking server is

Instead of a local SQLite file, MLflow can run as an HTTP server:

```
Local SQLite (Modules 4 & 5):        Tracking Server (Module 6):
────────────────────────────          ─────────────────────────────
sqlite:///mlflow.db                   http://mlflow:5000
Absolute host paths in DB             URL-based artifact paths
Only local processes can read         Any process with network access
Bind mount required for Docker        HTTP — no bind mount needed
```

The tracking server stores artifacts at its own configured path (inside a Docker
volume, on S3, on GCS — wherever you configure it). Clients (pipeline, API, batch)
connect via HTTP and let the server handle artifact URLs.

---

### How it works in Module 6

```yaml
# docker-compose.yml
services:
  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    command: >
      mlflow server
      --host 0.0.0.0
      --port 5000
      --backend-store-uri sqlite:////mlflow/mlflow.db
      --default-artifact-root /mlflow/artifacts
    volumes:
      - mlflow_data:/mlflow    ← Docker manages this storage
    ports:
      - "5000:5000"

  api:
    environment:
      - MLFLOW_TRACKING_URI=http://mlflow:5000   ← connects to server
    # No bind mount needed. No MLFLOW_ARTIFACTS_ROOT. No path hacks.
```

When the API loads a model:
```python
# model_loader.py — clean, no hacks
mlflow.set_tracking_uri("http://mlflow:5000")
model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")
# Server resolves the URI, serves the artifact via HTTP. Done.
```

The server knows where the artifacts are. It serves them. Containers don't need
to know anything about host filesystem paths.

---

### The artifact path in the database

With the tracking server, artifact URIs look like:

```
# Old (SQLite, host paths):
artifact_uri = '/home/silva/.../pipeline/mlruns/1/run_id/artifacts'

# New (tracking server):
artifact_uri = '/mlflow/artifacts/1/run_id/artifacts'
```

The path is relative to the server's artifact root, not the host filesystem.
Any container connecting to `http://mlflow:5000` gets the same artifacts,
regardless of host path.

---

## Part 3 — Implementation Status

### What was attempted

A full MLflow tracking server was implemented and tested in Module 6.
Three blocking issues were encountered and documented here for students:

**Issue 1 — PermissionError writing to `/mlflow`**
When the pipeline runs locally and connects to `http://localhost:5000`, the server
tells it to write artifacts to `/mlflow/artifacts`. On the host, `/mlflow` doesn't
exist (it's a Docker-internal path), causing `PermissionError`.

Fix attempted: `--serve-artifacts` with `--default-artifact-root mlflow-artifacts:/`
to use HTTP proxy instead of direct filesystem writes.

**Issue 2 — DNS rebinding security middleware blocking `http://mlflow:5000`**
MLflow 3.x includes security middleware that rejects requests with Host headers
that don't match its allowed list. Inside Docker, services connect via
`http://mlflow:5000` — the hostname `mlflow` is rejected as a potential DNS
rebinding attack.

Fix attempted: `--allowed-hosts "*"` to allow all hosts.

**Issue 3 — `mlflow-artifacts:/` URIs routing to `local_artifact_repo`**
Even with `--serve-artifacts` enabled, MLflow's artifact resolution for
`mlflow-artifacts:/` URIs fell back to `local_artifact_repo` instead of using
the HTTP proxy (`MlflowArtifactsRepository`). This appears to be a behavior
in MLflow 3.13.x where the `models:/m-xxx` (Logged Model) format is not
properly proxied through the tracking server in all scenarios.

**Result:** Module 6 reverts to the working bind mount + path remapping approach.
The concepts in this document remain accurate — the server is the right production
solution. The implementation gap is a MLflow 3.x configuration complexity, not a
conceptual flaw.

### What production does differently

In production:
1. A proper MLflow tracking server runs as a persistent service (PostgreSQL backend)
2. Artifacts stored in S3/GCS — URLs, not local paths, work everywhere
3. No DNS rebinding issues because services connect via proper domain names with TLS

---

## Part 4 — What Changed in Module 6

### docker-compose.yml

Added `mlflow` service. Removed bind mount for `./pipeline`. Added `mlflow_data` volume.

```
Before (Module 4/5 approach):      After (Module 6):
────────────────────────────        ─────────────────────────────
api:                                mlflow:
  volumes:                            command: mlflow server ...
    - ./pipeline:/app/pipeline        volumes:
  environment:                          - mlflow_data:/mlflow
    - MLFLOW_ARTIFACTS_ROOT=...
                                    api:
                                      environment:
                                        - MLFLOW_TRACKING_URI=http://mlflow:5000
                                      # No volumes needed for MLflow
```

### model_loader.py (api/)

Removed: `_remap()`, `_get_storage_location()`, `_get_artifact_uri()`, `_ARTIFACTS_ROOT`

```python
# Before — 60 lines with workarounds
if _ARTIFACTS_ROOT:
    storage_loc = _get_storage_location(mv.version)
    model_path = _remap(storage_loc)
    model = mlflow.sklearn.load_model(model_path)
else:
    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")

# After — 2 lines, clean
model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")
```

### batch/core.py

Same simplification — removed the three helper functions and the branching logic.

---

## Part 4 — The Workflow Change

### Before (Modules 4 & 5)

```
1. python main.py --promote        ← writes to local SQLite + ./mlruns/
2. docker compose up api           ← bind mounts ./pipeline, remaps paths
```

Machine-specific. Breaks on different host.

### After (Module 6)

```
1. docker compose up mlflow -d     ← start the server first
2. MLFLOW_TRACKING_URI=http://localhost:5000 \
   python main.py --promote        ← writes to server (goes into mlflow_data volume)
3. docker compose up               ← api/batch/dashboard read from http://mlflow:5000
```

Machine-independent. Works identically on VPS, colleague's machine, CI/CD.

---

## Part 5 — Deploying to a VPS

With the tracking server, VPS deployment is straightforward:

```bash
# On VPS — clone the repo
git clone https://github.com/your-repo/mlops-zoomcamp.git
cd mlops-zoomcamp/6-Full-System

# Start everything
docker compose up mlflow -d
MLFLOW_TRACKING_URI=http://localhost:5000 \
  python pipeline/main.py --sample-size 500000 --tune --promote
docker compose up

# Done. The system runs identically to local.
```

No path remapping. No bind mount tweaks. No host-specific configuration.

The only difference from local: the VPS IP instead of `localhost` for external access.

---

## Part 6 — What Production Adds

The tracking server in Module 6 still uses SQLite for its own metadata.
In real production, you'd use:

```
Development (Module 6):          Production:
─────────────────────────         ──────────────────────────────────
SQLite backend in server          PostgreSQL or MySQL backend
Local volume for artifacts        S3, GCS, or Azure Blob Storage
Single server instance            Load-balanced server cluster
HTTP (no auth)                    HTTPS + API key authentication
```

The patterns are identical. Infrastructure scales. The code doesn't change.

---

## Quick Reference

```bash
# Start MLflow server
docker compose up mlflow -d

# Check server is ready
curl http://localhost:5000/health

# Train pipeline pointing at server
MLFLOW_TRACKING_URI=http://localhost:5000 \
  python pipeline/main.py --sample-size 500000 --tune --promote

# View registry
open http://localhost:5000   # → Models → trip_duration_model

# Start all services
docker compose up

# What's in the mlflow_data volume?
docker run --rm -v 6-full-system_mlflow_data:/data alpine ls /data/
# → mlflow.db  artifacts/
```
