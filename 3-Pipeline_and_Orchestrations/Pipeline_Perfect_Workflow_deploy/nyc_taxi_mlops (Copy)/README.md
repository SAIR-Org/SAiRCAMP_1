# 🚖 NYC Taxi Trip Duration Prediction - Production ML Pipeline

A production-ready machine learning pipeline for predicting NYC taxi trip durations with comprehensive MLflow integration, automated logging, and retry mechanisms.

## 🎯 Features

- ✅ **Modular Architecture** - Clean separation of concerns with reusable components
- ✅ **MLflow Integration** - Complete experiment tracking, model registry, and versioning
- ✅ **SQLite Backend** - Single-file database for easy deployment
- ✅ **Comprehensive Logging** - Structured logging to both console and file
- ✅ **Retry Mechanisms** - Automatic retry with exponential backoff for transient failures
- ✅ **CLI Interface** - Full argparse support for configuration
- ✅ **Data Leakage Prevention** - Only prediction-time features used
- ✅ **Production Ready** - Model deployment packages with metadata

## 📁 Project Structure

```
nyc_taxi_mlops/
├── main.py                      # CLI entry point
├── requirements.txt             # Python dependencies
├── README.md                    # This file
│
├── config/
│   ├── __init__.py
│   └── config.py                # Centralized configuration
│
├── src/
│   ├── __init__.py
│   ├── pipeline.py              # Main pipeline orchestrator
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── data_acquisition.py # Kaggle data download
│   │   └── data_preprocessing.py # Data cleaning & validation
│   │
│   ├── features/
│   │   ├── __init__.py
│   │   └── feature_engineering.py # Feature transformers
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── model_training.py    # Training & MLflow tracking
│   │   ├── model_registry.py    # Model registry operations
│   │   └── model_deployment.py  # Deployment artifacts
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logging_utils.py     # Logging setup
│       └── retry_utils.py       # Retry decorators
│
├── models/                      # Saved model artifacts
├── data/                        # Data cache
└── logs/                        # Pipeline logs
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Pipeline with Default Configuration

```bash
python main.py
```

### 3. View MLflow UI

```bash
# In a separate terminal
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db --host 127.0.0.1 --port 5000
```

Open browser: http://127.0.0.1:5000

## 📋 CLI Usage

### Basic Usage

```bash
# Run with defaults
python main.py

# Run with specific sample size
python main.py --sample-size 100000

# Run with specific models only
python main.py --models "Random Forest" "Gradient Boosting"

# Skip tuning for faster execution
python main.py --skip-tuning

# Dry run to validate configuration
python main.py --dry-run
```

### Advanced Usage

```bash
# Custom configuration
python main.py \
  --sample-size 200000 \
  --random-state 42 \
  --test-size 0.2 \
  --val-size 0.2 \
  --cv-folds 5 \
  --models "Random Forest" "Gradient Boosting" \
  --experiment-name "my_experiment" \
  --model-name "my_model" \
  --log-level DEBUG

# Run specific steps only
python main.py --steps 1 2 3  # Only data acquisition, preprocessing, and splitting

# Custom paths
python main.py \
  --model-dir /path/to/models \
  --data-dir /path/to/data \
  --log-dir /path/to/logs
