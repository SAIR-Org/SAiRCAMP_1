# SAiRCAMP

A hands-on, project-based MLOps course built around a single real-world problem —
NYC Yellow Taxi trip duration prediction — developed progressively across modules.

---

## How This Course Works

Every module builds on the previous one. The codebase grows incrementally.
Each session is live-coded with students — you watch it being built, then run it yourself.

The project starts as a naive notebook and ends as a production ML system:
tracked, versioned, orchestrated, and deployable.

---

## Companion Course

SAiRCAMP runs in parallel with **[MLOps From First Principles (DDODS)](../DDODS/README.md)**.

```
DDODS                                   SAiRCAMP
──────────────────────────────          ──────────────────────────────
Concept-first, broad coverage           Project-first, production depth
Simple demos (Iris, telco churn)        One real dataset (NYC taxi, 1M+ rows)
Each tool introduced in isolation       Tools layered onto a growing system
Read the guide, then run the demo       Watch it built live, then run it yourself
```

If a concept in this course feels unfamiliar, DDODS likely has a dedicated module for it.
If DDODS feels too abstract, this course is where you see it applied at real scale.

---

## Modules

| # | Module | What's built | Status |
|---|---|---|---|
| 1 | [Intro & Setup](1-intro_and_setup/) | Naive model → broken model → production-ready model | ✅ |
| 2 | [Experiment Tracking](2-Exp_tracking/) | MLflow tracking, model registry, promotion workflow | ✅ |
| 3 | [Pipelines & Orchestration](3-Pipeline_and_Orchestrations/) | Plain Python pipeline → Prefect-orchestrated pipeline | ✅ |
| 4 | Deployment *(coming)* | Serve the registered model via FastAPI | 🔜 |
| 5 | Monitoring *(coming)* | Detect data drift, alert on model degradation | 🔜 |

---

## The Project Arc

```
Module 1    Raw notebook → production-grade model (no leakage, Config class, model card)
Module 2    Add MLflow → every run logged, best model registered and staged
Module 3    Add Prefect → pipeline orchestrated, observable, retryable
Module 4    Add FastAPI → registered model served as REST API           (coming)
Module 5    Add monitoring → predictions logged, drift detected         (coming)
```

Each module adds one layer. Nothing is rewritten — only extended.
By the end, the same problem that started as a notebook is a monitored, deployable system.

---

## The Dataset

NYC Yellow Taxi trip records (January 2016, ~10 million trips).
Downloaded via `kagglehub` — requires a free Kaggle account.

**Prediction task:** given pickup location, dropoff location, time, and passenger count —
predict trip duration in minutes. Only information available at pickup time is used.

---

## Setup

```bash
uv sync
source .venv/bin/activate
```

Each module has its own dependencies and instructions in its folder README.
