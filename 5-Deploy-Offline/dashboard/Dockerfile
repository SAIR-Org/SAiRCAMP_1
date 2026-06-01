FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY 5-Deploy-Offline/dashboard/ ./dashboard/

WORKDIR /app/dashboard

RUN uv pip install --system -r requirements.txt

CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
