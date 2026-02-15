.PHONY: help install clean run run-fast run-test mlflow-ui lint format test docs

# Default target
help:
	@echo "NYC Taxi ML Pipeline - Available Commands"
	@echo "=========================================="
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install dependencies"
	@echo "  make clean         Clean generated files and cache"
	@echo ""
	@echo "Pipeline:"
	@echo "  make run           Run full pipeline with default settings"
	@echo "  make run-fast      Run pipeline with reduced sample size (fast test)"
	@echo "  make run-test      Run pipeline with minimal data (quickest test)"
	@echo "  make dry-run       Validate configuration without running"
	@echo ""
	@echo "MLflow:"
	@echo "  make mlflow-ui     Start MLflow UI"
	@echo "  make mlflow-clean  Clean MLflow database and artifacts"
	@echo ""
	@echo "Development:"
	@echo "  make lint          Run code linting"
	@echo "  make format        Format code with black"
	@echo ""

# Installation
install:
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt
	@echo "✅ Installation complete"

# Clean generated files
clean:
	@echo "🧹 Cleaning generated files..."
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .pytest_cache
	rm -rf *.egg-info
	rm -rf build dist
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	find . -name "*~" -delete
	@echo "✅ Cleanup complete"

# Clean MLflow artifacts
mlflow-clean:
	@echo "🧹 Cleaning MLflow database and artifacts..."
	rm -f mlflow_nyc_taxi.db*
	rm -rf mlruns/
	rm -rf mlartifacts/
	@echo "✅ MLflow cleanup complete"

# Run pipeline with defaults
run:
	@echo "🚀 Running NYC Taxi ML Pipeline (full)..."
	python main.py

# Run pipeline with reduced sample (fast test)
run-fast:
	@echo "🚀 Running NYC Taxi ML Pipeline (fast mode)..."
	python main.py --sample-size 50000 --skip-tuning

# Run pipeline with minimal data (quickest test)
run-test:
	@echo "🚀 Running NYC Taxi ML Pipeline (test mode)..."
	python main.py --sample-size 10000 --skip-tuning --skip-cv --models "Linear Regression" "Ridge"

# Dry run
dry-run:
	@echo "🔍 Validating configuration..."
	python main.py --dry-run

# Start MLflow UI
mlflow-ui:
	@echo "🌐 Starting MLflow UI..."
	@echo "Open browser at: http://127.0.0.1:5000"
	mlflow ui --backend-store-uri sqlite:///mlflow_nyc_taxi.db --host 127.0.0.1 --port 5000

# Linting
lint:
	@echo "🔍 Running linting..."
	flake8 src/ config/ --max-line-length=100 --ignore=E203,W503 || true
	pylint src/ config/ --max-line-length=100 --disable=C0111,R0913 || true
	@echo "✅ Linting complete"

# Code formatting
format:
	@echo "✨ Formatting code..."
	black src/ config/ main.py --line-length=100
	isort src/ config/ main.py --profile black
	@echo "✅ Formatting complete"

# Run all quick checks
check: lint
	@echo "✅ All checks passed"

# Create project structure
setup:
	@echo "📁 Creating project structure..."
	mkdir -p models data logs
	@echo "✅ Project structure created"

# Full reset (clean + mlflow-clean)
reset: clean mlflow-clean
	@echo "♻️  Full reset complete"

# Development setup
dev-install: install
	@echo "📦 Installing development dependencies..."
	pip install black flake8 pylint isort pytest
	@echo "✅ Development setup complete"