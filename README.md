# SAiRCAMP MLOps

**Applied MLOps — a hands-on, project-based course built around a single real-world problem:**  
NYC Yellow Taxi trip duration prediction, developed progressively across 8 modules from a raw notebook to a live, secured, auto-deploying production system.

---

## 🔗 **Part of SAiR MLOps Blueprint**

This repo is the **implementation track** of the SAiR MLOps module.

| Resource | Link |
|---|---|
| **Hub Repo** | [SAIR-Org/SAiR-MLOps-Blueprint](https://github.com/SAIR-Org/SAiR-MLOps-Blueprint) |
| **Theory Track** | [MaaS-YT/MLOps-from-the-first-principles](https://github.com/MaaS-YT/MLOps-from-the-first-principles) |
| **YouTube Theory Playlist** | [MLOps from First Principles](https://youtube.com/playlist?list=PLVM9Nqm8zLE0&si=jtIah3TJB8PjOMgu) |

**Use this repo for:** Building the end-to-end production system.
**Use DDODS for:** Understanding the concepts, mental models, and theory behind MLOps.

> 📌 **Take both tracks together** — watch the theory, then build it live.

---

## How This Course Works

Every module builds on the previous one. The codebase grows incrementally.  
Each module is live-coded — you watch it being built, then run it yourself.

**One principle: extend, never rewrite.**  
Each module adds exactly one layer on top of what already works.

The system starts as a notebook and ends as a secured, auto-deploying production service with a real domain, HTTPS, and CI/CD — the same stack used in industry.

---

## The Full Arc

```
Module 1   model exists
Module 2   model exists + tracked
Module 3a  model exists + tracked + structured
Module 3b  model exists + tracked + structured + orchestrated
Module 4   model exists + ... + served online
Module 5   model exists + ... + served offline + monitored
Module 6   model exists + ... + full integrated system (local)
Module 7   model exists + ... + running on a real VPS
Module 8   model exists + ... + secured domain + CI/CD + HTTPS
── coming ──────────────────────────────────────────────────────
Module 9   model exists + ... + monitored + observable in production
```

---

## Modules

| # | Folder | What's Built | Key Concepts | Ports | Status |
|---|---|---|---|---|---|
| 1 | [1-intro_and_setup](1-intro_and_setup/) | Naive → broken → fixed model | EDA, data leakage, sklearn pipelines | — | ✅ |
| 2 | [2-Exp_tracking](2-Exp_tracking/) | MLflow tracking + model registry | Experiment comparison, runs, aliases | — | ✅ |
| 3a | [pipline_no_perfect](3-Pipeline_and_Orchestrations/pipline_no_perfect/) | Structured pipeline | Clean code, retry logic, separation of concerns | — | ✅ |
| 3b | [pipeline_with_prefect](3-Pipeline_and_Orchestrations/pipeline_with_prefect/) | Orchestrated pipeline | `@task`/`@flow`, Prefect UI, retries, observability | — | ✅ |
| 4 | [4-Deploy-Online](4-Deploy-Online/) | Online serving | FastAPI, Docker, MLflow aliases, schema migration | `8000` | ✅ |
| 5 | [5-Deploy-Offline](5-Deploy-Offline/) | Batch scoring + drift monitoring | Async API, drift detection, MAE ratio, Streamlit | `8000` `8001` `8501` | ✅ |
| 6 | [6-Full-System](6-Full-System/) | Full integrated local system | Docker Compose, service networking, MLflow server | `8000` `8001` `8501` | ✅ |
| 7 | [7-Deployment_test](7-Deployment_test/) | Running on a real VPS | SSH, firewall, remote MLflow, SSH tunnel, port mapping | `1078` `1079` `1080` `1081` | ✅ |
| 8 | [8-CI-CD-Ngnix](8-CI-CD-Ngnix/) | Production hardening | Nginx reverse proxy, DuckDNS, SSL/Certbot, GitHub Actions CI/CD | `1078` `1079` `1080` `1081` | ✅ |

---

## Why the Ports Change at Module 7

Modules 1–6 run locally — default ports work fine with no conflicts.  
From Module 7 onward the system runs on a **shared VPS** alongside other services.  
Ports are changed to avoid conflicts and the system is placed behind nginx so users only ever see a clean domain URL — not port numbers.

```
Modules 1–6  (local)        localhost:8000 / 8001 / 8501
Module 7     (VPS, direct)  server-ip:1078 / 1079 / 1080 / 1081
Module 8     (VPS, nginx)   https://your-domain.com/
                                /          → dashboard
                                /api/      → online API
                                /batch/    → batch API
                                /mlflow/   → MLflow UI
```

---

## The Dataset

**Modules 1–3:** NYC Yellow Taxi, January 2016. CSV with lat/lon coordinates.

**Modules 4–8:** NYC TLC official data, 2019–2024. Direct parquet download, no credentials needed.  
Zone IDs instead of lat/lon — the format change is a deliberate teaching moment about schema drift.

```
https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month:02d}.parquet
```

---

## The Drift Story

Train on 2019 → deploy → batch score by period → watch what happens:

```
2019:     7.7M trips/month   MAE 3.07 min  ← train here
2020-04:   204k trips/month   MAE 5.55 min  ← COVID ⚠️  model breaks
2022-01:  2.3M trips/month   MAE 3.00 min  ← recovery  ✅
2024-01:  2.7M trips/month   MAE 3.18 min  ← stable    ✅
```

Every student lived through 2020. Zero explanation needed.  
This is why monitoring exists — without it, the model silently serves 80% worse predictions for months.

---

## Quick Start by Module

### Modules 1–3 — Notebooks and pipelines

```bash
# From repo root
uv sync && source .venv/bin/activate

# Module 1
cd 1-intro_and_setup && jupyter notebook

# Module 2
cd 2-Exp_tracking && jupyter notebook

# Module 3b (orchestrated pipeline)
cd 3-Pipeline_and_Orchestrations/pipeline_with_prefect
prefect server start          # terminal 1
python main.py --sample-size 50000 --no-tune   # terminal 2
```

### Modules 4–6 — Local Docker system

```bash
cd 6-Full-System

# Train first (local)
cd pipeline
python main.py --sample-size 500000 --tune --promote

# Start the full system
cd ..
docker compose up

# Services
# Online API:  http://localhost:8000/docs
# Batch API:   http://localhost:8001/docs
# Dashboard:   http://localhost:8501
```

### Module 7 — VPS deployment

```bash
# On your local machine — open SSH tunnel to remote MLflow
ssh -N -L 1081:localhost:1081 user@your-vps-ip

# Train locally against the remote MLflow
export MLFLOW_TRACKING_URI=http://localhost:1081
cd 7-Deployment_test/pipeline
python main.py --sample-size 500000 --tune --promote

# On the VPS — start the full system
cd ~/Project/7-Deployment_test
docker compose up -d

# Access directly via IP
# http://your-vps-ip:1080         → dashboard
# http://your-vps-ip:1078/docs    → online API
# http://your-vps-ip:1079/docs    → batch API
# http://your-vps-ip:1081         → MLflow UI
```

### Module 8 — Production (nginx + HTTPS + CI/CD)

```bash
# On the VPS
cd ~/Project/8-CI-CD-Ngnix
docker compose up -d

# Access via domain (HTTPS)
# https://your-domain.com/          → dashboard
# https://your-domain.com/api/docs  → online API
# https://your-domain.com/batch/docs → batch API
# https://your-domain.com/mlflow/   → MLflow UI

# CI/CD — push to main = auto-deploy
git push origin main
```

---

## Concept Guides by Module

Each module has its own docs anchoring the key ideas:

| Module | Guide | Concept |
|---|---|---|
| 2 | [MLFLOW_QUICKSTART.md](2-Exp_tracking/MLFLOW_QUICKSTART.md) | Experiment tracking, runs, registry, aliases |
| 3b | [PREFECT_QUICKSTART.md](3-Pipeline_and_Orchestrations/pipeline_with_prefect/PREFECT_QUICKSTART.md) | Orchestration, `@task`/`@flow`, retries, states |
| 4 | [FASTAPI.md](4-Deploy-Online/FASTAPI.md) | Online serving, lifespan, Pydantic, health checks |
| 4 | [DOCKER_FOR_ML.md](4-Deploy-Online/DOCKER_FOR_ML.md) | Images, containers, volumes, bind mounts |
| 4 | [MLFLOW_REGISTRY.md](4-Deploy-Online/MLFLOW_REGISTRY.md) | Registry vs tracking, preprocessor artifact, shared code |
| 5 | [BATCH_DEPLOYMENT.md](5-Deploy-Offline/BATCH_DEPLOYMENT.md) | Batch vs online, async API, two-output design |
| 5 | [DRIFT_DETECTION.md](5-Deploy-Offline/DRIFT_DETECTION.md) | MAE ratio, volume signal, why σ formula fails |
| 6 | [SYSTEM_INTEGRATION.md](6-Full-System/SYSTEM_INTEGRATION.md) | Docker networking, shared state, startup order |
| 6 | [MLFLOW_SERVER.md](6-Full-System/MLFLOW_SERVER.md) | Why SQLite broke in Docker, tracking server solution |
| 6 | [MLOPS_LIFECYCLE.md](6-Full-System/MLOPS_LIFECYCLE.md) | Full picture — where every tool fits |
| 7 | [README.md](7-Deployment_test/README.md) | VPS setup, SSH tunnel, remote MLflow, port strategy |
| 8 | [ngnix.md](8-CI-CD-Ngnix/ngnix.md) | Reverse proxy, WebSocket, 127.0.0.1 vs localhost, 308 vs 301 |
| 8 | [SSL.md](8-CI-CD-Ngnix/SSL.md) | Certbot, Let's Encrypt, HTTP→HTTPS, the 308 trap |
| 8 | [CICD.md](8-CI-CD-Ngnix/CICD.md) | GitHub Actions, SSH deploy, secrets, runner lifecycle |

---

## Companion Course — DDODS

SAiRCAMP MLOps runs in parallel with **DDODS (MLOps from First Principles)**.

```
DDODS (Theory)                          SAiRCAMP MLOps (Implementation)
──────────────────────────────          ──────────────────────────────
Concept-first, broad coverage           Project-first, production depth
Simple focused demos                    One real dataset (1M+ rows)
Each tool explained in isolation        Tools layered onto a growing system
Theory of why things work               Reality of what breaks in production
```

Use DDODS to understand the concepts deeply.  
Use SAiRCAMP MLOps to build something real with them.

---

## What You Will Have Built by Module 8

```
A secured, auto-deploying production MLOps system:

  GitHub push
      ↓
  GitHub Actions (CI/CD)
      ↓
  VPS: git pull + docker compose up --build
      ↓
  nginx (HTTPS, port 443)
      ├── /           → Streamlit dashboard    :1080
      ├── /api/       → FastAPI online API     :1078
      ├── /batch/     → Batch scoring API      :1079
      └── /mlflow/    → MLflow tracking UI     :1081
```

Trained on 2019 NYC taxi data. Serving real predictions. Detecting drift.  
Reachable from anywhere in the world at `https://your-domain.com`.

---

## 📚 **Where This Fits in SAIR Jr.**

```
Module 4 — Applied Deep Learning     ✅   github.com/SAIR-Org/SAIR_Jr
Module 5 — GPT from Scratch          ✅   github.com/SAIR-Org/SAIR_Jr
Module 6 — MLOps  ← you are here          github.com/SAIR-Org/SAiR-MLOps-Blueprint
  ├── DDODS                         (theory, standalone repo)
  └── SAIRCAMP                      (live builds, standalone repo) ← YOU ARE HERE
Capstone — Real-World Impact Project      github.com/SAIR-Org/SAIR_Jr
```

---

## License

This project is for educational purposes. All content is provided as a companion resource to the live cohort sessions.
