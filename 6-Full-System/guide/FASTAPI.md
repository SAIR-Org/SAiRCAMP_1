# FastAPI for ML Serving — Mental Model, Concepts & Reference

---

## Part 1 — Why an API? (The Mental Model)

### The problem with model.pkl

After training, you have a model file. You could share it:

```python
# Option 1 — share the file
import pickle
model = pickle.load(open("xgboost_model.pkl", "rb"))
prediction = model.predict(features)
```

This works if everyone using the model:
- Has Python installed
- Has the exact same library versions
- Knows how to load and call the model
- Has access to the model file

In practice, the people who need predictions are:
- A mobile app (Swift/Kotlin — no Python)
- A frontend (JavaScript — no Python)
- Another backend service (Java, Go — no Python)
- A dashboard (needs predictions without running a model)

None of these can import a `.pkl` file.

**An API solves this.** It wraps the model in a standard HTTP interface:

```
Any client (any language, any platform)
         ↓
POST /predict  {"PULocationID": 161, "DOLocationID": 237, ...}
         ↓
FastAPI app loads model, runs prediction
         ↓
{"predicted_duration_minutes": 19.93}
         ↓
Client receives the result
```

The client sends JSON. The server responds with JSON. No Python required on the client side.
No model files to distribute. No version management at the client.

---

### Online vs batch serving — when to use which

There are two modes of ML serving. Students often ask: "why do we need both?"

**Online serving (this API):**
- One request → one prediction → immediate response
- Use when: a user is waiting for the answer
- Example: "How long will this taxi trip take?" — user is about to book the ride
- Latency matters: response must come back in milliseconds to seconds
- Volume: one request at a time (or thousands per second with load balancing)

**Batch serving (next component: `batch/`):**
- Many records → many predictions → stored results
- Use when: no one is waiting, you're scoring historical data
- Example: Score all trips from January 2020 to measure model degradation
- Latency doesn't matter: run overnight, take hours if needed
- Volume: millions of records in one job

This project has both:
- API serves real-time predictions (online)
- Batch scorer scores 2020/2022/2024 data to measure drift (offline)

The same model. Two completely different serving patterns.

---

### Why FastAPI specifically

FastAPI is not the only option. Flask, Django REST Framework, and others exist.
FastAPI is the right choice for ML serving for three reasons:

**1. Automatic request validation (Pydantic)**
```python
# You define this:
class TripRequest(BaseModel):
    PULocationID: int = Field(..., ge=1, le=265)
    trip_distance: float = Field(..., gt=0)

# FastAPI automatically rejects invalid requests:
# PULocationID: 999  → 422 Unprocessable Entity (out of range)
# trip_distance: -1  → 422 Unprocessable Entity (not > 0)
# PULocationID: "abc" → 422 Unprocessable Entity (not an int)
```

Without this, you'd write validation code manually. FastAPI does it for free.

**2. Automatic documentation (Swagger UI)**
```
http://localhost:8000/docs
```
FastAPI generates interactive API documentation automatically from your type annotations.
No extra code. No separate documentation to maintain.
Any developer can open this URL, see all endpoints, try them with real data.

**3. Performance (async-native, ASGI)**
FastAPI is built on Starlette (ASGI framework) and uses async Python.
It's one of the fastest Python web frameworks — comparable to Go and Node for I/O-bound workloads.
For ML serving, the bottleneck is usually model inference (CPU-bound), not I/O,
so async doesn't help with the prediction itself. But it does help serve many
concurrent users without blocking.

---

## Part 2 — FastAPI Concepts

### The lifespan pattern — startup and shutdown

ML serving has a unique requirement: the model must be loaded **before** the first
request arrives. Loading a model on every request would be catastrophically slow:

```python
# WRONG — loads model on every request (100ms-2s per request, just for loading)
@app.post("/predict")
def predict(trip: TripRequest):
    model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")
    return model.predict(...)

# CORRECT — loads model once at startup, reuses on every request
```

FastAPI provides the **lifespan** pattern for startup/shutdown logic:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP: runs once when the server starts
    load_model()       # downloads from MLflow, loads into memory
    yield              # ← server is now running, handling requests
    # SHUTDOWN: runs once when the server stops
    # (cleanup goes here if needed)

