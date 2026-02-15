# 🏗️ Pipeline Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER / DATA SCIENTIST                         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                    ┌────────────▼──────────────┐
                    │      main.py              │
                    │  (Prefect Flow Runner)    │
                    └────────────┬──────────────┘
                                 │
        ┌────────────────────────┴────────────────────────┐
        │                                                  │
┌───────▼────────┐                              ┌─────────▼──────────┐
│  PREFECT       │                              │     MLFLOW         │
│  Orchestrator  │◄─────────logs/metrics───────┤   Tracking Server  │
│                │                              │                    │
│ • Task Retry   │                              │ • Experiments      │
│ • Concurrency  │                              │ • Metrics          │
│ • Monitoring   │                              │ • Parameters       │
└───────┬────────┘                              │ • Artifacts        │
        │                                       │ • Model Registry   │
        │                                       └─────────┬──────────┘
        │                                                 │
        │                                       ┌─────────▼──────────┐
        │                                       │  SQLite Database   │
        │                                       │ mlflow_nyc_taxi.db │
        │                                       └────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────────────┐
│                        PIPELINE STAGES                                │
└──────────────────────────────────────────────────────────────────────┘
```

## Detailed Pipeline Flow

```
START
  │
  ├─► [STAGE 1] MLflow Setup
  │   ├─ Initialize tracking URI
  │   ├─ Create/set experiment
  │   └─ Configure tags
  │
  ├─► [STAGE 2] Data Loading
  │   ├─ Download from Kaggle (kagglehub)
  │   ├─ Load in chunks (500k rows)
  │   └─ Sample data (200k default)
  │
  ├─► [STAGE 3] Data Preprocessing
  │   ├─ Clean data
  │   │   ├─ Filter trip durations (1-120 min)
  │   │   ├─ Filter distances (0.1-50 mi)
  │   │   ├─ Filter NYC coordinates
  │   │   └─ Filter passengers (1-6)
  │   ├─ Validate no leakage
  │   └─ Split data (64% train, 16% val, 20% test)
  │
  ├─► [STAGE 4] Feature Engineering
  │   ├─ Build preprocessing pipeline
  │   │   ├─ NYCTaxiFeatureEngineer
  │   │   │   ├─ Distance features (haversine, manhattan)
  │   │   │   ├─ Temporal features (hour, day, cyclical)
  │   │   │   ├─ Airport features (JFK, LGA)
  │   │   │   └─ Interaction features
  │   │   ├─ OutlierHandler (IQR clipping)
  │   │   └─ RobustScaler
  │   └─ Fit on train, transform all sets
  │
  ├─► [STAGE 5] Model Training
  │   ├─ Train 5 models
  │   │   ├─ Linear Regression
  │   │   ├─ Ridge Regression
  │   │   ├─ Lasso Regression
  │   │   ├─ Random Forest
  │   │   └─ Gradient Boosting
  │   ├─ Log to MLflow (params, metrics, models)
  │   ├─ Auto-register models
  │   └─ Select best model (by val_r2)
  │
  ├─► [STAGE 6] Hyperparameter Tuning (Optional)
  │   ├─ Check if best model is tunable (RF or GB)
  │   ├─ HalvingRandomSearchCV
  │   │   ├─ Progressive resource allocation
  │   │   ├─ Efficient candidate search
  │   │   └─ 3-fold cross-validation
  │   ├─ Compare tuned vs original
  │   └─ Select better model
  │
  ├─► [STAGE 7] Model Evaluation
  │   ├─ Test set evaluation
  │   │   ├─ R² Score
  │   │   ├─ RMSE
  │   │   └─ MAE
  │   ├─ Cross-validation (3-fold)
  │   ├─ Generate comprehensive report
  │   └─ Log all metrics to MLflow
  │
  ├─► [STAGE 8] Model Registry
  │   ├─ Tag best model run
  │   ├─ Promote to Staging
  │   ├─ Update model metadata
  │   ├─ Archive old production (if auto-promote)
  │   ├─ Promote to Production (if enabled)
  │   └─ Display registry status
  │
  └─► END (Return results)
```

## Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DATA FLOW                                   │
└─────────────────────────────────────────────────────────────────────┘

Raw Data (Kaggle)
      │
      ▼
┌─────────────────┐
│ data_loader.py  │ ──► DataFrame (1M+ rows)
└─────────────────┘
      │
      ▼
┌─────────────────────┐
│ data_preprocessing  │ ──► Cleaned DataFrame (200k rows)
│      .py            │ ──► Train/Val/Test splits
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│ feature_engineering │ ──► X_train_processed (30+ features)
│      .py            │ ──► X_val_processed
└─────────────────────┘     └─ X_test_processed
      │
      ├──────────────────────────────────────┐
      │                                      │
      ▼                                      ▼
┌─────────────┐                    ┌─────────────────┐
│ training.py │ ──► 5 models       │ MLflow Registry │
└─────────────┘     + metrics      └─────────────────┘
      │                                      ▲
      ▼                                      │
┌─────────────┐                              │
│ tuning.py   │ ──► Tuned model    ─────────┤
└─────────────┘     + metrics                │
      │                                      │
      ▼                                      │
┌─────────────────┐                          │
│ evaluation.py   │ ──► Test metrics ────────┤
└─────────────────┘     CV metrics           │
      │                                      │
      ▼                                      │
┌─────────────┐                              │
│ registry.py │ ──► Staging/Production ──────┘
└─────────────┘
```

