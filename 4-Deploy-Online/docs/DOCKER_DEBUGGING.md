# Docker Debugging Log — Three Problems We Hit and How We Fixed Them

This document records the exact errors encountered when containerizing the
pipeline and API, why they happened, and how each was resolved.
These are real production problems — not manufactured examples.

---

## Problem 1 — Prefect Won't Start in Docker

### The error

```
RuntimeError: Timed out while attempting to connect to ephemeral Prefect API server.

WARNING: Unable to write to memo_store.toml at /root/.prefect/memo_store.toml:
FileNotFoundError(2, 'No such file or directory')
```

### What we tried first

Set `PREFECT_HOME=/tmp/prefect` in `docker-compose.yml` environment section:
```yaml
environment:
  - PREFECT_HOME=/tmp/prefect
```

Didn't work. The warning still showed `/root/.prefect/memo_store.toml`.

Then set it in the Dockerfile as `ENV`:
```dockerfile
ENV PREFECT_HOME=/tmp/prefect
ENV PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=120
RUN mkdir -p /tmp/prefect
```

Still timed out at ~20 seconds.

### Why it happened

Prefect's ephemeral server starts as a **subprocess** — a child process spawned
by the main Python process. In Docker, this subprocess does not inherit the
parent's environment variables reliably. So:

- `PREFECT_HOME` was set in the parent but not seen by the server subprocess
- The server kept trying to write to `/root/.prefect/` (the hardcoded default)
- The `PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS` timeout was also ignored
  by the subprocess

The deeper issue: Prefect's ephemeral server starts a full HTTP API server
(SQLite-backed) as a side process. In Docker, this architecture doesn't work
reliably without a dedicated persistent Prefect server service.

### The fix — architectural decision

**Don't containerize the pipeline.** The pipeline runs locally.

This is actually the correct production pattern:
- Training is a **development-time activity** — developers run it locally,
  watch the Prefect UI, iterate
- Serving is a **deployment artifact** — containerized for reproducibility

Prefect's value (UI visibility, retry tracking, task state) is lost inside a
Docker container anyway — there's no way to see the UI unless you also run a
dedicated Prefect server container.

