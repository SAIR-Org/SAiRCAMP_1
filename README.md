# SAiRCAMP

A hands-on, project-based MLOps course built around a single real-world problem —
NYC Yellow Taxi trip duration prediction — developed progressively across modules.

---

## How This Course Works

Every module builds on the previous one. The codebase grows incrementally.
Each session is live-coded with students — you watch it being built, then run it yourself.

The project starts as a naive notebook and ends as a fully automated production ML system:
tracked, versioned, orchestrated, deployed, monitored, and self-healing.

**One principle: extend, never rewrite.**
Each module adds exactly one layer on top of what already works.

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

If a concept feels unfamiliar, DDODS has a dedicated module for it.
If DDODS feels too abstract, this course is where you see it applied at real scale.

---

## The Full Arc

```
Module 1   model exists
Module 2   model exists + tracked
Module 3a  model exists + tracked + structured
Module 3b  model exists + tracked + structured + orchestrated
Module 4   model exists + tracked + structured + orchestrated + deployed + monitored + self-healing
```

---

## Modules

| # | Module | What's Built | Teaches | Status |
|---|---|---|---|---|
| 1 | [Intro & Setup](1-intro_and_setup/) | Naive → broken → production-ready model | EDA, data leakage, sklearn | ✅ |
| 2 | [Experiment Tracking](2-Exp_tracking/) | MLflow tracking + model registry | MLflow, experiment comparison, staging/production | ✅ |
| 3a | [Plain Pipeline](3-Pipeline_and_Orchestrations/pipline_no_perfect/) | Structured Python pipeline | Clean code, retry logic, 10-step pipeline | ✅ |
| 3b | [Prefect Pipeline](3-Pipeline_and_Orchestrations/pipeline_with_prefect/) | Prefect-orchestrated pipeline | @task/@flow, UI visibility, task retries | ✅ |
| 4 | [Deployment](4-Deployment/) | Full production system | Schema migration, online + batch deployment, drift, auto-retraining | 🔜 |

---

## Module 4 — The Grand Plan

Module 4 is where all previous tools stop being academic and become necessary.
It uses real production data (2019 TLC), introduces real drift (COVID 2020, new normal 2024),
and ends with a system that detects problems and fixes itself.

```
4-Deployment/
├── pipeline/     Train on 2019 TLC data → register Production model in MLflow
├── api/          FastAPI /predict endpoint → online serving (per-request)
├── batch/        Prefect scheduled flow → score monthly data (2020/2022/2024)
├── monitoring/   Drift detection → MAE chart over time, alert on threshold breach
├── retrain/      Champion/challenger → auto-retrain + compare before promoting
└── dashboard/    Streamlit → the complete product (predict / batch / drift / health)
```

### The Drift Story

```
Train:  2019 — 7.7M trips/month  avg_fare=$12.53  ← baseline
Batch score forward in time:
  2020:  238k trips/month   COVID collapse    → model breaks (MAE spikes)
  2022:  2.5M trips/month   new normal        → trip patterns changed
  2024:  3.0M trips/month   today             → fares 45% higher than 2019
```

Three real drift types in one dataset. No simulation needed.
Every student lived through 2020 — the context requires zero explanation.

### The Teaching Moments

| Step | The Lesson |
|---|---|
| pipeline | Schema migration — data sources change format (lat/lon → zone IDs) |
| api | Online vs batch — two patterns, two use cases, one decision |
| batch | Drift is real — COVID broke the model without anyone touching the code |
| monitoring | Why monitoring exists — nobody watches 7M predictions by hand |
| retrain | Champion/challenger — retraining without a gate can silently hurt you |
| dashboard | The full product — this is what an MLOps engineer actually ships |

---

## The Dataset

**Modules 1–3:** NYC Yellow Taxi records, January 2016 (~10M trips).
Downloaded via `kagglehub`. Format: CSV with lat/lon coordinates.

**Module 4:** NYC TLC official data, 2019–2024. Direct parquet download.
No Kaggle account needed. Zone IDs instead of lat/lon.
The format change is intentional — schema migration is a lesson, not a flaw.

---

## Setup

```bash
uv sync
source .venv/bin/activate
```

Each module has its own `README.md` with full instructions.