## Module Dependencies

```
main.py
  ├── config.py
  ├── data_loader.py
  ├── data_preprocessing.py
  │   └── config.py
  ├── feature_engineering.py
  │   └── config.py
  ├── training.py
  │   └── config.py
  ├── evaluation.py
  ├── tuning.py
  │   └── config.py
  └── registry.py
      └── config.py
```

## Task Execution Flow (Prefect)

```
@flow: nyc_taxi_ml_pipeline
  │
  ├─ @task: setup_mlflow()
  │
  ├─ @task: download_dataset()
  ├─ @task: load_data_chunks()
  │
  ├─ @task: clean_data()
  ├─ @task: validate_no_leakage()
  ├─ @task: split_data()
  │
  ├─ @task: build_preprocessing_pipeline()
  ├─ @task: fit_transform_pipeline()
  │
  ├─ @task: train_all_models()
  │   ├─ @task: train_single_model()  [x5 - concurrent]
  │   └─ @task: select_best_model()
  │
  ├─ @task: tune_best_model() [optional]
  │   ├─ @task: tune_model()
  │   └─ @task: compare_tuning_results()
  │
  ├─ @task: evaluate_on_test_set()
  ├─ @task: cross_validate_model()
  ├─ @task: generate_evaluation_report()
  │
  ├─ @task: tag_best_model()
  ├─ @task: promote_to_staging()
  ├─ @task: promote_to_production() [optional]
  └─ @task: display_registry_status()
```

## Data Leakage Prevention Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                    TIME BOUNDARY                                 │
│                                                                  │
│  Pickup Time          ║          Dropoff Time                   │
│  (Features Available) ║  (Target + Leakage Features)            │
│                       ║                                          │
│  ✅ pickup_datetime   ║  ❌ dropoff_datetime                    │
│  ✅ pickup_location   ║  ❌ fare_amount                          │
│  ✅ dropoff_location  ║  ❌ tip_amount                           │
│  ✅ passenger_count   ║  ❌ total_amount                         │
│  ✅ trip_distance     ║  ✅ trip_duration (TARGET)               │
│  ✅ vendor_id         ║                                          │
│  ✅ rate_code         ║                                          │
│  ✅ payment_type      ║                                          │
│                       ║                                          │
└───────────────────────╨──────────────────────────────────────────┘
                        │
                        │  SPLIT BEFORE ENGINEERING
                        │
                   Train │ Val │ Test
                    64%  │ 16% │ 20%
```

## MLflow Model Registry Workflow

```
┌──────────────┐
│  Training    │
│  Complete    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Auto-Register│──► Version 1, 2, 3, ...
│   (None)     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Promote    │
│  to Staging  │──► Version X (best model)
└──────┬───────┘
       │
       │ [Manual or Auto]
       ▼
┌──────────────┐
│   Promote    │
│to Production │──► Version X (deployed)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Archive Old │
│  Production  │──► Old versions archived
└──────────────┘
```

## Technology Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    TECHNOLOGY LAYERS                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Orchestration Layer          │  Prefect 2.x                │
├─────────────────────────────────────────────────────────────┤
│  Experiment Tracking          │  MLflow 2.x                 │
├─────────────────────────────────────────────────────────────┤
│  ML Framework                 │  Scikit-learn 1.3+          │
├─────────────────────────────────────────────────────────────┤
│  Data Processing              │  Pandas, NumPy              │
├─────────────────────────────────────────────────────────────┤
│  Data Source                  │  Kagglehub                  │
├─────────────────────────────────────────────────────────────┤
│  Storage                      │  SQLite (MLflow backend)    │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Principles

1. **Modularity**: Each stage is a separate module
2. **Reproducibility**: Random seeds, version control
3. **Observability**: Comprehensive logging with Prefect + MLflow
4. **Scalability**: Task-based architecture, concurrent execution
5. **Data Integrity**: No leakage, proper splitting
6. **Production Ready**: Model registry, stage transitions
7. **Maintainability**: Clear structure, documentation

## Performance Optimization

- ✅ **Chunk-based data loading**: Memory efficient
- ✅ **HalvingRandomSearchCV**: 5x faster than GridSearch
- ✅ **Concurrent task execution**: Prefect task runner
- ✅ **Efficient feature engineering**: Vectorized operations
- ✅ **Early stopping**: Skip unnecessary computations
- ✅ **Smart sampling**: Default 200k samples for speed

## Future Architecture Enhancements

```
Current State                    Future State
─────────────                    ────────────

Local Python           ──►       Docker Container
SQLite Database        ──►       PostgreSQL/MySQL
Manual Deployment      ──►       CI/CD Pipeline
Single Machine         ──►       Distributed Computing (Dask)
No API                 ──►       FastAPI REST Service
No Monitoring          ──►       Prometheus + Grafana
Static Features        ──►       Feature Store (Feast)
```

---

This architecture provides a solid foundation for an educational ML pipeline that can progressively grow into a production system! 🚀