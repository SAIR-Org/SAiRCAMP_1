# 🚖 NYC Taxi ML Pipeline - Production Ready

A production-grade machine learning pipeline for predicting NYC Yellow Taxi trip durations, orchestrated with **Prefect** and tracked with **MLflow**.

## 📋 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Pipeline Stages](#pipeline-stages)
- [Configuration](#configuration)
- [MLflow Integration](#mlflow-integration)
- [Advanced Usage](#advanced-usage)

## ✨ Features

### Core Features
- ✅ **Zero Data Leakage**: Strict separation of training/validation/test sets
- ✅ **Prefect Orchestration**: Modular, resumable, and monitorable workflow
- ✅ **MLflow Tracking**: Complete experiment tracking and model registry
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
├── main.py                  # Main Prefect flow (run this!)
├── requirements.txt         # Python dependencies
├── README.md               # This file
│
├── config/
│   └── config.py           # Centralized configuration
│
├── src/
│   ├── data_loader.py      # Data loading from Kaggle
│   ├── data_preprocessing.py   # Cleaning and splitting
│   ├── feature_engineering.py  # Custom transformers
│   ├── training.py         # Model training logic
│   ├── evaluation.py       # Model evaluation
│   ├── tuning.py          # Hyperparameter tuning
│   └── registry.py        # MLflow registry operations
│
├── data/                   # Data directory (created automatically)
├── models/                 # Model artifacts (created automatically)
├── logs/                   # Log files (created automatically)
└── mlflow_nyc_taxi.db     # MLflow SQLite database (created automatically)
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
```

### Run with Custom Settings

```python
from main import nyc_taxi_ml_pipeline

# Run pipeline
result = nyc_taxi_ml_pipeline(
    sample_size=200000,      # Number of samples
    tune_model=True,         # Enable hyperparameter tuning
    promote_to_prod=False    # Auto-promote to production
)
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

- [ ] **Docker**: Containerize the pipeline
- [ ] **FastAPI**: REST API for model serving  
- [ ] **Monitoring**: Data drift, model performance monitoring
- [ ] **CI/CD**: Automated testing and deployment
- [ ] **Feature Store**: Centralized feature management
- [ ] **A/B Testing**: Champion/challenger deployment

## 📄 License

MIT License - Feel free to use for educational purposes

## 🙏 Acknowledgments

- NYC TLC for the taxi dataset
- Prefect for workflow orchestration
- MLflow for experiment tracking
- Scikit-learn for ML algorithms

---

**Ready to run?** Just execute:
```bash
python main.py
```

Happy modeling! 🚀