FROM python:3.11-slim

WORKDIR /app

RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid 1001 --no-create-home appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools && \
    pip install --no-cache-dir -r requirements.txt

COPY app/ app/

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8009

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8009/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
