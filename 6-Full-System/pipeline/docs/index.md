# Pipeline v2 — Documentation Index

Reference docs for `4-Deploy-Online/pipeline/`. Each file covers one component in depth: the decisions made, the why behind them, and how each piece connects to the next.

---

## Files

| Doc | Covers |
|---|---|
| [data_acquisition.md](data_acquisition.md) | TLC parquet download, per-month sampling, memory strategy |
| [data_preprocessing.md](data_preprocessing.md) | Cleaning filters, target computation, no-leakage contract |
| [feature_engineering.md](feature_engineering.md) | All 23 features, zone centroid lookup, why each feature exists |
| [model_training.md](model_training.md) | 6-model portfolio, XGBoost config, HalvingRandomSearchCV tuning |
| [model_registry.md](model_registry.md) | MLflow 3.x aliases, @champion/@challenger, how downstream loads the model |
| [flow_and_orchestration.md](flow_and_orchestration.md) | Prefect task graph, 9 steps, why each is a separate task |

---

## Quick Reference

```
Data flow:
  TLC parquet URL
    → DataAcquisition.run()          500k rows, 4 months sampled
    → DataPreprocessor.run()         ~96% retained after filters
    → train/val/test split           64% / 16% / 20%
    → TripFeatureEngineer            23 features
    → OutlierHandler + RobustScaler
    → 6 models trained in parallel   LR, Ridge, Lasso, RF, GBM, XGBoost
    → best model tuned               HalvingRandomSearchCV
    → test set evaluation            runs once, after all training
    → MLflow registry                @champion alias
```

```
Load the model (all downstream components):
  import mlflow
  from config.config import MLFLOW_TRACKING_URI
  mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
  model = mlflow.sklearn.load_model("models:/trip_duration_model@champion")
```

```
Current champion: v22  XGBoost  Test R²=0.817  MAE=3.07 min
```
