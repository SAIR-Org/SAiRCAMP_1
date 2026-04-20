# Module 1 — Introduction & Setup

**Project:** NYC Yellow Taxi Trip Duration Prediction  
**Goal:** Build a production-ready ML model, progressively — starting from scratch, breaking things deliberately, then fixing them properly.

---

## What This Module Is

This is a live-coding module. The instructor builds the project in front of you, one notebook at a time.

The three notebooks are not independent — they are three stages of the same project.
Each stage adds a layer of production thinking. The problems in stage 2 are **deliberate**.
The fixes in stage 3 are the point.

```
nyc_1.ipynb    Explore the problem. Build a first honest model.
nyc_2.ipynb    Build fast and dirty. Watch everything that can go wrong, go wrong.
nyc_3.ipynb    Fix every problem. Arrive at a production-ready implementation.
```

Follow along. Run the cells. When the instructor introduces a bug or a bad practice,
notice it — it will be fixed in the next notebook.

---

## The Problem

A taxi app needs to estimate trip duration at the moment of pickup:

```
User opens app → enters destination → app shows "Your trip will take ~14 minutes"
```

The model must make this prediction using **only information available at pickup time**:
where you are, where you're going, what time it is, how many passengers.

It cannot use fare amount, tip, or total cost — those are only known after the trip ends.
This constraint is not obvious. Most of notebook 2 is about what happens when you ignore it.

---

## The Dataset

NYC Yellow Taxi trip records, January 2016 (~10 million trips).
Each row is one trip. 19 columns including pickup/dropoff coordinates,
timestamps, distance, passenger count, and financial fields.

The target: `trip_duration` — computed from dropoff minus pickup time, in minutes.

Downloaded via `kagglehub` from the Kaggle dataset `elemento/nyc-yellow-taxi-trip-data`.

---

## Stage 1 — `nyc_1.ipynb`: Explore Honestly

**What happens:** Load 500k rows. Build the target variable. Clean unrealistic trips.
Engineer features that make sense (haversine distance, rush hour flag, day of week).
Train Linear Regression and Polynomial Regression. Evaluate fairly.

**Result:** Polynomial Regression, R² ≈ 0.71, MAE ≈ 3 minutes.

**What this notebook gets right:**
- Uses only pickup-time features
- Clean, honest evaluation
- Saves the model properly

**What it doesn't have yet:** no tracking, no versioning, no validation set, no reproducibility guarantees.

This is the baseline. A real result from a clean first attempt.

---

## Stage 2 — `nyc_2.ipynb`: Break It (On Purpose)

**What happens:** The same problem, rebuilt quickly — with 14 labeled production failures injected deliberately.

The instructor codes this live. Every problem is marked with `⚠️ PROBLEM N:` in the code.
Watch for them.

**The 14 problems:**

| # | Problem | Effect |
|---|---|---|
| 1 | No random seed | Different results every run — not reproducible |
| 2 | Data leakage: post-trip features | Model sees `fare_amount`, `tip_amount`, `total_amount` — unknown at pickup |
| 3 | Feature engineering before split | Test data statistics contaminate training |
| 4 | No configuration | Magic numbers scattered everywhere |
| 5 | No validation set | Can't detect overfitting |
| 6 | No cross-validation | Unreliable performance estimates |
| 7 | No hyperparameter tuning | Default parameters throughout |
| 8 | No experiment tracking | Can't compare runs, no history |
| 9 | No model versioning | Overwrites previous models |
| 10 | Test set used for selection | Optimistic, dishonest metrics |
| 11 | No error analysis | Don't know where the model fails |
| 12 | No documentation | No model card, no usage instructions |
| 13 | Deployment-breaking leakage | Prediction function requires post-trip inputs |
| 14 | No environment spec | Can't reproduce the environment |

**The fake result:** Random Forest, R² ≈ 0.96, MAE ≈ 0.77 minutes.

This looks excellent. It is not. The model learned from the fare amount and tip —
information that perfectly encodes trip duration because fares are calculated by time and distance.
The model is memorizing the answer, not predicting it.

This is what data leakage looks like in practice: impressive numbers that collapse in production.

---

## Stage 3 — `nyc_3.ipynb`: Fix Everything

**What happens:** A production-grade implementation that addresses every problem from stage 2.

**The key structural decisions:**

**Split first, engineer second.**  
All feature engineering happens inside a custom sklearn transformer (`NYCYellowTaxiFeatureEngineer`).
The data is split into train/val/test *before* any feature engineering runs.
The transformer is fit on training data only, then applied to val and test.

**No leakage features.**  
Explicitly excluded: `fare_amount`, `tip_amount`, `total_amount`, `extra`, `mta_tax`,
`tolls_amount`, `improvement_surcharge`, `store_and_fwd_flag`, `tpep_dropoff_datetime`.
Only pickup-time information is used.

**Config class.**  
Every hardcoded number lives in one place: `RANDOM_STATE`, `TEST_SIZE`, filter thresholds,
model hyperparameters. Change the config, everything changes consistently.

**Proper evaluation.**  
Train/val/test split. Cross-validation. The test set is touched exactly once —
after model selection is complete. Validation metrics drive all decisions.

**The honest result:** Gradient Boosting (or Random Forest), R² ≈ 0.72–0.83, MAE ≈ 2–3 minutes.

Lower than stage 2. This is correct. The model is now predicting honestly.

---

## What to Pay Attention To

**The leakage moment** — when stage 2 adds `fare_amount` to the features.
The R² jumps dramatically. This is the moment to ask: "why would a model trained
on trip cost know the duration before the trip starts?"

**The split-first discipline** — stage 3 creates three splits before writing a single
line of feature engineering. The order is not a detail — it is the architecture.

**The `fit_transform` / `transform` pattern** — the preprocessor is fitted once on training.
Validation and test are transformed using the same fitted parameters.
This is how you guarantee that test-time behavior matches training-time behavior.

**The model card** — stage 3 ends by saving not just the model file but a complete
`model_card.json`: what data was used, what features are required, what the metrics are,
what the limitations are, what monitoring is recommended.
This is the handoff document. Without it, no one can safely deploy or maintain the model.

---

## The Numbers to Remember

| Stage | Notebook | Model | R² | MAE | Honest? |
|---|---|---|---|---|---|
| Explore | nyc_1 | Polynomial Regression | 0.71 | 3.0 min | Yes |
| Break | nyc_2 | Random Forest (leakage) | 0.96 | 0.77 min | No — data leakage |
| Fix | nyc_3 | Gradient Boosting (clean) | ~0.83 | ~2.3 min | Yes |

The production model is "worse" than the broken model. That is the lesson.

---

## What Comes Next

Module 2 (`2-Exp_tracking/`) takes the stage 3 model and adds experiment tracking with MLflow.
Every training run will be logged. Models will be versioned in a registry.
The progression continues: the code from this module is the foundation everything else builds on.

---

## Setup

```bash
uv sync
source .venv/bin/activate
jupyter notebook
```

You need a Kaggle account and API credentials for `kagglehub` to download the dataset.
Set `KAGGLE_USERNAME` and `KAGGLE_KEY` as environment variables, or place
`kaggle.json` in `~/.kaggle/`.
