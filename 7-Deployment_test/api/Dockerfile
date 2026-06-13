FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY shared/ ./shared/
COPY api/ ./api/

WORKDIR /app/api

RUN uv pip install --system -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "1078"]
