#!/bin/bash

# ============================================
# NYC Taxi ML Pipeline - Local Setup Script
# ============================================

set -e  # Exit on error

echo "🚀 Setting up NYC Taxi ML Pipeline with Prefect..."
echo "=" | head -c 70 | tr '\n' '='
echo ""

# ============================================
# Step 1: Check Prerequisites
# ============================================

echo "📋 Step 1/7: Checking prerequisites..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "   ✓ Python $PYTHON_VERSION detected"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is required but not installed"
    exit 1
fi
echo "   ✓ pip3 detected"

# ============================================
# Step 2: Create Virtual Environment
# ============================================

echo ""
echo "🔧 Step 2/7: Creating virtual environment..."

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "   ✓ Virtual environment created"
else
    echo "   ℹ️  Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate
echo "   ✓ Virtual environment activated"

# ============================================
# Step 3: Install Dependencies
# ============================================

echo ""
echo "📦 Step 3/7: Installing Python dependencies..."

pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
echo "   ✓ Dependencies installed"

# ============================================
# Step 4: Setup Kaggle Credentials
# ============================================

echo ""
echo "🔑 Step 4/7: Setting up Kaggle credentials..."

KAGGLE_DIR="$HOME/.kaggle"
KAGGLE_FILE="$KAGGLE_DIR/kaggle.json"

if [ ! -f "$KAGGLE_FILE" ]; then
    echo "   ⚠️  Kaggle credentials not found"
    echo "   📝 Please download kaggle.json from: https://www.kaggle.com/settings"
    echo "   📂 Save it to: $KAGGLE_FILE"
    
    read -p "   Press Enter when ready to continue..."
    
    if [ ! -f "$KAGGLE_FILE" ]; then
        echo "   ❌ Kaggle credentials still not found"
        exit 1
    fi
fi

chmod 600 "$KAGGLE_FILE"
echo "   ✓ Kaggle credentials configured"

# ============================================
# Step 5: Create Project Directories
# ============================================

echo ""
echo "📁 Step 5/7: Creating project directories..."

mkdir -p models data logs
echo "   ✓ Directories created: models/, data/, logs/"

# ============================================
# Step 6: Initialize Prefect
# ============================================

echo ""
echo "🎯 Step 6/7: Initializing Prefect..."

# Set Prefect to use local SQLite (no server needed for simple setup)
export PREFECT_API_URL="http://127.0.0.1:4200/api"

echo "   📝 Prefect will use local ephemeral server"
echo "   💡 For production, use: docker-compose up -d"

# ============================================
# Step 7: Test Installation
# ============================================

echo ""
echo "🧪 Step 7/7: Testing installation..."

python3 -c "
import prefect
import mlflow
import sklearn
import pandas
import numpy
print('   ✓ All imports successful')
print(f'   - Prefect: {prefect.__version__}')
print(f'   - MLflow: {mlflow.__version__}')
print(f'   - scikit-learn: {sklearn.__version__}')
"

# ============================================
# Setup Complete
# ============================================

echo ""
echo "=" | head -c 70 | tr '\n' '='
echo ""
echo "✅ Setup complete! Your NYC Taxi ML Pipeline is ready."
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. 🚀 Start Prefect Server (in a new terminal):"
echo "   prefect server start"
echo ""
echo "2. 🌐 Open Prefect UI in browser:"
echo "   http://127.0.0.1:4200"
echo ""
echo "3. 📊 Open MLflow UI (in another terminal):"
echo "   mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db --port 5000"
echo "   http://127.0.0.1:5000"
echo ""
echo "4. ▶️  Run the pipeline:"
echo "   python flows/nyc_taxi_flow.py"
echo ""
echo "   OR deploy and run with Prefect:"
echo "   prefect deploy --all"
echo "   prefect deployment run 'NYC Taxi ML Pipeline/development-testing'"
echo ""
echo "5. 🐳 For production, use Docker:"
echo "   ./deploy_docker.sh"
echo ""
echo "=" | head -c 70 | tr '\n' '='
echo ""
