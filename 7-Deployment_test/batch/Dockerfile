FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY shared/ ./shared/
COPY batch/ ./batch/

WORKDIR /app/batch

RUN uv pip install --system -r requirements.txt

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "1079"]
