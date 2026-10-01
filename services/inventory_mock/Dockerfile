FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY inventory_mock ./inventory_mock

RUN useradd --create-home --uid 10002 mock \
    && chown -R mock:mock /app
USER mock

ENV MOCK_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

CMD ["sh", "-c", "exec uvicorn inventory_mock.main:app --host 0.0.0.0 --port ${MOCK_PORT:-8000}"]
