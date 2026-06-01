FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY shared/ ./shared/
COPY pipeline/ ./pipeline/

WORKDIR /app/pipeline

RUN uv pip install --system -r requirements.txt

CMD ["python", "main.py", "--sample-size", "500000", "--tune", "--promote"]
