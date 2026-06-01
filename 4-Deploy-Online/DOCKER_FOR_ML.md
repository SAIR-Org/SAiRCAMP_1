# Docker for ML — Mental Model, Concepts & Reference

---

## Part 1 — Why Docker? (The Mental Model)

### The "works on my machine" problem

Every ML engineer has lived this:

```
Data scientist: "The model works perfectly, here's the code."
Engineer:       "It crashes on the server."
Data scientist: "But it works on my laptop!"

Laptop:  Python 3.10, scikit-learn 1.2.0, numpy 1.24, CUDA 11.8
Server:  Python 3.8,  scikit-learn 1.0.2, numpy 1.21, no CUDA
```

The model isn't broken. The environment is different. The code assumes a specific
Python version, specific library versions, specific system libraries. When the
environment changes, the behavior changes — or the code crashes entirely.

**Docker solves this by packaging the environment with the code.**

Instead of shipping code and hoping the environment matches, you ship a container:
a self-contained unit that includes the OS libraries, Python version, all packages,
and your code. It runs identically everywhere Docker is installed — your laptop,
a colleague's machine, a cloud server.

---

### What a container actually is

A common mental model mistake: thinking containers are mini virtual machines.
They're not. They're isolated processes.

```
Virtual Machine                    Container
──────────────                     ──────────────
Full OS (2-4 GB)                   Your app + dependencies (~500 MB)
Boots in minutes                   Starts in seconds
Strong isolation (separate kernel) Process-level isolation (shared kernel)
High overhead                      Low overhead
```

A container is a process that:
- Has its own filesystem (isolated from the host)
- Has its own network namespace
- Has its own process namespace
- But shares the host OS kernel

When you run a Python container, you're running a Python process in an isolated
environment — not booting a new operating system.

---

### Images vs containers

This distinction is important:

**Image:** A read-only template. A snapshot of an environment at a point in time.
Built once, used many times. Stored in a registry (Docker Hub, etc.).

```dockerfile
# This is a Dockerfile — instructions for building an image
FROM python:3.12-slim        # start from official Python 3.12 image
RUN pip install fastapi      # add FastAPI
COPY api/ ./api/             # add your code
CMD ["uvicorn", "main:app"]  # set the default command
```

Running `docker build` creates an image from these instructions.

**Container:** A running instance of an image. You can run many containers from the
same image simultaneously. Containers are ephemeral — they start, do work, stop.
Any data written inside a container disappears when the container stops (unless you use volumes).

```
Image (blueprint)    →   Container (instance running)
                     →   Container (another instance)
                     →   Container (yet another instance)
```

---

### The ML-specific challenge: shared state

A standard web app container is stateless — each request is independent. The app
reads from a database and returns a response. Simple.

An ML system has a problem: the **model artifacts** need to be shared between
the training container (which writes them) and the serving container (which reads them).

```
Pipeline container     API container
──────────────         ──────────────
Trains model           Loads model
Registers in MLflow    Reads from MLflow registry
Writes artifacts →  ←  Reads artifacts
```

If each container has its own isolated filesystem, they can't share data.
This is where **volumes** come in.

---

### Volumes — the solution to shared state

A volume is storage that exists outside any container. It's managed by Docker
and can be mounted into multiple containers simultaneously.

```
Docker Volume: mlflow_store
       ↓                  ↓
Pipeline container     API container
/mlflow/ ←── volume ──→ /mlflow/
```

When the pipeline writes `mlflow_trip_duration.db` to `/mlflow/`, that file
appears in the API container's `/mlflow/` directory immediately. They share the
same underlying storage.

```yaml
# docker-compose.yml
volumes:
  mlflow_store:              # Docker manages this storage

services:
  pipeline:
    volumes:
      - mlflow_store:/mlflow  # mount at /mlflow inside the container

  api:
    volumes:
      - mlflow_store:/mlflow  # same volume, same path
```

This is the pattern used in this project. The pipeline writes the MLflow database
and artifacts. The API reads them. Both see the same files via the shared volume.

---

## Part 2 — Docker Concepts

### The Dockerfile — layer by layer

```dockerfile
FROM python:3.12-slim
```

Every image starts from a base. `python:3.12-slim` is an official image from Docker Hub —
Debian Linux with Python 3.12 pre-installed, stripped of unnecessary packages.
`slim` is ~150MB. The full `python:3.12` is ~1GB. For ML, use `slim` and add only
what you need.

```dockerfile
RUN pip install uv
```

