FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY dashboard/ ./dashboard/

WORKDIR /app/dashboard

RUN uv pip install --system -r requirements.txt

CMD ["streamlit", "run", "app.py", "--server.port", "1080", "--server.address", "0.0.0.0"]
