# Model Training

**File:** `src/models/model_training.py`  
**Class:** `ModelTrainer`  
**Function:** `build_model_portfolio()`

---

## Overview

Trains 6 models on the engineered features, tracks every run in MLflow, selects the best by validation R², and tunes it with `HalvingRandomSearchCV`. The winner is evaluated once on the held-out test set.

---

## The 6 Models

| Model | Role | Typical Val R² |
|---|---|---|
| `LinearRegression` | Baseline — shows the linear signal floor | 0.677 |
| `Ridge` | Regularized linear — checks if coefficients need shrinking | 0.677 |
| `Lasso` | Sparse linear — feature selection via L1 penalty | 0.674 |
| `RandomForestRegressor` | Strong tree ensemble — parallel, robust | 0.812 |
| `GradientBoostingRegressor` | Sequential boosting (sklearn) — slow but solid | 0.797 |
| `XGBoost` | Optimized boosting — champion in practice | **0.816** |

The linear models (R²≈0.677) establish what the signal looks like without interactions. The gap between 0.677 and 0.816 is entirely explained by `zone_pair` and `centroid_distance_miles` — features that require non-linear splits to exploit.

---

## XGBoost Configuration

```python
XGBRegressor(
    n_estimators    = 300,
    learning_rate   = 0.05,
    max_depth       = 6,
    subsample       = 0.8,
    colsample_bytree= 0.8,
    tree_method     = 'hist',   # fast histogram-based splits
    n_jobs          = -1,
    verbosity       = 0
)
```

**Why `tree_method='hist'`?**  
The `hist` method bins continuous features before building trees. On 307k training rows with 23 features, this is 5–10× faster than the default `exact` method with negligible accuracy difference.

**Why `subsample=0.8` and `colsample_bytree=0.8`?**  
Row and column subsampling reduce overfitting and speed up training by 20%. The 20% dropout forces the model to generalize rather than memorize specific rows/features.

---

## Hyperparameter Tuning

Tuning uses `HalvingRandomSearchCV` from sklearn (no external dependencies).

**Why HalvingRandomSearchCV instead of GridSearch or Optuna?**

| Method | How it works | Tradeoff |
|---|---|---|
| GridSearchCV | Trains every combination on full data | Thorough but slow |
| RandomSearchCV | Random combinations, full data | Faster, less thorough |
| **HalvingRandomSearchCV** | Start with many configs + few data, eliminate weak ones, keep strong ones | Best speed/quality balance |
| Optuna | Bayesian optimization, learns from past trials | Best quality, extra dependency |

`HalvingRandomSearchCV` is the right call here because it's built into sklearn (students already know it) and it's fast enough on 300k rows. The tuning step is about showing students that hyperparameters are tracked in MLflow — the actual R² improvement is secondary.

### XGBoost Tuning Grid

```python
{
    'n_estimators':    [300, 500],
    'learning_rate':   [0.03, 0.05],
    'max_depth':       [5, 6, 8],
    'subsample':       [0.8, 1.0],
    'colsample_bytree':[0.8, 1.0],
}
```

### Configuration

```python
tuning_n_candidates  = 6    # configs evaluated in first halving round
tuning_min_resources = 100  # minimum rows per config in first round
tuning_factor        = 3    # each round keeps top 1/3 of configs
tuning_cv_folds      = 3    # cross-validation folds per config
```

A tuned model is only registered if it improves over the base model by at least `min_r2_improvement = 0.01`. Otherwise the base model is kept.

---

## MLflow Tracking Per Run

Every training run logs:

```
Params:     model hyperparameters (from model.get_params())
            train_samples, val_samples, features count

Metrics:    train_r2, val_r2, train_rmse, val_rmse
            train_mae, val_mae, training_time, overfitting_gap
            (test_r2, test_mae, test_rmse logged after evaluation)

Tags:       model_family, data_leakage='none', orchestrator='prefect'
            data_source='tlc_direct', schema_version='zone_ids'
            final_model='true', deployment_ready='true' (on champion)

Artifacts:  model (sklearn pipeline artifact)
            feature_importance.json (XGBoost only, on champion run)
```

**Why log `overfitting_gap`?**  
`train_r2 - val_r2`. A gap > 0.15 signals the model is memorizing training data. Random Forest typically shows 0.08–0.12 — acceptable. If a student adds a leaky feature, this metric spikes immediately and is visible in the MLflow UI.

---

## No-Leakage Training Contract

The split happens **before** feature engineering:

```
Raw DataFrame (X, y)
    ↓
train_test_split → X_train_raw, X_val_raw, X_test_raw
    ↓
engineer_features:
    preprocessor.fit(X_train_raw)           ← sees ONLY training rows
    preprocessor.transform(X_train_raw)     ← X_train_p
    preprocessor.transform(X_val_raw)       ← X_val_p   (unseen)
    preprocessor.transform(X_test_raw)      ← X_test_p  (unseen)
    ↓
model.fit(X_train_p, y_train)
model.predict(X_val_p)                      ← validation metrics
    ↓ (after all training and tuning)
model.predict(X_test_p)                     ← test metrics (once)
```

The scaler's `median` and `IQR`, the outlier handler's `bounds`, and the `feature_names_` are all fit on training data only.

---

## Splitting Ratios

```python
test_size = 0.20    # 20% held out immediately, never seen during training or tuning
val_size  = 0.20    # 20% of remaining for validation during training

Result on 480k clean rows:
  Train: 307,775 rows (64%)
  Val:    76,944 rows (16%)
  Test:   96,180 rows (20%)
```

---

## Benchmark vs 2016 Pipeline

| | 2016 (pipeline_with_prefect) | 2019 (this pipeline) |
|---|---|---|
| Best model | Gradient Boosting | XGBoost |
| Test R² | 0.838 | 0.817 |
| MAE | 2.26 min | 3.07 min |
| Features | 19 (lat/lon-based) | 23 (zone + centroid) |

The 0.02 R² gap is structural: 2016 had trip-level lat/lon (exact pickup/dropoff GPS) whereas 2019 has zone-level centroids (approximate). That gap is not closable without a zone-to-GPS mapping for every trip.

The 0.81 min MAE gap is partly explained by 2019 having more traffic variability (more data from outer boroughs, more mixed trip types) than the 2016 Kaggle snapshot.
