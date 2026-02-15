FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p models data logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PREFECT_API_URL=http://prefect-server:4200/api
ENV MLFLOW_TRACKING_URI=sqlite:///mlflow_nyc_taxi.db

# Expose ports (if needed)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import prefect; print('healthy')" || exit 1

# Default command - run Prefect agent
CMD ["prefect", "agent", "start", "--pool", "default-agent-pool"]
