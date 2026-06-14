# SAiRCAMP — MLOps Course


## Testing  CI/CD Deployment  


A hands-on, project-based MLOps course built around a single real-world problem:
**NYC Yellow Taxi trip duration prediction**, developed progressively across 6 modules.

---

## How This Course Works

Every module builds on the previous one. The codebase grows incrementally.
Each module is live-coded — you watch it being built, then run it yourself.

**One principle: extend, never rewrite.**
Each module adds exactly one layer on top of what already works.

---

## The Full Arc

```
Module 1   model exists
Module 2   model exists + tracked
Module 3a  model exists + tracked + structured
Module 3b  model exists + tracked + structured + orchestrated
Module 4   model exists + ... + served online
Module 5   model exists + ... + served offline + monitored
Module 6   model exists + ... + full integrated system
```

---

## Modules

| # | Folder | What's Built | Teaches | Status |
|---|---|---|---|---|
| 1 | [1-intro_and_setup](1-intro_and_setup/) | Naive → broken → fixed model | EDA, data leakage, sklearn | ✅ |
| 2 | [2-Exp_tracking](2-Exp_tracking/) | MLflow tracking + registry | Experiment comparison, model registry | ✅ |
| 3a | [pipline_no_perfect](3-Pipeline_and_Orchestrations/pipline_no_perfect/) | Structured pipeline | Clean code, retry logic | ✅ |
| 3b | [pipeline_with_prefect](3-Pipeline_and_Orchestrations/pipeline_with_prefect/) | Orchestrated pipeline | @task/@flow, Prefect UI, retries | ✅ |
| 4 | [4-Deploy-Online](4-Deploy-Online/) | Online serving | Schema migration, MLflow aliases, FastAPI, Docker | ✅ |
| 5 | [5-Deploy-Offline](5-Deploy-Offline/) | Batch scoring + monitoring | Batch deployment, drift detection, Streamlit | ✅ |
| 6 | [6-Full-System](6-Full-System/) | Complete integrated system | System integration, full MLOps lifecycle | ✅ |

---

## The Dataset

**Modules 1–3:** NYC Yellow Taxi, January 2016. CSV with lat/lon coordinates.

**Modules 4–6:** NYC TLC official data, 2019–2024. Direct parquet download, no credentials.
Zone IDs instead of lat/lon — the format change is a deliberate teaching moment.

```
https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month:02d}.parquet
```

---

## The Drift Story

Train on 2019 → deploy → batch score by period → watch what happens:

```
2019:    7.7M trips/month   MAE 3.07 min  ← train here
2020-04:  204k trips/month   MAE 5.55 min  ← COVID ⚠️ model breaks
2022-01: 2.3M trips/month   MAE 3.00 min  ← recovery ✅
2024-01: 2.7M trips/month   MAE 3.18 min  ← stable ✅
```

Every student lived through 2020. Zero explanation needed.

---

## Quick Start

```bash
# Setup (from repo root)
uv sync
source .venv/bin/activate

# Run the full system (Module 6 — standalone)
cd 6-Full-System
python pipeline/main.py --sample-size 500000 --tune --promote
docker compose up
# Online API:  http://localhost:8000/docs
# Batch API:   http://localhost:8001/docs
# Dashboard:   http://localhost:8501
```

Each module also runs standalone. See its `README.md` for instructions.

---

## Companion Course

SAiRCAMP runs in parallel with **MLOps From First Principles (DDODS)**.

```
DDODS                                   SAiRCAMP
──────────────────────────────          ──────────────────────────────
Concept-first, broad coverage           Project-first, production depth
Simple demos                            One real dataset (1M+ rows)
Each tool in isolation                  Tools layered onto a growing system
```
