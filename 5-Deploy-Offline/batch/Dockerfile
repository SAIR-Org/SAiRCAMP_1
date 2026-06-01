FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

# shared/ lives in Module 4 — needed for preprocessor pickle to load correctly
COPY 4-Deploy-Online/shared/ ./shared/
COPY 5-Deploy-Offline/batch/ ./batch/

WORKDIR /app/batch

RUN uv pip install --system -r requirements.txt

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8001"]
