"""
Prometheus metrics definitions for the MLOps system.

These metrics track:
- HTTP requests (count, latency, status codes)
- Predictions (count, values, latency)
- Model information (version, alias)
- System health (active requests)
"""

from prometheus_client import Counter, Histogram, Gauge, Info

# ──────────────────────────────────────────────────────────────
# HTTP Request Metrics
# ──────────────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
)

# ──────────────────────────────────────────────────────────────
# Prediction Metrics
# ──────────────────────────────────────────────────────────────
PREDICTION_COUNT = Counter(
    'predictions_total',
    'Total number of predictions made'
)

PREDICTION_VALUE = Gauge(
    'prediction_value_minutes',
    'Last predicted trip duration in minutes'
)

PREDICTION_LATENCY = Histogram(
    'prediction_duration_seconds',
    'Time to compute a single prediction in seconds',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1]
)

# ──────────────────────────────────────────────────────────────
# Model Metrics
# ──────────────────────────────────────────────────────────────
MODEL_INFO = Info(
    'model_info',
    'Information about the currently loaded model'
)

# ──────────────────────────────────────────────────────────────
# System Metrics
# ──────────────────────────────────────────────────────────────
ACTIVE_REQUESTS = Gauge(
    'active_requests',
    'Number of requests currently being processed'
)

# ──────────────────────────────────────────────────────────────
# Legacy aliases for compatibility with standard dashboards
# ──────────────────────────────────────────────────────────────
http_requests_total = REQUEST_COUNT
http_request_duration_seconds = REQUEST_LATENCY