`RUN` executes a command during the build and saves the result as a new layer.
Each `RUN` creates a layer. Layers are cached — if this line hasn't changed,
Docker reuses the cached layer instead of re-running `pip install uv`.

**Layer caching is why Dockerfile order matters:**
```dockerfile
# WRONG — cache-busting order
COPY . .                        # copies all source files (changes often)
RUN pip install -r requirements.txt  # re-runs every time any source changes

# CORRECT — cache-friendly order
COPY requirements.txt .         # only copy requirements first (changes rarely)
RUN pip install -r requirements.txt  # only re-runs when requirements change
COPY . .                        # copy source code last
```

In this project:
```dockerfile
FROM python:3.12-slim

RUN pip install uv               # Layer 1: uv installed (cached after first build)

WORKDIR /app

COPY shared/ ./shared/           # Layer 2: shared code (changes occasionally)
COPY api/ ./api/                 # Layer 3: api code (changes often)

WORKDIR /app/api

RUN uv pip install --system -r requirements.txt  # Layer 4: dependencies (cached when requirements unchanged)

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### The build context — what Docker can see

When you run `docker build`, Docker sends a **build context** to the Docker daemon —
all the files it's allowed to use in `COPY` instructions.

```yaml
# docker-compose.yml
services:
  api:
    build:
      context: .        # build context = 4-Deploy-Online/ directory
      dockerfile: api/Dockerfile
```

With `context: .` (the `4-Deploy-Online/` directory), the Dockerfile can `COPY`:
- `shared/` ✅
- `api/` ✅
- `pipeline/` ✅
- Files outside `4-Deploy-Online/` ❌

This is why `shared/` is at the `4-Deploy-Online/` level — both the `pipeline/Dockerfile`
and `api/Dockerfile` need to copy it, so it must be in the shared build context.

**`.dockerignore`** excludes files from the build context:
```
**/__pycache__
**/*.pyc
**/.venv
**/mlruns            ← don't copy model artifacts into image (they go in volumes)
**/mlflow_*.db       ← don't copy MLflow DB into image
```

Excluding `mlruns/` is important — model artifacts can be hundreds of MB.
They don't belong in the image (which should be reproducible and small).
They belong in volumes (which hold runtime data).

---

### docker-compose — multi-container orchestration

Docker Compose coordinates multiple containers that work together.
Instead of running `docker run` commands with long argument lists, you describe
the system in `docker-compose.yml` and start everything with one command.

```yaml
services:           # each service = one container type

  pipeline:         # the training service
    build: ...      # how to build the image
    volumes: ...    # what storage to mount
    environment:    # environment variables
    profiles:       # only start this service when --profile train is passed
      - train

  api:              # the serving service
    build: ...
    ports:
      - "8000:8000" # host_port:container_port
    volumes: ...
    healthcheck:    # how Docker knows the service is ready
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]

volumes:            # named volumes managed by Docker
  mlflow_store:
```

---

### Profiles — one-shot vs long-running services

The pipeline runs once and exits. The API runs indefinitely.
Docker Compose **profiles** separate them:

```yaml
pipeline:
  profiles:
    - train    # only starts when --profile train is passed
```

```bash
# Start everything (only api — pipeline has a profile)
docker compose up

# Run the pipeline explicitly (one-shot, exits when done)
docker compose --profile train run --rm pipeline
# --rm removes the container after it exits (cleanup)

# API stays running, pipeline exits — correct behavior
```

Without profiles, `docker compose up` would try to start both services,
the pipeline would finish and exit, Docker Compose would see a "failed" container
and potentially restart it in a loop.

---

### Environment variables — configuring containers

Containers should be configurable without rebuilding the image.
Environment variables are the standard mechanism:

```yaml
# docker-compose.yml
environment:
  - MLFLOW_TRACKING_URI=sqlite:////mlflow/mlflow_trip_duration.db
  - MLFLOW_ARTIFACT_LOCATION=/mlflow/artifacts
