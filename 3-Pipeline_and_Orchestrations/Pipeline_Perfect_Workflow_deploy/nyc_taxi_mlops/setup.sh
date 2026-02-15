#!/usr/bin/env bash
# Setup script for NYC Taxi ML Pipeline

set -e  # Exit on error

echo "=================================================="
echo "NYC Taxi ML Pipeline - Setup"
echo "=================================================="
echo ""

# Check Python version
echo "🐍 Checking Python version..."
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "   Python version: $python_version"

if ! python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
    echo "❌ Python 3.8 or higher is required"
    exit 1
fi
echo "✅ Python version OK"
echo ""

# Create virtual environment (optional but recommended)
if [ "$1" == "--venv" ]; then
    echo "🔨 Creating virtual environment..."
    if [ ! -d "venv" ]; then
        python -m venv venv
        echo "✅ Virtual environment created"
    else
        echo "⚠️  Virtual environment already exists"
    fi
    echo ""
    echo "📌 To activate the virtual environment:"
    echo "   source venv/bin/activate  (Linux/Mac)"
    echo "   venv\\Scripts\\activate    (Windows)"
    echo ""
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Create directory structure
echo "📁 Creating project directories..."
mkdir -p models
mkdir -p data
mkdir -p logs
echo "✅ Directories created"
echo ""

# Check Kaggle credentials
echo "🔑 Checking Kaggle credentials..."
if [ -f "$HOME/.kaggle/kaggle.json" ]; then
    echo "✅ Kaggle credentials found"
else
    echo "⚠️  Kaggle credentials not found"
    echo ""
    echo "📌 To download data from Kaggle:"
    echo "   1. Go to https://www.kaggle.com/settings"
    echo "   2. Create new API token (downloads kaggle.json)"
    echo "   3. Run: mkdir -p ~/.kaggle && mv kaggle.json ~/.kaggle/"
    echo "   4. Run: chmod 600 ~/.kaggle/kaggle.json"
fi
echo ""

# Test imports
echo "🧪 Testing imports..."
python -c "
import numpy
import pandas
import sklearn
import mlflow
import kagglehub
print('✅ All imports successful')
"
echo ""

# Run dry run
echo "🔍 Running configuration validation..."
python main.py --dry-run
echo ""

echo "=================================================="
echo "✅ Setup Complete!"
echo "=================================================="
echo ""
echo "🚀 Next steps:"
echo "   1. Run pipeline:     python main.py"
echo "   2. Or use Make:      make run"
echo "   3. View MLflow UI:   make mlflow-ui"
echo ""
echo "📚 For more options:    python main.py --help"
echo "                        make help"
echo ""