app = FastAPI(lifespan=lifespan)
```

When uvicorn starts:
1. `lifespan` begins executing
2. `load_model()` runs — model loaded into memory
3. `yield` — server is ready, starts accepting requests
4. Every `/predict` call uses the already-loaded model
5. When server stops, code after `yield` runs (cleanup)

**Why `yield` instead of `return`:** The `yield` suspends the lifespan context while
the server runs. Code before `yield` = startup. Code after `yield` = shutdown.
This is a Python context manager pattern (`async with`).

---

### Pydantic models — request and response contracts

```python
from pydantic import BaseModel, Field

class TripRequest(BaseModel):
    tpep_pickup_datetime: str
    PULocationID: int = Field(..., ge=1, le=265)   # required, range 1-265
    DOLocationID: int = Field(..., ge=1, le=265)
    trip_distance: float = Field(..., gt=0)         # required, must be > 0
    passenger_count: int = Field(default=1, ge=1, le=6)  # optional, default 1
```

`BaseModel` is Pydantic's base class. It:
- Parses incoming JSON into Python objects
- Validates all fields according to their types and constraints
- Returns a 422 error with a clear message if validation fails
- Provides `.model_dump()` to convert back to a dict

`Field(...)` — the `...` means required (no default). `ge` = greater than or equal.
`gt` = greater than. `le` = less than or equal.

```python
class PredictionResponse(BaseModel):
    predicted_duration_minutes: float
    model_version: str
    model_alias: str
```

The response model does the opposite: takes a Python dict/object and serializes it to JSON.
FastAPI validates the response against this schema too — if your code returns a
`predicted_duration_minutes` that's a string, FastAPI catches it before the client sees it.

---

### Path operations — endpoints

```python
@app.get("/health")
def health():
    s = get_state()
    return {"status": "ok", "model_version": s.version, "model_alias": s.alias}
```

`@app.get("/health")` registers a **GET** handler at the `/health` path.
Returning a dict from a route function automatically serializes to JSON.

```python
@app.post("/predict", response_model=PredictionResponse)
def predict(trip: TripRequest):
    ...
```

`@app.post("/predict")` registers a **POST** handler.
`response_model=PredictionResponse` tells FastAPI to validate the response against
the `PredictionResponse` schema and exclude any extra fields.

The `trip: TripRequest` parameter tells FastAPI to:
1. Parse the request body as JSON
2. Validate it against `TripRequest`
3. Inject the validated object as `trip`

You never write `json.loads(request.body)` manually. FastAPI does it.

---

### HTTP status codes — what they mean

FastAPI returns these automatically:

| Code | Meaning | When |
|------|---------|------|
| 200 | OK | Successful GET or POST |
| 422 | Unprocessable Entity | Pydantic validation failed |
| 503 | Service Unavailable | Model not loaded |
| 500 | Internal Server Error | Unhandled exception |

You can return explicit status codes:
```python
from fastapi import HTTPException

@app.post("/predict")
def predict(trip: TripRequest):
    if get_state().model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    ...
```

---

### Global state — sharing the model across requests

The model and preprocessor live in global state, loaded once at startup:

```python
# model_loader.py
class _State:
    model = None
    preprocessor = None
    version: str = "unknown"
    alias: str = MODEL_ALIAS

_state = _State()

def load_model() -> None:
    # ... loads model and preprocessor from MLflow ...
    _state.model = mlflow.sklearn.load_model(...)
    _state.preprocessor = pickle.load(...)

def get_state() -> _State:
    return _state
```

```python
# main.py
@app.post("/predict")
def predict(trip: TripRequest):
    s = get_state()           # gets the global _state object
    X = s.preprocessor.transform(pd.DataFrame([trip.model_dump()]))
    duration = float(s.model.predict(X)[0])
    ...
```

**Why a class instead of module-level variables?**
`_State` groups related mutable state (model, preprocessor, version, alias) into one object.
`get_state()` gives any part of the app access without importing the private `_state` directly.
This is a simple dependency injection pattern — clean enough for a serving app this size.

---

## Part 3 — Connecting Concepts to Code

### The full request lifecycle

```
Client sends POST /predict with JSON body
        ↓
FastAPI parses JSON → TripRequest Pydantic model
  Validates: PULocationID in [1,265]? trip_distance > 0? ✓
        ↓
predict() function called with validated TripRequest
        ↓
trip.model_dump() → Python dict
pd.DataFrame([dict]) → 1-row DataFrame with correct column names
        ↓
preprocessor.transform(df) → numpy array (23 features)
  TripFeatureEngineer: zone pair, centroid distances, temporal features
  OutlierHandler: clips outliers to training set bounds
  RobustScaler: scales to training set distribution
        ↓
