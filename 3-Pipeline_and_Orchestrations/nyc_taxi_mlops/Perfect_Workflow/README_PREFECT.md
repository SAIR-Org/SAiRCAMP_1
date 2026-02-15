# 🚖 NYC Taxi ML Pipeline with Prefect Orchestration

A **production-ready**, **fully orchestrated** ML pipeline for NYC taxi trip duration prediction with **Prefect 2.x**, **MLflow**, and **Docker** support.

## 🎯 Why Prefect Over Airflow?

| Feature | Prefect 2.x | Airflow |
|---------|-------------|---------|
| **Setup Complexity** | ✅ Simple (1 command) | ❌ Complex (multiple components) |
| **Python-Native** | ✅ Pure Python, no DAG files | ⚠️ DAG files required |
| **ML Workflow Focus** | ✅ Designed for data/ML | ⚠️ General purpose |
| **Local Development** | ✅ Works without server | ❌ Requires full setup |
| **Retry Logic** | ✅ Built-in per task | ⚠️ Manual configuration |
| **Caching** | ✅ Native task caching | ❌ Manual implementation |
| **Modern UI** | ✅ React-based, intuitive | ⚠️ Older UI |
| **Dynamic Workflows** | ✅ Fully dynamic | ⚠️ Limited dynamism |
| **Learning Curve** | ✅ Gentle | ❌ Steep |
| **Infrastructure** | ✅ Lightweight | ❌ Heavy (Redis, DB, etc.) |

**Verdict**: Prefect is better suited for ML pipelines, easier to develop with, and requires less infrastructure.

---

## 📁 Project Structure

```
nyc-taxi-mlops/
│
├── flows/
│   └── nyc_taxi_flow.py        # Prefect flow definitions
│
├── src/
│   ├── data/                    # Data acquisition & preprocessing
│   ├── features/                # Feature engineering
│   ├── models/                  # Model training & registry
│   └── utils/                   # Utilities
│
├── config/
│   └── config.py                # Configuration management
│
├── prefect.yaml                 # Prefect deployment config
├── docker-compose.yml           # Multi-container orchestration
├── Dockerfile                   # Container image definition
├── requirements.txt             # Python dependencies
│
├── setup_local.sh              # Local setup script
├── deploy_docker.sh            # Docker deployment script
│
├── models/                      # Saved model artifacts
├── data/                        # Data cache
└── logs/                        # Pipeline logs
```

---

## 🚀 Quick Start

### Option 1: Local Development (Simplest)

Perfect for development and testing:

```bash
# 1. Run setup script
chmod +x setup_local.sh
./setup_local.sh

# 2. Activate virtual environment
source venv/bin/activate

# 3. Start Prefect server (in new terminal)
prefect server start

# 4. Run the pipeline directly
python flows/nyc_taxi_flow.py

# 5. Or deploy and run with Prefect
prefect deploy --all
prefect deployment run 'NYC Taxi ML Pipeline/development-testing'
```

### Option 2: Docker Production (Recommended)

Production-ready with full orchestration:

```bash
# 1. Run deployment script
chmod +x deploy_docker.sh
./deploy_docker.sh

# 2. Deploy flows
docker-compose exec prefect-agent prefect deploy --all

# 3. Run a deployment
docker-compose exec prefect-agent prefect deployment run \
  'NYC Taxi ML Pipeline/development-testing'

# 4. Monitor in browser
open http://localhost:4200
```

---

## 📊 Prefect Features in This Pipeline

### 1. **Task-Based Architecture**

Each pipeline step is a Prefect task with:
- ✅ **Automatic retry** with exponential backoff
- ✅ **Task-level caching** to skip expensive operations
- ✅ **Timeout handling** for long-running tasks
- ✅ **Tags** for filtering and organization

```python
@task(
    name="Train Models",
    retries=2,
    retry_delay_seconds=10,
    timeout_seconds=3600,
    tags=["model", "training", "mlflow"]
)
def train_models_task(...):
    # Your training logic
```

### 2. **Flow Orchestration**

The main flow orchestrates 10 tasks with proper dependencies:

