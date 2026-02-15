# 🚀 Quick Start Guide - NYC Taxi ML Pipeline with Prefect

## ⚡ 5-Minute Setup

### Prerequisites
- Python 3.9+ installed
- Docker & Docker Compose installed (for production)
- Kaggle account and API key

---

## 📋 Option A: Local Development (No Docker)

Perfect for **testing** and **development**.

```bash
# 1. Clone/navigate to project
cd nyc-taxi-mlops

# 2. Setup Kaggle credentials
mkdir -p ~/.kaggle
# Download kaggle.json from https://www.kaggle.com/settings
cp ~/Downloads/kaggle.json ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json

# 3. Run setup script
chmod +x setup_local.sh
./setup_local.sh

# 4. Activate environment
source venv/bin/activate

# 5. Start Prefect server (in NEW terminal)
prefect server start

# 6. Run pipeline
python flows/nyc_taxi_flow.py
```

**That's it!** Open http://localhost:4200 to see Prefect UI.

---

## 🐳 Option B: Docker Production (Recommended)

Perfect for **production** and **scheduled runs**.

```bash
# 1. Clone/navigate to project
cd nyc-taxi-mlops

# 2. Setup Kaggle credentials (same as above)
mkdir -p ~/.kaggle
cp ~/Downloads/kaggle.json ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json

# 3. Run deployment script
chmod +x deploy_docker.sh
./deploy_docker.sh

# 4. Deploy flows
docker-compose exec prefect-agent prefect deploy --all

# 5. Run a deployment
docker-compose exec prefect-agent prefect deployment run \
  'NYC Taxi ML Pipeline/development-testing'
```

**Access UIs:**
- Prefect: http://localhost:4200
- MLflow: http://localhost:5000
- Jupyter: http://localhost:8888

---

## 🎯 What Happens?

The pipeline will:
1. ✅ Download NYC taxi data from Kaggle
2. ✅ Clean and preprocess data
3. ✅ Split into train/val/test sets
4. ✅ Engineer features (distance, time, airport flags)
5. ✅ Train 5 ML models with MLflow tracking
6. ✅ Tune the best model (optional)
7. ✅ Cross-validate (optional)
8. ✅ Evaluate on test set
9. ✅ Register in MLflow Model Registry
10. ✅ Create deployment package

**Expected Duration:** 2-4 minutes (development) | 10-15 minutes (full training)

---

## 📊 Monitoring Execution

### Prefect UI (http://localhost:4200)
- See real-time task execution
- View logs for each task
- Check artifacts and reports
- Monitor resource usage

### MLflow UI (http://localhost:5000)
- Compare model performance
- Track experiments
- View model versions
- Manage staging/production

---

## 🎨 Customizing Runs

### Change Sample Size
```bash
# Local
python flows/nyc_taxi_flow.py --sample-size 50000

# Docker
docker-compose exec prefect-agent prefect deployment run \
  'NYC Taxi ML Pipeline/development-testing' \
  --param sample_size=50000
```

### Skip Expensive Operations
```bash
# Local
python flows/nyc_taxi_flow.py --skip-tuning --skip-cv

# Docker
docker-compose exec prefect-agent prefect deployment run \
  'NYC Taxi ML Pipeline/production-training' \
  --param skip_tuning=true \
  --param skip_cv=true
```

### Train Specific Models
```bash
# Local
python -c "
from flows.nyc_taxi_flow import nyc_taxi_ml_pipeline
nyc_taxi_ml_pipeline(models=['Random Forest', 'Gradient Boosting'])
"

# Docker
docker-compose exec prefect-agent prefect deployment run \
  'NYC Taxi ML Pipeline/development-testing' \
  --param models='["Random Forest"]'
```

---

## 🗓️ Scheduling Automated Runs

### View Available Deployments
```bash
prefect deployment ls
```

### Schedule Weekly Training
Already configured in `prefect.yaml`:
- **Production Training**: Every Sunday at 2 AM
- **Weekly Retrain**: Every Monday at 3 AM

### Custom Schedule
Edit `prefect.yaml` and add:
```yaml
deployments:
  - name: my-schedule
    schedule:
      cron: "0 */6 * * *"  # Every 6 hours
      timezone: "America/New_York"
```

Then deploy:
```bash
prefect deploy --all
```

---

## 🛑 Stopping Services

### Local
```bash
# Stop Prefect server
pkill -f "prefect server"

# Deactivate environment
deactivate
```

### Docker
```bash
# Stop all services
docker-compose down

# Stop and remove volumes (complete cleanup)
docker-compose down -v
```

---

## 🔍 Troubleshooting

### Issue: "Prefect server not responding"
```bash
# Check server status
curl http://localhost:4200/api/health

# Restart (Docker)
docker-compose restart prefect-server

# Restart (Local)
pkill -f "prefect server"
prefect server start
```

### Issue: "Kaggle authentication failed"
```bash
# Verify credentials exist
cat ~/.kaggle/kaggle.json

# Check permissions
chmod 600 ~/.kaggle/kaggle.json

# For Docker, ensure mounted correctly
docker-compose exec prefect-agent ls -la /root/.kaggle/
```

### Issue: "Out of memory"
```bash
# Reduce sample size
python flows/nyc_taxi_flow.py --sample-size 50000

# Or in Docker
docker-compose exec prefect-agent prefect deployment run \
  'NYC Taxi ML Pipeline/development-testing' \
  --param sample_size=50000
```

### Issue: "MLflow database locked"
```bash
# Stop MLflow UI
pkill -f "mlflow ui"

# Remove lock files
rm -f mlflow_nyc_taxi.db-shm mlflow_nyc_taxi.db-wal

# Restart MLflow (Local)
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db --port 5000

# Restart MLflow (Docker)
docker-compose restart mlflow-ui
```

---

## 📚 Next Steps

1. ✅ **Explore Prefect UI** - Understand flow execution
2. ✅ **Review MLflow Experiments** - Compare model performance  
3. ✅ **Customize Parameters** - Adjust to your needs
4. ✅ **Set Up Schedules** - Automate retraining
5. ✅ **Add Notifications** - Get alerts on failures
6. ✅ **Deploy to Production** - Use Docker for stability

---

## 🆘 Need Help?

- **Prefect Docs**: https://docs.prefect.io/
- **MLflow Docs**: https://mlflow.org/docs/latest/
- **Project README**: See `README_PREFECT.md` for full documentation
- **Issues**: Check troubleshooting section above

---

## ✅ Success Indicators

You know it's working when:
- ✅ Prefect UI shows running/completed flows
- ✅ MLflow UI has logged experiments
- ✅ `models/` directory has saved artifacts
- ✅ No error messages in logs
- ✅ Test R² > 0.70

**Enjoy your fully orchestrated ML pipeline!** 🎉
