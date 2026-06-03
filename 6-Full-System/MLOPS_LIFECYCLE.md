# The MLOps Lifecycle — The Full Picture

This document ties all six modules together.
Read this after completing Module 6 to see where every tool fits.

---

## Part 1 — What MLOps Actually Is

### The gap between a model and a product

A data scientist can train a model in an afternoon. The hard part is everything else:

```
Model trained ✅

Questions that remain:
  → How do others use it?          (serving)
  → How do we track what we built?  (experiment tracking)
  → How do we run it reliably?      (orchestration)
  → How do we deploy it safely?     (registry + CI/CD)
  → How do we know if it's still good? (monitoring)
  → What do we do when it degrades? (retraining)
  → How does it fit with other systems? (integration)
```

**MLOps** is the discipline of answering all these questions for ML systems.
It borrows from software engineering (DevOps) and applies it to the unique
challenges of ML — where the "code" (the model) changes when data changes,
not just when a developer writes new code.

---

## Part 2 — The Full Lifecycle

```
┌────────────────────────────────────────────────────────────────────┐
│                     THE MLOPS LIFECYCLE                            │
│                                                                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │  BUILD   │───▶│ REGISTER │───▶│  SERVE   │───▶│ MONITOR  │      │
│  │          │    │          │    │          │    │          │      │
│  │ Module 1 │    │ Module 2 │    │ Module 4 │    │ Module 5 │      │
│  │ Module 3 │    │          │    │          │    │          │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│       ▲                                                │           │
│       │                 ┌──────────────────────────────┘           │
│       │                 │         drift detected                   │
│       │                 ▼                                          │
│       └──── RETRAIN (Module 6) ◀─── human decides ◀─── alert       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

This is not a one-time process. It's a cycle. Models degrade. You retrain.
The cycle repeats for the life of the product.

---

## Part 3 — Where Each Module Fits

### Module 1 — Build (the foundation)

```
Tool:      Jupyter, scikit-learn
Teaches:   EDA, feature engineering, data leakage, model evaluation
Answers:   "Does this problem have a signal? Can a model learn it?"
```

Before you build an MLOps system, you need to know if the ML problem is solvable.
Module 1 shows the exploration process — including how to make mistakes
(Module 1b: deliberate data leakage) and how to fix them (Module 1c).

**What it doesn't do:** Track anything. Run reliably. Deploy anything.

---

### Module 2 — Track (experiment tracking)

```
Tool:      MLflow tracking
Teaches:   Log params, metrics, artifacts. Compare runs. Reproducibility.
Answers:   "Which of my 50 experiments was actually the best one?"
```

Without tracking, every model run is forgotten. You can't compare, reproduce,
or explain your decisions. Module 2 adds memory to the process.

**Key concept:** Every training run is an experiment. Every experiment is logged.
The best experiments get promoted to the registry.

**What it doesn't do:** Structure the code. Deploy anything. Monitor anything.

---

### Module 3 — Structure + Orchestrate (pipeline)

```
Tool:      plain Python (Module 3a), Prefect (Module 3b)
Teaches:   Pipeline class, retry logic, Prefect @task/@flow, observability
Answers:   "How do I run this reliably and know what's happening?"
```

A notebook is not a pipeline. Module 3a shows how to structure code into
repeatable steps. Module 3b adds orchestration — each step becomes an
observable unit with retry logic, state tracking, and UI visibility.

**Key concept (Module 3b):** Tasks must be called from the flow, not from
other tasks. Each task gets its own retry budget and state in the UI.

**What it doesn't do:** Serve predictions. Monitor in production. Handle schema changes.

---

### Module 4 — Deploy Online (serving)

```
Tool:      FastAPI, Docker, MLflow registry
Teaches:   Schema migration, model registry aliases, online serving, containerization
Answers:   "How do I serve this model to users in real time?"
```

Module 4 is where the model becomes a product. Three big transitions:

1. **Schema migration:** 2016 Kaggle (lat/lon) → 2019 TLC (zone IDs). Data sources
   change in production. The system must adapt without rewriting everything.

2. **Registry + aliases:** `@champion` / `@challenger` replace hardcoded version numbers.
   Services load `models:/trip_duration_model@champion` — when you promote a new model,
   every service automatically serves it on next startup.

3. **Docker:** The API is containerized. The same container runs on any machine.
   The path-remapping problem (SQLite stores absolute host paths) is a real Docker
   debugging lesson — see `4-Deploy-Online/docs/DOCKER_DEBUGGING.md`.

**What it doesn't do:** Score historical data. Detect drift. Know if the model is degrading.

---

### Module 5 — Deploy Offline (batch + monitoring)

```
Tool:      Prefect, FastAPI, Streamlit, SQLite, Parquet
Teaches:   Batch deployment, two-output design, drift detection, monitoring dashboard
Answers:   "Is my deployed model still good? What happened to it over time?"
```

Module 5 uses the same model as Module 4 in a completely different way.
Instead of answering one request at a time, it scores entire months of historical data.

Two key contributions:

1. **Batch deployment:** Score all trips for a period → store predictions for analytics.
   Enables questions the online API cannot answer: "Which routes had the worst accuracy
   in January 2020? How did accuracy vary by distance?"

2. **Drift detection:** Aggregate scored results → compute MAE ratio + volume →
   alert if degradation detected. The COVID shock (2020-04: MAE 1.81x, volume -97%)
   is the real example that proves why monitoring exists.

**The lesson the data taught us:** The σ formula for drift detection failed
(train_std=10min is too large). MAE ratio is the right metric — direct, interpretable,
threshold is business-meaningful not statistical.

**What it doesn't do:** Serve real-time predictions. Wire everything together.

---

### Module 6 — Full System (integration)

```
Tool:      Docker Compose (multi-service)
Teaches:   Service integration, Docker networking, shared state, manual retrain workflow
Answers:   "How do all these pieces work together as one system?"
```

Module 6 is mostly about wiring. The services were built in Modules 4 and 5.
The new work is:
- One `docker compose up` starts everything
- Dashboard shows both online predictions and batch/drift results
- Services talk via Docker network names (`http://api:8000`, `http://batch:8001`)
- Retrain is manual: human reviews drift, runs pipeline, restarts API