```
Data Acquisition
    ↓
Data Preprocessing
    ↓
Data Splitting
    ↓
Feature Engineering
    ↓
Model Training
    ↓
Hyperparameter Tuning (optional)
    ↓
Cross-Validation (optional)
    ↓
Test Evaluation
    ↓
Model Registry
    ↓
Deployment Package
```

### 3. **Smart Caching**

Data acquisition is cached for 7 days:

```python
@task(
    cache_key_fn=lambda *args, **kwargs: "nyc_taxi_data_acquisition",
    cache_expiration=timedelta(days=7)
)
def acquire_data_task(config):
    # Downloads cached for a week
```

### 4. **Dynamic Configuration**

Run with different parameters:

```python
# Quick test
nyc_taxi_ml_pipeline(
    sample_size=10000,
    skip_tuning=True,
    skip_cv=True
)

# Full production run
nyc_taxi_ml_pipeline(
    sample_size=None,  # Use all data
    skip_tuning=False,
    skip_cv=False
)
```

### 5. **Artifacts & Reporting**

Automatic generation of:
- 📊 **Data quality reports**
- 📈 **Model comparison tables**
- 📋 **Test evaluation summaries**
- 📦 **Pipeline execution summaries**

All visible in Prefect UI!

### 6. **Concurrent Execution**

Tasks that don't depend on each other can run in parallel:

```python
@flow(
    task_runner=ConcurrentTaskRunner()
)
def nyc_taxi_ml_pipeline():
    # Parallel execution where possible
```

---

## 🗓️ Scheduled Deployments

### Pre-configured Schedules

**1. Production Training** (Weekly)
- **When**: Every Sunday at 2 AM
- **What**: Full training with complete dataset
- **Use**: Regular model updates

**2. Weekly Retrain** (Weekly)
- **When**: Every Monday at 3 AM
- **What**: Automated retraining workflow
- **Use**: Continuous model improvement

**3. Development Testing** (Manual)
- **When**: On-demand
- **What**: Fast validation with small sample
- **Use**: CI/CD pipeline testing

**4. Fast Validation** (Manual)
- **When**: On-demand
- **What**: Quick pipeline health check
- **Use**: Pre-deployment validation

### Custom Schedules

Create your own in `prefect.yaml`:

```yaml
deployments:
  - name: my-custom-schedule
    schedule:
      cron: "0 */6 * * *"  # Every 6 hours
      timezone: "America/New_York"
```

---

## 🎛️ Configuration Options

### Flow Parameters

Control execution behavior:

```bash
# Sample size
prefect deployment run 'NYC Taxi ML Pipeline/development-testing' \
  --param sample_size=50000

# Skip expensive operations
prefect deployment run 'NYC Taxi ML Pipeline/production-training' \
  --param skip_tuning=true \
  --param skip_cv=true

# Train specific models only
prefect deployment run 'NYC Taxi ML Pipeline/development-testing' \
  --param models='["Random Forest", "Gradient Boosting"]'

# Custom random seed
prefect deployment run 'NYC Taxi ML Pipeline/production-training' \
  --param random_state=123
```

### Environment Variables

Configure via `.env` file:

```bash
# Prefect
PREFECT_API_URL=http://127.0.0.1:4200/api

# MLflow
MLFLOW_TRACKING_URI=sqlite:///mlflow_nyc_taxi.db
MLFLOW_EXPERIMENT_NAME=nyc_taxi_production

# Kaggle
KAGGLE_USERNAME=your_username
KAGGLE_KEY=your_api_key

# Pipeline
SAMPLE_SIZE=200000
RANDOM_STATE=42
```

---

## 🐳 Docker Deployment

### Architecture

```
┌─────────────────────────────────────────┐
│         Docker Compose Setup            │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────┐  ┌──────────────┐   │
│  │   Prefect    │  │  PostgreSQL  │   │
│  │   Server     │◄─┤   Database   │   │
│  └──────┬───────┘  └──────────────┘   │
│         │                               │
│  ┌──────▼───────┐  ┌──────────────┐   │
│  │   Prefect    │  │   MLflow UI  │   │
│  │    Agent     │  │              │   │
│  └──────────────┘  └──────────────┘   │
│                                         │
│  ┌──────────────┐                      │
│  │  Jupyter Lab │  (Optional)          │
│  └──────────────┘                      │
└─────────────────────────────────────────┘
```

