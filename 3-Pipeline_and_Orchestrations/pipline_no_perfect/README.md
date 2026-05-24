# NYC Taxi ML Pipeline — Plain Python (No Orchestration)

This is the **base pipeline** — no orchestration framework, pure Python.
It is the foundation that `pipeline_with_prefect/` builds on top of.

---

## What This Pipeline Does

Predicts NYC taxi trip duration using historical trip data from Kaggle.

```
Data Download (Kaggle)
  → Preprocessing & Cleaning
    → Train / Val / Test Split   ← split BEFORE feature engineering (no leakage)
      → Feature Engineering      ← fitted on train only
        → Train 5 Models         ← Linear Regression, Ridge, Lasso, Random Forest, Gradient Boosting
          → Select Best Model
            → Hyperparameter Tuning (HalvingRandomSearchCV)
              → Cross-Validation
                → Test Evaluation
                  → Register in MLflow
                    → Save Deployment Package
```

---

## How to Run

```bash
# From repo root (one-time):
uv sync
source .venv/bin/activate

cd 3-Pipeline_and_Orchestrations/pipline_no_perfect

# Quick test (small data, no tuning)
python main.py --sample-size 50000 --skip-tuning

# Full run with tuning
python main.py --sample-size 200000

# Full run, skip cross-validation (faster)
python main.py --sample-size 200000 --skip-tuning --skip-cv

# Specific models only
python main.py --models "Random Forest" "Gradient Boosting"

# Dry run (validate config, no data downloaded)
python main.py --dry-run
```

### View Results in MLflow

```bash
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db
# Open http://127.0.0.1:5000
```

---

## CLI Reference

| Argument | Default | Description |
|---|---|---|
| `--sample-size` | 200000 | Number of training samples |
| `--skip-tuning` | False | Skip hyperparameter tuning |
| `--skip-cv` | False | Skip cross-validation |
| `--models` | all 5 | Which models to train |
| `--experiment-name` | auto | MLflow experiment name |
| `--model-name` | auto | MLflow registered model name |
| `--test-size` | 0.2 | Test set fraction |
| `--val-size` | 0.2 | Validation set fraction |
| `--cv-folds` | 5 | Cross-validation folds |
| `--log-level` | INFO | DEBUG / INFO / WARNING / ERROR |
| `--max-retries` | 3 | Retry attempts for flaky operations |
| `--retry-delay` | 5 | Initial retry delay (seconds) |
| `--steps` | all | Run only specific pipeline steps (1–10) |
| `--dry-run` | False | Validate config without running |

---

## Project Structure

```
pipline_no_perfect/
├── main.py                        # CLI entry point
├── requirements.txt
├── README.md
├── config/
│   └── config.py                  # All configuration dataclasses
└── src/
    ├── pipeline.py                # NYCTaxiMLPipeline class — orchestrates all steps
    ├── data/
    │   ├── data_acquisition.py    # Kaggle download + retry logic
    │   └── data_preprocessing.py  # Cleaning, validation, outlier removal
    ├── features/
    │   └── feature_engineering.py # sklearn Pipeline: engineer → outlier → scale
    ├── models/
    │   ├── model_training.py      # Training + MLflow tracking
    │   ├── model_registry.py      # MLflow registry operations
    │   └── model_deployment.py    # Save deployment artifacts
    └── utils/
        ├── logging_utils.py       # Structured logging setup
        └── retry_utils.py         # @retry_with_backoff decorator
```

---

## Key Design Decisions

### Retry mechanism
Manual `@retry_with_backoff` decorator in `retry_utils.py`. Applied to data download
and model training. Works, but retry state is invisible — you only see the final
success or a Python traceback.

### Orchestration
The `NYCTaxiMLPipeline` class in `src/pipeline.py` calls each step in order.
If step 5 fails, you get a traceback with no information about which of the 5
models failed or at what point.

### Data leakage prevention
Split happens at step 3, before feature engineering at step 4. All sklearn
transformers are `fit` on train only, `transform` applied to val and test.

---

## Actual Results (200K samples, tuning enabled)

| Model | Val R² | Val MAE |
|---|---|---|
| Linear Regression | ~0.65 | ~4.1 min |
| Ridge | ~0.65 | ~4.1 min |
| Lasso | ~0.64 | ~4.2 min |
| Random Forest | ~0.82 | ~2.6 min |
| **Gradient Boosting** | **~0.83** | **~2.5 min** |

**Winner: Gradient Boosting — Test R²: 0.8382, Test MAE: 2.27 min**

---

## What's Missing (Added in `pipeline_with_prefect/`)

- No task-level visibility — one monolithic traceback on failure
- No retry state in any UI — retries happen silently
- No way to re-run a single failed step
- No flow parameters you can change from a UI
- Individual model failures aren't isolated — one failure stops all training
