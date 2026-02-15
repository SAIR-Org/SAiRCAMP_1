#!/bin/bash

# ============================================
# NYC Taxi ML Pipeline - Docker Deployment
# ============================================

set -e  # Exit on error

echo "🐳 Deploying NYC Taxi ML Pipeline with Docker..."
echo "=" | head -c 70 | tr '\n' '='
echo ""

# ============================================
# Step 1: Check Prerequisites
# ============================================

echo "📋 Step 1/6: Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required but not installed"
    echo "   Install from: https://docs.docker.com/get-docker/"
    exit 1
fi
echo "   ✓ Docker detected: $(docker --version)"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo "❌ Docker Compose is required but not installed"
    exit 1
fi
echo "   ✓ Docker Compose detected"

# Check Kaggle credentials
KAGGLE_FILE="$HOME/.kaggle/kaggle.json"
if [ ! -f "$KAGGLE_FILE" ]; then
    echo "❌ Kaggle credentials not found at $KAGGLE_FILE"
    echo "   Download from: https://www.kaggle.com/settings"
    exit 1
fi
echo "   ✓ Kaggle credentials found"

# ============================================
# Step 2: Set Environment Variables
# ============================================

echo ""
echo "🔧 Step 2/6: Setting environment variables..."

# Load Kaggle credentials
export KAGGLE_USERNAME=$(cat $KAGGLE_FILE | python3 -c "import sys, json; print(json.load(sys.stdin)['username'])")
export KAGGLE_KEY=$(cat $KAGGLE_FILE | python3 -c "import sys, json; print(json.load(sys.stdin)['key'])")

echo "   ✓ Environment variables configured"

# ============================================
# Step 3: Create Required Directories
# ============================================

echo ""
echo "📁 Step 3/6: Creating directories..."

mkdir -p models data logs
echo "   ✓ Local directories created"

# ============================================
# Step 4: Stop Existing Containers
# ============================================

echo ""
echo "🛑 Step 4/6: Stopping existing containers..."

docker-compose down 2>/dev/null || true
echo "   ✓ Existing containers stopped"

# ============================================
# Step 5: Build and Start Services
# ============================================

echo ""
echo "🏗️  Step 5/6: Building and starting services..."

docker-compose up -d --build

echo "   ✓ Services started"
echo ""
echo "   Waiting for services to be healthy..."
sleep 10

# Wait for Prefect server
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:4200/api/health > /dev/null 2>&1; then
        echo "   ✓ Prefect server is healthy"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT+1))
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "   ⚠️  Prefect server may not be fully ready"
fi

# ============================================
# Step 6: Create Work Pool
# ============================================

echo ""
echo "🎯 Step 6/6: Creating Prefect work pool..."

# Wait a bit more for full initialization
sleep 5

# Create work pool (this will fail if it already exists, which is fine)
docker-compose exec -T prefect-server prefect work-pool create default-agent-pool --type process 2>/dev/null || echo "   ℹ️  Work pool may already exist"

echo "   ✓ Work pool configured"

# ============================================
# Deployment Complete
# ============================================

echo ""
echo "=" | head -c 70 | tr '\n' '='
echo ""
echo "✅ Docker deployment complete!"
echo ""
echo "🌐 Service URLs:"
echo "   • Prefect UI:  http://localhost:4200"
echo "   • MLflow UI:   http://localhost:5000"
echo "   • Jupyter Lab: http://localhost:8888"
echo ""
echo "📊 Container Status:"
docker-compose ps
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. 📥 Deploy flows to Prefect:"
echo "   docker-compose exec prefect-agent prefect deploy --all"
echo ""
echo "2. ▶️  Run a flow:"
echo "   docker-compose exec prefect-agent prefect deployment run \\"
echo "     'NYC Taxi ML Pipeline/development-testing'"
echo ""
echo "3. 📊 Monitor execution:"
echo "   Open http://localhost:4200 in your browser"
echo ""
echo "4. 🔍 View logs:"
echo "   docker-compose logs -f prefect-agent"
echo ""
echo "5. 🛑 Stop services:"
echo "   docker-compose down"
echo ""
echo "=" | head -c 70 | tr '\n' '='
echo ""