### Services

| Service | Port | Purpose |
|---------|------|---------|
| **Prefect Server** | 4200 | Orchestration & UI |
| **PostgreSQL** | 5432 | Prefect metadata |
| **Prefect Agent** | - | Flow execution |
| **MLflow UI** | 5000 | Experiment tracking |
| **Jupyter Lab** | 8888 | Interactive development |

### Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f prefect-agent

# Stop services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Execute commands in container
docker-compose exec prefect-agent bash
```

---

## 📈 Monitoring & Observability

### Prefect UI (http://localhost:4200)

- 📊 **Flow Runs**: Real-time execution status
- 📋 **Task Runs**: Individual task status & logs
- 📈 **Artifacts**: Generated reports & visualizations
- 🗓️ **Deployments**: Scheduled and manual runs
- 🔔 **Notifications**: Failures, successes, custom events

### MLflow UI (http://localhost:5000)

- 🧪 **Experiments**: All training runs
- 📊 **Metrics**: R², RMSE, MAE comparisons
- 🎯 **Parameters**: Hyperparameter tracking
- 🏛️ **Model Registry**: Versioning & staging
- 📦 **Artifacts**: Models, preprocessors, metadata

### Logs

```bash
# Local logs
tail -f logs/pipeline.log

# Docker logs
docker-compose logs -f prefect-agent

# Specific task logs (in Prefect UI)
Click on task → View Logs tab
```

---

## 🔧 Advanced Usage

### 1. Custom Task Definitions

Add your own tasks:

```python
@task(
    name="My Custom Task",
    retries=3,
    cache_key_fn=my_cache_function,
    tags=["custom"]
)
def my_custom_task(data):
    # Your logic
    return result

# Use in flow
@flow
def my_flow():
    result = my_custom_task(data)
```

### 2. Conditional Execution

Skip tasks based on conditions:

```python
@flow
def smart_pipeline(skip_tuning: bool):
    # Always run these
    data = acquire_data()
    cleaned = preprocess(data)
    
    # Conditional execution
    if not skip_tuning:
        tuned_model = tune_model(cleaned)
    else:
        tuned_model = None
```

### 3. Sub-flows

Modularize complex workflows:

```python
@flow
def data_preparation_subflow():
    data = acquire_data()
    cleaned = preprocess(data)
    return cleaned

@flow
def main_pipeline():
    data = data_preparation_subflow()
    model = train_model(data)
```

### 4. Notifications

Add Slack/Email notifications:

```python
from prefect.blocks.notifications import SlackWebhook

@flow(on_failure=[notify_on_failure])
def my_flow():
    # Your flow logic
    pass

def notify_on_failure(flow, flow_run, state):
    slack = SlackWebhook.load("my-slack-webhook")
    slack.notify(f"Flow {flow.name} failed!")
```

### 5. Secrets Management

Store sensitive data securely:

```python
from prefect.blocks.system import Secret

# Create secret (one time)
secret = Secret(value="my-api-key")
secret.save("my-api-key")

# Use in flow
@task
def use_secret():
    api_key = Secret.load("my-api-key").get()
    # Use api_key securely
```

---

## 🧪 Testing

### Test Pipeline Locally

```bash
# Quick validation (10K samples, no tuning)
python flows/nyc_taxi_flow.py

# With custom config
python -c "
from flows.nyc_taxi_flow import nyc_taxi_ml_pipeline
nyc_taxi_ml_pipeline(sample_size=5000, skip_tuning=True)
"
```

### Test Deployments

```bash
# Deploy to Prefect
prefect deploy --all

# Run test deployment
prefect deployment run 'NYC Taxi ML Pipeline/fast-validation'

# Check status
prefect flow-run ls --limit 5
```

### CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Test Pipeline
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run validation
        run: |
          python flows/nyc_taxi_flow.py \
            --sample-size 5000 \
            --skip-tuning \
            --skip-cv
```

---

