# One image for every service (ADR-005); SERVICE picks the app at start-up.
FROM python:3.12-slim
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-serving.txt .
RUN pip install --no-cache-dir -r requirements-serving.txt
COPY configs/ configs/
COPY src/ src/
ENV PYTHONUNBUFFERED=1 SERVING_DIR=/serving PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/health')" || exit 1
CMD ["sh", "-c", "if [ \"$SERVICE\" = mcp ]; then python -m src.gateway.mcp_server; else uvicorn src.services.apps:app --host 0.0.0.0 --port $PORT; fi"]
