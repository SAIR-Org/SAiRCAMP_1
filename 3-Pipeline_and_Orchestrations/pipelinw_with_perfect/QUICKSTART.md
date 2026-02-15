# 🚀 QUICKSTART GUIDE

Get the NYC Taxi ML Pipeline running in 5 minutes!

## Step 1: Setup Environment (2 minutes)

```bash
# Navigate to project directory
cd nyc_taxi_ml_pipeline

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Configure Kaggle API (1 minute)

**Option A: Using kaggle.json**
```bash
# Download kaggle.json from Kaggle → Account → API → Create New Token
# Place it in ~/.kaggle/kaggle.json
mkdir -p ~/.kaggle
mv ~/Downloads/kaggle.json ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json
```

**Option B: Using environment variables**
```bash
export KAGGLE_USERNAME=your_username
export KAGGLE_KEY=your_api_key
```

## Step 3: Validate Setup (30 seconds)

```bash
python validate_setup.py
```

You should see:
```
🎉 ALL TESTS PASSED!

You're ready to run the pipeline:
   python main.py
```

## Step 4: Run the Pipeline (2-5 minutes)

```bash
python main.py
```

Watch the magic happen! You'll see:
- 📥 Data downloading
- 🧹 Data cleaning
- ⚙️ Feature engineering
- 🎯 Model training (5 models)
- 🔧 Hyperparameter tuning
- 🔬 Model evaluation
- 🏛️ Model registry

## Step 5: View Results (Optional)

**MLflow UI:**
```bash
# In a new terminal
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db --host 127.0.0.1 --port 5000

# Open: http://127.0.0.1:5000
```

**Prefect UI (Optional):**
```bash
# Start Prefect server
prefect server start

# Open: http://127.0.0.1:4200
```

## 📊 Expected Output

```
✅ PIPELINE EXECUTION COMPLETE
═══════════════════════════════════════════════════════════════════

🏆 BEST MODEL: Random Forest
   • Run ID: abc12345...
   • Val R²: 0.8234
   • Test R²: 0.8156
   • Test MAE: 2.43 minutes

📦 MODEL REGISTRY:
   • Model: nyc_taxi_predictor
   • Version: 3
   • Stage: Staging

🔗 Load model:
   model = mlflow.sklearn.load_model('models:/nyc_taxi_predictor/Staging')

🎉 SUCCESS!
═══════════════════════════════════════════════════════════════════
```

## 🎯 What Happened?

1. ✅ **Downloaded** 1M+ taxi trips from Kaggle
2. ✅ **Cleaned** data (removed outliers, invalid coordinates)
3. ✅ **Engineered** 30+ features (distance, temporal, airport, etc.)
4. ✅ **Trained** 5 models (Linear, Ridge, Lasso, RF, GB)
5. ✅ **Tuned** the best model (HalvingRandomSearch)
6. ✅ **Evaluated** on test set (R² ~0.80-0.85)
7. ✅ **Registered** model in MLflow (Staging stage)

## 🔍 Explore the Results

### Load and Use the Model

```python
import mlflow.sklearn
import pandas as pd

# Load the best model
model = mlflow.sklearn.load_model('models:/nyc_taxi_predictor/Staging')

# Make predictions (you'll need to preprocess first!)
# predictions = model.predict(X_processed)
```

### Check MLflow Experiments

```python
import mlflow
from mlflow import MlflowClient

mlflow.set_tracking_uri('sqlite:///mlflow_nyc_taxi.db')
client = MlflowClient()

# Get all runs
runs = client.search_runs(experiment_ids=['0'])
for run in runs:
    print(f"Run: {run.info.run_name}")
    print(f"  Val R²: {run.data.metrics.get('val_r2', 'N/A')}")
    print(f"  Test R²: {run.data.metrics.get('test_r2', 'N/A')}")
```

## ⚙️ Customize the Pipeline

### Change Sample Size

```python
# In main.py
result = nyc_taxi_ml_pipeline(
    sample_size=100000,  # Smaller for faster testing
    tune_model=True,
    promote_to_prod=False
)
```

### Skip Hyperparameter Tuning

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
    promote_to_prod=True  # Automatically promote to Production
)
```

## 🚨 Troubleshooting

### "Kaggle API credentials not found"
- Make sure `kaggle.json` is in `~/.kaggle/`
- Or set environment variables: `KAGGLE_USERNAME` and `KAGGLE_KEY`

### "Module not found"
```bash
pip install -r requirements.txt
```

### "MLflow database is locked"
```bash
# Kill any running MLflow UI
pkill -f "mlflow ui"
```

### Out of memory
```python
# Reduce sample size
result = nyc_taxi_ml_pipeline(sample_size=50000)
```

## 📚 Next Steps

1. **Read the full README.md** for detailed documentation
2. **Explore `src/` modules** to understand each component
3. **Customize `config/config.py`** for your needs
4. **Add more models** in `src/training.py`
5. **Deploy the model** (see README for future enhancements)

## 🎓 Learning Path

This pipeline demonstrates:
- ✅ **Prefect**: Workflow orchestration
- ✅ **MLflow**: Experiment tracking & model registry
- ✅ **Scikit-learn**: ML algorithms & pipelines
- ✅ **Production practices**: Modular code, no leakage, proper evaluation

**Ready for the next level?**
- Add Docker containerization
- Build a FastAPI service
- Implement monitoring
- Set up CI/CD

---

**Questions? Issues?**

Check the full README.md or inspect the code in `src/` modules.

Happy learning! 🚀