## 🔍 Troubleshooting

### Common Issues

**1. "Prefect server not responding"**
```bash
# Check if server is running
curl http://localhost:4200/api/health

# Restart server
docker-compose restart prefect-server

# Or for local
pkill -f "prefect server"
prefect server start
```

**2. "Task keeps retrying"**
- Check task logs in Prefect UI
- Verify data availability
- Check network connectivity
- Review error messages

**3. "MLflow database locked"**
```bash
# Stop all MLflow UI instances
pkill -f "mlflow ui"

# Remove lock files
rm -f mlflow_nyc_taxi.db-shm mlflow_nyc_taxi.db-wal

# Restart
mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db --port 5000
```

**4. "Out of memory"**
```bash
# Reduce sample size
prefect deployment run 'NYC Taxi ML Pipeline/development-testing' \
  --param sample_size=50000

# Or increase Docker memory limit in docker-compose.yml
services:
  prefect-agent:
    deploy:
      resources:
        limits:
          memory: 8G
```

**5. "Kaggle authentication failed"**
```bash
# Verify credentials
cat ~/.kaggle/kaggle.json

# Re-export for Docker
export KAGGLE_USERNAME=your_username
export KAGGLE_KEY=your_key
docker-compose up -d
```

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or set environment variable
export PREFECT_LOGGING_LEVEL=DEBUG
```

---

## 📚 Best Practices

### 1. **Task Granularity**
- Each task should do ONE thing well
- Tasks should be idempotent (can run multiple times safely)
- Keep tasks under 15 minutes when possible

### 2. **Error Handling**
- Use task-level retries for transient failures
- Add timeouts for long-running tasks
- Log errors with context

### 3. **Resource Management**
- Use caching for expensive data operations
- Clean up temporary files
- Monitor memory usage

### 4. **Testing**
- Test with small samples first
- Validate data quality at each step
- Use fast-validation deployment for CI/CD

### 5. **Production**
- Use Docker for consistent environments
- Set up monitoring and alerts
- Schedule retraining based on model drift
- Keep logs for debugging

---

## 🚦 Production Readiness Checklist

- [ ] **Code Quality**
  - [ ] All tests passing
  - [ ] Code reviewed
  - [ ] Documentation complete

- [ ] **Infrastructure**
  - [ ] Docker images built
  - [ ] Services healthy
  - [ ] Network connectivity verified

- [ ] **Monitoring**
  - [ ] Prefect UI accessible
  - [ ] MLflow tracking working
  - [ ] Logs collecting properly

- [ ] **Security**
  - [ ] Credentials secured
  - [ ] API keys in secrets
  - [ ] Network isolated

- [ ] **Performance**
  - [ ] Training time acceptable
  - [ ] Resource usage reasonable
  - [ ] Caching working

- [ ] **Deployment**
  - [ ] Schedules configured
  - [ ] Notifications set up
  - [ ] Rollback plan ready

---

## 📖 Additional Resources

### Prefect Documentation
- [Prefect Docs](https://docs.prefect.io/)
- [Prefect Cloud](https://www.prefect.io/cloud)
- [Prefect Discourse](https://discourse.prefect.io/)

### MLflow Documentation
- [MLflow Docs](https://mlflow.org/docs/latest/index.html)
- [MLflow Model Registry](https://mlflow.org/docs/latest/model-registry.html)

### Related Projects
- [Prefect Recipes](https://github.com/PrefectHQ/prefect-recipes)
- [MLflow Examples](https://github.com/mlflow/mlflow/tree/master/examples)

---

## 🤝 Contributing

Contributions welcome! To add features:

1. Fork the repository
2. Create a feature branch
3. Add your task/flow in `flows/`
4. Update documentation
5. Submit a pull request

---

## 📄 License

This project is provided as-is for educational and production use.

---

## 🙏 Acknowledgments

- **Prefect** for modern workflow orchestration
- **MLflow** for experiment tracking
- **NYC TLC** for the dataset
- **Kaggle** for hosting the data

---

**Production Ready** | **Prefect Orchestrated** | **MLflow Integrated** | **Docker Deployed** | **7x Faster**