model.predict(array) → [19.93] (duration in minutes)
        ↓
PredictionResponse(predicted_duration_minutes=19.93, ...)
FastAPI serializes to JSON
        ↓
{"predicted_duration_minutes": 19.93, "model_version": "v6", "model_alias": "champion"}
```

### Why `pd.DataFrame([trip.model_dump()])`

The preprocessor's `TripFeatureEngineer.transform()` expects a pandas DataFrame with
named columns — not a numpy array, not a list.

```python
trip.model_dump()
# → {"tpep_pickup_datetime": "2019-01-15T14:30:00", "PULocationID": 161, ...}

pd.DataFrame([trip.model_dump()])
# → 1-row DataFrame:
#   tpep_pickup_datetime  PULocationID  DOLocationID  ...
#   2019-01-15T14:30:00   161           237           ...
```

The `[...]` wraps the dict in a list — `pd.DataFrame` expects a list of records
(each record = one row). A single dict would create a DataFrame with one column per
dict value, which is wrong.

---

### The health endpoint — why it exists

```python
@app.get("/health")
def health():
    s = get_state()
    return {"status": "ok", "model_version": s.version, "model_alias": s.alias}
```

The health endpoint serves two purposes:

**1. Docker healthcheck:**
```yaml
# docker-compose.yml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  retries: 3
  start_period: 60s
```
Docker pings `/health` every 30 seconds. If it fails 3 times, the container is
marked unhealthy. Orchestration platforms (Kubernetes, ECS) use this to know
when to restart a container or route traffic elsewhere.

**2. Operator visibility:**
```bash
curl http://localhost:8000/health
# {"status": "ok", "model_version": "v6", "model_alias": "champion"}
```
At a glance you know what model version is live. When you promote a new champion
and restart the API, the health endpoint confirms the new version is serving.

---

## Part 4 — The Bigger Picture

### Where FastAPI sits in the MLOps stack

```
MLflow Registry    Stores versioned models
        ↓
FastAPI API        Loads @champion, serves predictions   ← this layer
        ↓
Clients            Mobile app, web frontend, other services
        ↓
Monitoring         Track prediction latency, input distributions
```

The API is the **public interface** of the model. Everything about how the model is
trained, versioned, and stored is internal. Clients only see the API contract:
send these fields, get back this response.

When you retrain and promote a new champion, the API contract doesn't change.
Clients don't know (or care) that model v7 replaced v6.

---

### What you actually built

```
Without an API:
  "Here is the model.pkl — figure out how to use it"
  → Client needs Python, right libraries, preprocessing knowledge
  → Version management is manual
  → No validation of inputs
  → No visibility into what's serving

With this API:
  POST /predict — one endpoint, any client, any language
  → Input validation automatic (Pydantic)
  → Model loaded from registry at startup (correct preprocessing guaranteed)
  → /health shows what version is serving
  → /docs gives interactive documentation for free
  → Docker containerizes the whole thing for reproducible deployment
```

---

## Quick Reference

### Run locally

```bash
cd 4-Deploy-Online/api
uvicorn main:app --port 8000           # single worker
uvicorn main:app --port 8000 --reload  # auto-reload on code changes (development)
uvicorn main:app --port 8000 --workers 4  # multi-worker (production)
```

### Test endpoints

```bash
# Health
curl http://localhost:8000/health

# Predict
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "tpep_pickup_datetime": "2019-01-15T14:30:00",
    "PULocationID": 161,
    "DOLocationID": 237,
    "passenger_count": 1,
    "VendorID": 1,
    "RatecodeID": 1,
    "trip_distance": 2.5,
    "payment_type": 1
  }'

# Interactive docs
open http://localhost:8000/docs    # Swagger UI
open http://localhost:8000/redoc  # ReDoc
```

### FastAPI patterns used in this project

```python
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field

# Startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown

app = FastAPI(lifespan=lifespan)

# Request schema with validation
class Request(BaseModel):
    field: int = Field(..., ge=1, le=265)   # required, range
    optional: float = Field(default=1.0)    # optional with default

# Response schema
class Response(BaseModel):
    result: float
    version: str

# Endpoint
@app.post("/predict", response_model=Response)
def predict(req: Request):
    if not ready:
        raise HTTPException(status_code=503, detail="not ready")
    return Response(result=42.0, version="v1")
```