The `pipeline/Dockerfile` was kept for documentation and future CI use (where
you'd add a Prefect server service), but removed from `docker-compose.yml`.

### Lesson

> Orchestration tools like Prefect are designed for development observability,
> not for containerization. If you need Prefect in Docker, run a dedicated
> Prefect server as a separate service and point the pipeline at it via
> `PREFECT_API_URL=http://prefect-server:4200/api`.

---

## Problem 2 — MLflow Version Mismatch Corrupted the Database

### The error

```
mlflow.exceptions.MlflowException: _verify_schema raised an exception
```

Locally, after the Docker container had run:
```
mlflow.store.db.utils._verify_schema: schema version mismatch
```

### What happened

Local environment had **MLflow 3.9.0**.
Docker image built with **MLflow 3.13.0** (resolved from `mlflow>=3.0.0`).

When the Docker container started, MLflow 3.13.0 opened the local SQLite DB
(via bind mount) and ran **Alembic migrations** — upgrading the DB schema
to version 3.13.0.

After the container stopped, the local MLflow 3.9.0 could no longer read
the upgraded schema. The DB was now permanently in a newer format.

### The fix

Pin the same version in both places:

```
# 4-Deploy-Online/pipeline/requirements.txt
mlflow==3.13.0

# 4-Deploy-Online/api/requirements.txt
mlflow==3.13.0
```

Upgrade locally to match:
```bash
uv pip install "mlflow==3.13.0"
```

### How to check parity

```bash
# Local
python -c "import mlflow; print(mlflow.__version__)"

# Docker
docker run --rm 4-deploy-online-api python -c "import mlflow; print(mlflow.__version__)"
```

Both must show the same version.

### Lesson

> Never use `>=` version constraints for packages that write to shared state
> (databases, registries). Two components sharing a SQLite file must use
> the **exact same version** of the library that owns the schema.
> `mlflow>=3.0.0` is fine for isolated environments. It's a bug when two
> processes with different versions share the same DB file.

---

## Problem 3 — Absolute Artifact Paths Break Inside Docker

### The error

```
mlflow.exceptions.MlflowException: No such artifact: ''

OSError: No such file or directory:
'/home/silva/SILVA.AI/Projects/MLOps/mlops-zoomcamp/4-Deploy-Online/pipeline/
mlruns/1/models/m-6b2d23f06ec34e42b2cc813dd8868a8a/artifacts/.'
```

### Why it happened

MLflow stores artifact paths as **absolute host filesystem paths** inside the
SQLite database:

```sql
-- model_versions table
storage_location = '/home/silva/.../pipeline/mlruns/1/models/m-xxx/artifacts'

-- runs table
artifact_uri = '/home/silva/.../pipeline/mlruns/1/run_id/artifacts'
```

These paths exist on the host machine. Inside the Docker container, the
bind mount maps `./pipeline` to `/app/pipeline`. So the correct container
path is `/app/pipeline/mlruns/...` — but MLflow reads the DB and tries
to open `/home/silva/.../mlruns/...`, which doesn't exist.

### What we tried first

Attempt 1 — load the model by `mv.source`:
```python
model = mlflow.sklearn.load_model(mv.source)  # mv.source = "models:/m-xxx"
```

Failed — `mv.source` in MLflow 3.x is an internal `models:/m-xxx` URI,
not a filesystem path. MLflow tried to resolve it and failed with
`No such artifact: ''`.

Attempt 2 — use `mv.storage_location`:
```python
model_path = _remap(mv.storage_location)
```

Failed — `ModelVersion` in MLflow 3.x does not expose `storage_location`
as a Python attribute (it's a DB column, not a model field).

### The fix

Read `storage_location` directly from SQLite and remap it:

```python
def _get_storage_location(version: str) -> str:
    """Read storage_location directly from SQLite (not exposed as Python attr)."""
    db_path = MLFLOW_TRACKING_URI.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT storage_location FROM model_versions WHERE name=? AND version=?",
        (MODEL_NAME, version)
    ).fetchone()
    conn.close()
    return row[0] if row else None

def _remap(path: str) -> str:
    """Replace host pipeline prefix with container pipeline path."""
    if not MLFLOW_ARTIFACTS_ROOT or not path:
        return path
    idx = path.find("/mlruns/")
    return MLFLOW_ARTIFACTS_ROOT + path[idx:] if idx >= 0 else path
```

In `docker-compose.yml`:
```yaml
environment:
  - MLFLOW_ARTIFACTS_ROOT=/app/pipeline
```

At load time:
```python
if _ARTIFACTS_ROOT:
    storage_loc = _get_storage_location(mv.version)
    model_path = _remap(storage_loc)
    # /home/silva/.../mlruns/... → /app/pipeline/mlruns/...
    model = mlflow.sklearn.load_model(model_path)
else:
    # Local — use MLflow registry URI directly
    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")
```

The same remapping applies to the preprocessor artifact:
```python
artifact_uri = _get_artifact_uri(mv.run_id)
preprocessor_path = Path(_remap(artifact_uri)) / "preprocessor" / "preprocessor.pkl"
```

### The production solution

This workaround exists because SQLite as an MLflow backend stores local paths.
In production, use a **proper MLflow tracking server** with object storage:

```
Local development:
  MLFLOW_TRACKING_URI=sqlite:///mlflow.db
  Artifacts stored at: /local/path/mlruns/...   ← host-absolute paths

Production:
  MLFLOW_TRACKING_URI=http://mlflow-server:5000
  Artifacts stored at: s3://my-bucket/mlruns/... ← URL, works everywhere
```

With S3/GCS artifact storage, the paths in the DB are URLs — they work
identically from any machine, any container, any cloud region.

### Lesson

> SQLite + local artifacts is a single-developer setup. The moment you add
> a second process (Docker container, CI runner, colleague's machine) that
> reads the same MLflow DB, you hit the absolute path problem.
> The fix is a tracking server with cloud artifact storage — but for
> local development and course work, the `_remap()` workaround is sufficient.

---

## Summary

| Problem | Root cause | Fix | Production solution |
|---------|-----------|-----|-------------------|
| Prefect timeout | Subprocess doesn't inherit Docker ENV | Run pipeline locally | Add Prefect server service to docker-compose |
| MLflow schema mismatch | `>=` constraint resolved differently locally vs Docker | Pin exact version: `mlflow==3.13.0` | Always pin exact versions in shared-state systems |
| Absolute artifact paths | SQLite stores host filesystem paths | `_remap()` function + `MLFLOW_ARTIFACTS_ROOT` env var | Use MLflow tracking server + S3/GCS artifacts |

---

## The Broader Lesson

All three problems share a common theme: **coupling between local development
and containerized deployment**.

When you use local files (SQLite, local filesystem) as shared infrastructure
between a host process (pipeline) and a container (API), you're fighting
against Docker's isolation model. Docker is designed for self-contained units.

The proper production architecture separates concerns:
```
Local:      train → push model to remote MLflow server
Container:  load model from remote MLflow server → serve predictions
```

No shared local files. No path remapping. No version parity issues.
For a course running on a single machine, the workarounds above are
sufficient and teach the right lessons by making the problems visible.