**The retrain workflow:**
```
Monitoring detects alert (MAE 1.81x in 2020-04)
→ Human decides to retrain
→ Pipeline runs: train_years=[2019, 2020]
→ New model registers as @challenger
→ Champion/challenger gate: evaluated on 2020-06 holdout
→ Challenger wins (+1.37 min improvement)
→ Promoted to @champion
→ docker compose restart api → serves new model
```

---

## Part 4 — The Tools and Why Each One

```
Tool          Module  What it solves
────────────  ──────  ──────────────────────────────────────────────
Jupyter         1     Exploration — see the data before committing to code
scikit-learn    1     Modeling — the actual ML
MLflow          2     Memory — track every experiment, reproduce any run
Prefect         3     Reliability — structure + retry + observability
FastAPI         4,5   Serving — expose the model as an HTTP API
Docker          4,6   Reproducibility — same environment everywhere
Streamlit       5,6   Visibility — dashboard for non-technical stakeholders
SQLite          5     Simplicity — lightweight storage for batch results
Parquet         5     Analytics — columnar format for per-trip predictions
```


## Part 5 — The Data Story

The NYC taxi dataset was chosen because it tells a real drift story:

```
2019:   7.7M trips/month   MAE 3.07 min   ← train here
2020-04:  204k trips/month   MAE 5.55 min   ← COVID ⚠️ everything broke
2022-01: 2.3M trips/month   MAE 3.00 min   ← recovery ✅
2024-01: 2.7M trips/month   MAE 3.18 min   ← stable ✅
```

The drift is real. The COVID event actually happened. The numbers are from the actual
TLC dataset — not manufactured, not approximated.

**Why this matters:** Students who see real data behave differently trust the lessons
more than students who see toy examples. The COVID shock is immediately recognizable
and emotionally resonant. When the model breaks in 2020, students understand exactly why.

**The schema migration story (Module 4):**
NYC TLC changed their data format in 2017 — lat/lon coordinates were replaced by
zone IDs. This is a real production event: a data provider changed their format and
every downstream consumer had to adapt. The course treats this as a teaching moment,
not a nuisance. Modules 1–3 use the old format. Module 4 migrates to the new one.
Students see both versions and understand why migration matters.

---

## Part 6 — The Progression

Each module adds exactly one layer. Nothing is rewritten:

```
Module 1   model exists                                          Jupyter
Module 2   model exists + tracked                               + MLflow
Module 3a  model exists + tracked + structured                  + plain Python
Module 3b  model exists + tracked + structured + orchestrated   + Prefect
Module 4   model exists + ... + served online                   + FastAPI + Docker
Module 5   model exists + ... + served offline + monitored      + batch + Streamlit
Module 6   model exists + ... + full integrated system          + Docker Compose
```

The same problem (NYC taxi trip duration prediction) runs through all six modules.
Students see how each tool integrates with what was already built.
Nothing is thrown away. Everything compounds.

## The One-Sentence Summary of Each Module

```
Module 1:  Does the model work?
Module 2:  Can we reproduce and compare?
Module 3:  Can we run it reliably and watch it?
Module 4:  Can users get predictions in real time?
Module 5:  Is the model still good? What does the data say?
Module 6:  Does it all work together as one system?
```

If you can answer yes to all six, you have built a production ML system.
