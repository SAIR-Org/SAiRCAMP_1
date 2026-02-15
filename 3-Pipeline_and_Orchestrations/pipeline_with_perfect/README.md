# 🚖 NYC Taxi ML Pipeline - Production Ready

A production-grade machine learning pipeline for predicting NYC Yellow Taxi trip durations, orchestrated with **Prefect** and tracked with **MLflow**.

## 📋 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Command-Line Usage](#command-line-usage)
- [Pipeline Stages](#pipeline-stages)
- [Configuration](#configuration)
- [MLflow Integration](#mlflow-integration)
- [Advanced Usage](#advanced-usage)
- [Production Patterns](#production-patterns)

## ✨ Features

### Core Features
- ✅ **Zero Data Leakage**: Strict separation of training/validation/test sets
- ✅ **Prefect Orchestration**: Modular, resumable, and monitorable workflow
- ✅ **MLflow Tracking**: Complete experiment tracking and model registry
- ✅ **Command-Line Parameterization**: Run with different configs (like Prefect's pattern)
- ✅ **Production Ready**: Clean, modular, and well-documented code
- ✅ **Fast Training**: Optimized with HalvingRandomSearchCV

### ML Best Practices
- 🔒 **Data Leakage Prevention**: Only uses features available at pickup time
- 🎯 **Proper Data Splitting**: Split BEFORE feature engineering
- ⚖️ **Robust Preprocessing**: IQR-based outlier handling + RobustScaler
- 🔧 **Smart Feature Engineering**: 30+ engineered features (temporal, geographic, interactions)
- 📊 **Model Registry**: Staging → Production workflow with MLflow

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PREFECT ORCHESTRATION                     │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │  Stage  │          │  Stage  │          │  Stage  │
   │    1    │   ───>   │    2    │   ───>   │   ...   │
   │ MLflow  │          │  Data   │          │  Model  │
   │  Setup  │          │ Loading │          │Training │
   └─────────┘          └─────────┘          └─────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────────────┐
│                    MLFLOW TRACKING                           │
│  • Experiments  • Metrics  • Models  • Model Registry        │
└──────────────────────────────────────────────────────────────┘
```

### Pipeline Stages

1. **MLflow Setup** - Initialize tracking and experiment
2. **Data Loading** - Download and load data from Kaggle
3. **Data Preprocessing** - Clean, validate, and split data
4. **Feature Engineering** - Create 30+ engineered features
5. **Model Training** - Train 5 models, select best
6. **Hyperparameter Tuning** - Optimize best model (optional)
7. **Model Evaluation** - Test set evaluation + cross-validation
8. **Model Registry** - Promote to Staging/Production

## 📁 Project Structure

```
nyc_taxi_ml_pipeline/
│
├── main.py                      # Main Prefect flow with CLI args
├── main_advanced.py             # Advanced version (year/month params)
├── validate_setup.py            # Setup validation script
├── requirements.txt             # Python dependencies
│
├── README.md                    # This file
├── QUICKSTART.md               # 5-minute quick start guide
├── ARCHITECTURE.md             # Architecture documentation
├── PARAMETERIZATION_GUIDE.md   # CLI parameterization guide
├── PROJECT_SUMMARY.md          # Project overview
├── QUICKFIX.md                 # Common fixes
│
├── config/
│   └── config.py               # Centralized configuration
│
├── src/
│   ├── data_loader.py          # Data loading from Kaggle
│   ├── data_preprocessing.py   # Cleaning and splitting
│   ├── feature_engineering.py  # Custom transformers
│   ├── training.py             # Model training logic
│   ├── evaluation.py           # Model evaluation
│   ├── tuning.py              # Hyperparameter tuning
│   └── registry.py            # MLflow registry operations
│
├── data/                       # Data directory (created automatically)
├── models/                     # Model artifacts (created automatically)
├── logs/                       # Log files (created automatically)
└── mlflow_nyc_taxi.db         # MLflow SQLite database (created automatically)
```

## 🚀 Installation

### Prerequisites
- Python 3.8+
- pip

### Setup

```bash
# 1. Clone or download this project
cd nyc_taxi_ml_pipeline

# 2. Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure Kaggle API (for data download)
# Place your kaggle.json in ~/.kaggle/ or set KAGGLE_USERNAME and KAGGLE_KEY
```

## ⚡ Quick Start

### Run the Complete Pipeline

```bash
# Run with default settings
python main.py

# Quick test with smaller sample
python main.py --sample-size 50000 --no-tune

# Full run with tuning and auto-promotion
python main.py --sample-size 200000 --tune --promote
```

### View MLflow UI

```bash
# In a separate terminal
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db --host 127.0.0.1 --port 5000

# Open browser at: http://127.0.0.1:5000
```

### View Prefect UI (Optional)

```bash
# Start Prefect server
prefect server start

# Open browser at: http://127.0.0.1:4200
```

## 🎯 Command-Line Usage

The pipeline supports **parameterization** like Prefect's `week3_duration-prediction.py` pattern:

### Basic Usage (main.py)

```bash
# Show all options
python main.py --help

# Run with custom sample size
python main.py --sample-size 100000

# Disable tuning for faster runs
python main.py --no-tune

# Auto-promote to production
python main.py --tune --promote

# Custom experiment name
python main.py --experiment-name "quick_test"

# Custom run name
python main.py --run-name "baseline_model"
```

### Advanced Usage (main_advanced.py)

Process specific year/month data (Prefect pattern):

```bash
# Process specific month
python main_advanced.py --year 2023 --month 1

# Process with tuning
python main_advanced.py --year 2023 --month 2 --tune

# Auto-promote to production
python main_advanced.py --year 2023 --month 3 --tune --promote

# Batch process multiple months
for month in {1..12}; do
    python main_advanced.py --year 2023 --month $month
done
```

### Available Arguments

**main.py:**
```
--sample-size INT        Number of samples (default: 200000)
--tune / --no-tune       Enable/disable tuning (default: tune)
--promote                Auto-promote to production
--experiment-name STR    Custom MLflow experiment name
--run-name STR          Custom run name
--data-year INT         Year of data (default: 2016)
--data-month INT        Month of data (default: 1)
--debug                 Enable debug mode
--skip-download         Skip data download
```

**main_advanced.py:**
```
--year INT              Year of data to process (default: 2016)
--month INT             Month of data (1-12, default: 1)
--sample-size INT       Number of samples (default: 200000)
--tune / --no-tune      Enable/disable tuning
--promote               Auto-promote to production
--experiment-suffix STR Suffix for experiment name
```

### Common Workflows

```bash
# 1. Quick test (fast)
python main.py --sample-size 50000 --no-tune

# 2. Full training run
python main.py --sample-size 200000 --tune

# 3. Production deployment
python main.py --tune --promote

# 4. Monthly training (Prefect pattern)
python main_advanced.py --year 2023 --month 1 --tune

# 5. A/B testing different configs
python main.py --sample-size 100000 --run-name "config_A"
python main.py --sample-size 200000 --run-name "config_B"
```

See **PARAMETERIZATION_GUIDE.md** for detailed examples and production patterns.

## 📊 Pipeline Stages

### Stage 1: MLflow Setup
- Initialize MLflow tracking URI
- Create/set experiment
- Configure experiment tags

### Stage 2: Data Loading
- Download NYC Yellow Taxi dataset from Kaggle
- Load data in chunks (efficient memory usage)
- Sample data if needed

### Stage 3: Data Preprocessing
- **Clean data**: Filter unrealistic values
  - Trip duration: 1-120 minutes
  - Trip distance: 0.1-50 miles
  - NYC coordinates only
  - Passenger count: 1-6
- **Validate no leakage**: Ensure only pickup-time features
- **Split data**: Train (64%) / Val (16%) / Test (20%)

### Stage 4: Feature Engineering
- **Distance features**: Haversine, Manhattan, direction
- **Temporal features**: Hour, day of week, month (with cyclical encoding)
- **Time flags**: Rush hour, weekend
- **Airport features**: Distance to JFK/LGA
- **Efficiency metrics**: Distance per passenger, efficiency ratio
- **Interaction features**: Distance × passengers, etc.
- **Total**: 30+ engineered features

### Stage 5: Model Training
Train 5 models:
1. Linear Regression (baseline)
2. Ridge Regression
3. Lasso Regression
4. Random Forest
5. Gradient Boosting

Each model is:
- Trained on processed features
- Evaluated on validation set
- Logged to MLflow with metrics and parameters
- Auto-registered in MLflow Model Registry

### Stage 6: Hyperparameter Tuning (Optional)
- Uses **HalvingRandomSearchCV** (much faster than GridSearch)
- Only tunes the best model (RF or GB)
- Logs tuning results to MLflow
- Compares tuned vs original model

### Stage 7: Model Evaluation
- **Test set evaluation**: Final R², RMSE, MAE
- **Cross-validation**: 3-fold CV on training set
- **Comprehensive report**: All metrics in one place
- Logs all metrics to MLflow

### Stage 8: Model Registry
- Tag best model run
- Promote to **Staging** stage
- Optional: Auto-promote to **Production**
- Display registry status

## ⚙️ Configuration

Edit `config/config.py` to customize:

```python
# Data filtering
SAMPLE_SIZE = 200000
MIN_TRIP_DURATION = 60  # seconds
MAX_TRIP_DURATION = 7200

# Model hyperparameters
RF_N_ESTIMATORS = 100
RF_MAX_DEPTH = 20
GB_LEARNING_RATE = 0.1

# Tuning config
TUNING_N_CANDIDATES = 6
TUNING_FACTOR = 3
```

## 📈 MLflow Integration

### Tracking

Every run logs:
- **Parameters**: All model hyperparameters
- **Metrics**: Train/val/test R², RMSE, MAE, training time
- **Tags**: Model family, data leakage status, optimization method
- **Model**: Serialized model with signature
- **Artifacts**: Model files, preprocessor

### Model Registry

Models are automatically registered with:
- **Name**: `nyc_taxi_predictor`
- **Versions**: Auto-incremented
- **Stages**: None → Staging → Production → Archived
- **Metadata**: Algorithm, metrics, descriptions, tags

### Loading Models

```python
import mlflow.sklearn

# Load production model
model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/Production")

# Load staging model
model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/Staging")

# Load specific version
model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/3")
```

## 🎯 Advanced Usage

### Run Specific Stages

```python
from src.data_loader import download_dataset, load_data_chunks
from src.data_preprocessing import clean_data

# Just load and clean data
dataset_path = download_dataset()
df = load_data_chunks(dataset_path, sample_size=100000)
df_clean = clean_data(df)
```

### Custom Model Portfolio

Edit `src/training.py`:

```python
def get_model_portfolio():
    return {
        'My Custom Model': MyCustomRegressor(),
        'Random Forest': RandomForestRegressor(...)
    }
```

### Skip Tuning

```python
result = nyc_taxi_ml_pipeline(
    sample_size=200000,
    tune_model=False,  # Skip tuning
    promote_to_prod=False
)
```

### Auto-Promote to Production

```python
result = nyc_taxi_ml_pipeline(
    sample_size=200000,
    tune_model=True,
    promote_to_prod=True  # Auto-promote best model
)
```

## 📊 Expected Results

With default settings:

- **Best Model**: Random Forest or Gradient Boosting
- **Test R²**: ~0.80-0.85 (80-85% variance explained)
- **Test MAE**: ~2-3 minutes (average error)
- **Training Time**: 2-5 minutes total

## 🔍 Monitoring

### Prefect Dashboard
- Flow runs and status
- Task execution times
- Retry attempts
- Logs and artifacts

### MLflow UI
- Experiment comparison
- Metric visualization
- Model lineage
- Registry status

## 🏭 Production Patterns

### Scheduled Monthly Training

Create a script to process data monthly:

```bash
#!/bin/bash
# train_monthly.sh

YEAR=$(date +%Y)
MONTH=$(date +%m)

python main_advanced.py \
    --year $YEAR \
    --month $MONTH \
    --sample-size 200000 \
    --tune \
    --promote
```

Schedule with cron:
```bash
# Run on the 1st of every month at 2 AM
0 2 1 * * cd /path/to/pipeline && ./train_monthly.sh
```

### Batch Processing Multiple Periods

```bash
# Process all months of 2023
for month in {1..12}; do
    echo "Processing 2023-${month}"
    python main_advanced.py \
        --year 2023 \
        --month $month \
        --tune \
        --experiment-suffix "2023_monthly"
done
```

### A/B Testing Different Configurations

```bash
# Test different sample sizes
for size in 50000 100000 200000; do
    python main.py \
        --sample-size $size \
        --tune \
        --run-name "sample_${size}"
done

# Compare results in MLflow UI
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db
```

### CI/CD Integration

**GitHub Actions example:**

```yaml
# .github/workflows/train.yml
name: Train Monthly Model

on:
  schedule:
    - cron: '0 2 1 * *'  # 1st of each month at 2 AM
  workflow_dispatch:      # Manual trigger

jobs:
  train:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run training pipeline
        env:
          KAGGLE_USERNAME: ${{ secrets.KAGGLE_USERNAME }}
          KAGGLE_KEY: ${{ secrets.KAGGLE_KEY }}
        run: |
          python main_advanced.py \
            --year $(date +%Y) \
            --month $(date +%m) \
            --tune \
            --promote
      
      - name: Upload MLflow artifacts
        uses: actions/upload-artifact@v3
        with:
          name: mlflow-db
          path: mlflow_nyc_taxi.db
```

### Prefect Deployments

```bash
# Create deployment for monthly training
prefect deployment build main_advanced.py:nyc_taxi_ml_pipeline_advanced \
    -n "monthly-training" \
    -p default-agent-pool \
    --cron "0 2 1 * *"

# Apply deployment
prefect deployment apply nyc_taxi_ml_pipeline_advanced-deployment.yaml

# Start agent to run deployments
prefect agent start -p default-agent-pool
```

### Monitoring with MLflow

Track all runs and compare:

```python
import mlflow
from mlflow import MlflowClient

# Connect to tracking server
mlflow.set_tracking_uri('sqlite:///mlflow_nyc_taxi.db')
client = MlflowClient()

# Get all runs from experiment
experiment = client.get_experiment_by_name('nyc_taxi_production_pipeline')
runs = client.search_runs(experiment_ids=[experiment.experiment_id])

# Compare performance across months
for run in runs:
    period = run.data.tags.get('data_period', 'N/A')
    test_r2 = run.data.metrics.get('test_r2', 0)
    print(f"{period}: R² = {test_r2:.4f}")
```

## 🚨 Troubleshooting

### Kaggle API Error
```bash
# Set credentials
export KAGGLE_USERNAME=your_username
export KAGGLE_KEY=your_api_key
```

### MLflow Database Locked
```bash
# Stop any running MLflow UI instances
pkill -f "mlflow ui"

# Restart
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db
```

### Memory Issues
```python
# Reduce sample size
result = nyc_taxi_ml_pipeline(sample_size=100000)
```

## 📝 Next Steps (Future Enhancements)

The pipeline is designed for progressive enhancement:

- [x] **Prefect Orchestration**: Task-based workflow ✅
- [x] **MLflow Tracking**: Complete experiment tracking ✅
- [x] **Command-Line Parameterization**: Production-ready CLI ✅
- [ ] **Docker**: Containerize the pipeline
- [ ] **FastAPI**: REST API for model serving  
- [ ] **Monitoring**: Data drift, model performance monitoring
- [ ] **CI/CD**: Automated testing and deployment
- [ ] **Feature Store**: Centralized feature management
- [ ] **A/B Testing**: Champion/challenger deployment

## 📚 Additional Documentation

- **QUICKSTART.md** - Get running in 5 minutes
- **PARAMETERIZATION_GUIDE.md** - Complete CLI usage guide
- **ARCHITECTURE.md** - Design decisions and diagrams
- **PROJECT_SUMMARY.md** - Project overview
- **QUICKFIX.md** - Common issues and fixes

## 📄 License

MIT License - Feel free to use for educational purposes

## 🙏 Acknowledgments

- NYC TLC for the taxi dataset
- Prefect for workflow orchestration
- MLflow for experiment tracking
- Scikit-learn for ML algorithms

---

## 🎯 Quick Reference

### Basic Commands
```bash
# Quick test
python main.py --sample-size 50000 --no-tune

# Full training
python main.py --tune

# Production deployment
python main.py --tune --promote
```

### Advanced Commands (Prefect Pattern)
```bash
# Process specific month
python main_advanced.py --year 2023 --month 1 --tune

# Batch processing
for m in {1..3}; do 
    python main_advanced.py --year 2023 --month $m
done
```

### View Results
```bash
# MLflow UI
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db

# Prefect UI
prefect server start
```

---

**Ready to run?** 

```bash
# Validate setup first
python validate_setup.py

# Then run the pipeline
python main.py
```

Happy modeling! 🚀