```

### CLI Arguments

#### Data Configuration
- `--sample-size`: Number of samples (default: 200000)
- `--chunk-size`: CSV chunk size (default: 500000)
- `--num-chunks`: Number of chunks to load (default: 2)

#### Model Configuration
- `--random-state`: Random seed (default: 42)
- `--test-size`: Test set fraction (default: 0.2)
- `--val-size`: Validation set fraction (default: 0.2)
- `--cv-folds`: Cross-validation folds (default: 5)
- `--models`: Models to train (default: all)
- `--skip-tuning`: Skip hyperparameter tuning
- `--skip-cv`: Skip cross-validation

#### MLflow Configuration
- `--experiment-name`: MLflow experiment name
- `--model-name`: Registered model name

#### Logging Configuration
- `--log-level`: Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- `--log-file`: Log file name

#### Retry Configuration
- `--max-retries`: Maximum retry attempts (default: 3)
- `--retry-delay`: Initial retry delay in seconds (default: 5)

## 🏗️ Pipeline Steps

The pipeline consists of 10 steps:

1. **Data Acquisition** - Download NYC taxi data from Kaggle
2. **Data Preprocessing** - Clean and validate data
3. **Data Splitting** - Split into train/val/test sets (before feature engineering!)
4. **Feature Engineering** - Create engineered features and preprocessing pipeline
5. **Model Training** - Train all models with MLflow tracking
6. **Model Tuning** - Hyperparameter tuning with HalvingRandomSearchCV
7. **Cross-Validation** - Validate best model with k-fold CV
8. **Test Evaluation** - Final evaluation on held-out test set
9. **Model Registry** - Register model and transition to staging
10. **Save Deployment** - Create deployment package with artifacts

## 🔧 Configuration

### Environment Variables

Override configuration with environment variables:

```bash
export RANDOM_STATE=42
export SAMPLE_SIZE=100000
export MLFLOW_EXPERIMENT_NAME="my_experiment"

python main.py
```

### Programmatic Configuration

```python
from config.config import Config

# Create custom config
config = Config()
config.data.sample_size = 100000
config.model.random_state = 42

# Run pipeline
from src.pipeline import NYCTaxiMLPipeline
pipeline = NYCTaxiMLPipeline(config)
pipeline.run()
```

## 📊 MLflow Integration

### Experiment Tracking

Every run automatically logs:
- **Parameters**: Model hyperparameters, data split sizes
- **Metrics**: R², RMSE, MAE for train/val/test sets
- **Tags**: Model family, data leakage status, optimization level
- **Artifacts**: Trained models with signatures

### Model Registry

Models are automatically registered with:
- **Version Control**: Auto-incrementing versions
- **Stage Management**: None → Staging → Production → Archived
- **Metadata**: Performance metrics, feature info, timestamps
- **Lineage**: Full traceability from training to deployment

### Loading Models

```python
import mlflow

# Load from registry by stage
model = mlflow.sklearn.load_model("models:/nyc_taxi_predictor/Production")

# Load specific version
model = mlflow.sklearn.load_modelchmod +x setup.sh main.py("models:/nyc_taxi_predictor/3")

# Load from run ID
model = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
```

## 🔄 Retry Mechanismschmod +x setup.sh main.py

Automatic retry with exponential backoff for:
- Data download failures (network issues)
- Data loading errors (file corruption)
- Model training failures (transient errors)
- MLflow API calls (connection issues)

Configuration:
- Max retries: 3 (configurable)
- Initial delay: 5 seconds (configurable)
- Exponential backoff with 2x multiplier

## 📝 Logging

### Log Levels

- **DEBUG**: Detailed diagnostic information
- **INFO**: Confirmation that things are working (default)
- **WARNING**: Indication something unexpected happened
- **ERROR**: Serious problem, function couldn't complete
- **CRITICAL**: Program may be unable to continue

### Log Files

Logs are written to both:
- **Console**: INFO level and above
- **File**: DEBUG level and above (rotated at 10MB, 5 backups)

### Log Location

```
logs/
└── pipeline.log         # Current log
└── pipeline.log.1       # Previous log
└── pipeline.log.2       # Older log
...
```

## 📦 Deployment Package

Each trained model generates a deployment package:

```
models/nyc_taxi_{model}_{timestamp}/
├── model.pkl           # Trained model
├── preprocessor.pkl    # Fitted preprocessing pipeline
├── model_card.json     # Complete metadata
└── README.md          # Usage instructions
```

### Using Deployment Package

```python
import joblib
import pandas as pd

# Load model and preprocessor
model = joblib.load('models/nyc_taxi_random_forest_20240115_120000/model.pkl')
preprocessor = joblib.load('models/nyc_taxi_random_forest_20240115_120000/preprocessor.pkl')

