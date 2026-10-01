FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY cdms ./cdms

RUN useradd --create-home --uid 10001 cdms
USER cdms

ENV CDMS_PORT=8001

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/api/v1/ready', timeout=2).status == 200 else 1)"

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn cdms.main:app --host 0.0.0.0 --port ${CDMS_PORT:-8001} --workers 1"]
