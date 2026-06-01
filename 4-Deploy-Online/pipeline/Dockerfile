FROM python:3.12-slim

ENV PREFECT_HOME=/tmp/prefect
ENV PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=120
RUN mkdir -p /tmp/prefect

RUN pip install uv

WORKDIR /app

COPY shared/ ./shared/
COPY pipeline/ ./pipeline/

WORKDIR /app/pipeline

RUN uv pip install --system -r requirements.txt

CMD ["python", "main.py", "--sample-size", "500000", "--tune", "--promote"]