```

```python
# pipeline/config/config.py
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{_MLFLOW_DB_PATH}"  # local default
)
```

Locally: no env var set → uses the local SQLite file at `pipeline/mlflow_trip_duration.db`.
In Docker: env var set → uses the mounted volume at `/mlflow/mlflow_trip_duration.db`.

Same code. Different behavior. No code change needed.

This is also how you'd point the system at a remote MLflow server:
```bash
export MLFLOW_TRACKING_URI=http://your-mlflow-server:5000
docker compose up api
```

---

## Part 3 — Connecting Concepts to Code

### Why two Dockerfiles

**`pipeline/Dockerfile`** — training container:
```dockerfile
FROM python:3.12-slim
RUN pip install uv
WORKDIR /app
COPY shared/ ./shared/
COPY pipeline/ ./pipeline/
WORKDIR /app/pipeline
RUN uv pip install --system -r requirements.txt
CMD ["python", "main.py", "--sample-size", "500000", "--tune", "--promote"]
```

Contains: Python + ML libraries (scikit-learn, XGBoost, MLflow, Prefect) + training code.
Does NOT contain: the API code, FastAPI, uvicorn.

**`api/Dockerfile`** — serving container:
```dockerfile
FROM python:3.12-slim
RUN pip install uv
WORKDIR /app
COPY shared/ ./shared/
COPY api/ ./api/
WORKDIR /app/api
RUN uv pip install --system -r requirements.txt
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Contains: Python + inference libraries (scikit-learn, XGBoost, MLflow) + FastAPI + serving code.
Does NOT contain: the pipeline code, Prefect, training utilities.

**Both contain `shared/`** — the feature engineering code must be importable in both contexts.

---

### The path resolution inside Docker

In the API container, the filesystem looks like:
```
/app/
├── shared/
│   └── feature_engineering.py
└── api/
    ├── main.py
    ├── model_loader.py
    └── schema.py
```

In `api/model_loader.py`:
```python
_DEPLOYMENT_DIR = Path(__file__).parent.parent   # /app/api/../  = /app/
_PIPELINE_DIR   = _DEPLOYMENT_DIR / "pipeline"   # /app/pipeline/ (doesn't exist in api container)

sys.path.insert(0, str(_DEPLOYMENT_DIR))  # adds /app/ → shared.feature_engineering importable ✅
sys.path.insert(0, str(_PIPELINE_DIR))    # adds /app/pipeline/ → doesn't exist, no-op ✅
```

The preprocessor pickle references `shared.feature_engineering.TripFeatureEngineer`.
Python finds `shared` in `/app/` → loads correctly. ✅

---

### The complete Docker workflow

```bash
# Step 1: build both images (once, or when code changes)
docker compose build

# Step 2: train the model (populates the mlflow_store volume)
docker compose --profile train run --rm pipeline

# Step 3: start the API (reads from the mlflow_store volume)
docker compose up api

# Step 4: test
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"tpep_pickup_datetime": "2019-01-15T14:30:00", "PULocationID": 161,
       "DOLocationID": 237, "passenger_count": 1, "VendorID": 1,
       "RatecodeID": 1, "trip_distance": 2.5, "payment_type": 1}'

# Step 5: retrain when needed (run the pipeline again, new @champion registered)
docker compose --profile train run --rm pipeline

# Step 6: restart API to load new champion
docker compose restart api
```

---

## Part 4 — The Bigger Picture

### What you gain from Docker in ML

| Without Docker | With Docker |
|----------------|-------------|
| "It works on my machine" | Runs identically everywhere |
| Manual dependency management | `docker build` reproduces the exact environment |
| Implicit Python version | `FROM python:3.12-slim` is explicit |
| Shared global packages conflict | Isolated container per service |
| "What version of sklearn is serving?" | `docker inspect` tells you exactly |
| Rollback = change a file path manually | Rollback = `docker compose up --scale api=0 && docker run old-image` |

### What you don't gain yet

This setup uses a local Docker volume. The model runs on your machine.
To move to production you'd need:
- A container registry (Docker Hub, ECR, GCR) to store images
- A volume that persists in the cloud (EFS, GCS bucket)
- An orchestration platform (Kubernetes, ECS) to run containers at scale

These are not needed for learning the patterns. The Docker concepts here —
images, containers, volumes, compose — are identical in production.
Only the infrastructure changes.

---

## Quick Reference

```bash
# Build
docker compose build                          # build all services
docker compose build api                      # build one service

# Run
docker compose up api                         # start api (foreground)
docker compose up -d api                      # start api (background)
docker compose --profile train run --rm pipeline  # run pipeline once

# Inspect
docker compose ps                             # running services
docker compose logs api                       # api logs
docker compose logs -f api                    # follow logs

# Stop
docker compose down                           # stop and remove containers
docker compose down -v                        # also remove volumes (deletes MLflow data!)

# Shell into a running container
docker compose exec api bash

# Rebuild after code changes
docker compose build api && docker compose up api
```