# Prepare input
input_data = pd.DataFrame({
    'tpep_pickup_datetime': ['2016-01-01 12:00:00'],
    'pickup_longitude': [-73.98],
    'pickup_latitude': [40.75],
    'dropoff_longitude': [-73.95],
    'dropoff_latitude': [40.78],
    'passenger_count': [1],
    'VendorID': [2],
    'RatecodeID': [1],
    'trip_distance': [3.5],
    'payment_type': [1]
})

# Predict
input_processed = preprocessor.transform(input_data)
prediction = model.predict(input_processed)
print(f"Predicted trip duration: {prediction[0]:.2f} minutes")
```

## 🛡️ Data Leakage Prevention

The pipeline strictly prevents data leakage:

### ✅ Prediction-Time Features (Used)
- Temporal: Pickup datetime
- Geographic: Pickup/dropoff coordinates
- Trip metadata: Passenger count, vendor ID, payment type
- Distance: Trip distance (known at pickup from route planning)

### 🚫 Post-Trip Features (Excluded)
- Financial: Fare amount, tip amount, total amount
- Trip outcome: Dropoff datetime (contains target!)
- Additional charges: Tolls, MTA tax, surcharge

### Pipeline Guarantees
1. **Early Splitting**: Data split BEFORE feature engineering
2. **Fitted on Training**: All transformers fitted only on training data
3. **No Future Data**: Only information available at pickup time

## 🧪 Testing

### Validate Pipeline

```bash
# Dry run
python main.py --dry-run

# Small sample test
python main.py --sample-size 10000 --skip-tuning --skip-cv

# Single model test
python main.py --models "Linear Regression" --sample-size 50000
```

### Run Specific Steps

```bash
# Test data acquisition only
python main.py --steps 1

# Test data acquisition and preprocessing
python main.py --steps 1 2

# Test training without tuning
python main.py --steps 1 2 3 4 5 8
```

## 📈 Performance

### Optimization Features
- **Fast Training**: No CV during initial model comparison (7x faster)
- **HalvingRandomSearchCV**: Progressive resource allocation for tuning
- **Selective Tuning**: Only tune best-performing model
- **Efficient Preprocessing**: Vectorized operations with NumPy

### Expected Performance
- **Training Time**: 2-4 minutes (200K samples, 5 models, tuning enabled)
- **Test R²**: ~0.75-0.85 (depends on data and model)
- **Test MAE**: ~3-5 minutes

## 🔍 Troubleshooting

### Kaggle API Issues

```bash
# Set up Kaggle credentials
mkdir -p ~/.kaggle
# Download kaggle.json from https://www.kaggle.com/settings
cp kaggle.json ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json
```

### MLflow Database Lock

```bash
# Stop any running MLflow UI instances
pkill -f "mlflow ui"

# Remove database lock
rm -f mlflow_nyc_taxi.db-shm mlflow_nyc_taxi.db-wal
```

### Memory Issues

```bash
# Reduce sample size
python main.py --sample-size 50000

# Reduce chunk size
python main.py --chunk-size 250000 --num-chunks 1
```

### Import Errors

```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Verify installation
python -c "import mlflow; import sklearn; import pandas; print('All imports OK')"
```

## 🤝 Contributing

This is a production-ready template. To extend:

1. Add new models in `src/models/model_training.py`
2. Add new features in `src/features/feature_engineering.py`
3. Add new data sources in `src/data/data_acquisition.py`
4. Add new metrics in model evaluation methods

## 📄 License

This project is provided as-is for educational and production use.

## 🙏 Acknowledgments

- NYC Taxi & Limousine Commission for the dataset
- Kaggle for hosting the data
- MLflow for experiment tracking
- Scikit-learn for ML algorithms

---

**Ready for Production** | **MLflow Integrated** | **Fully Automated** | **7x Faster**