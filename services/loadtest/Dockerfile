FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /loadtest

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY locustfile.py ./

EXPOSE 8089

ENTRYPOINT ["locust"]
CMD ["-f", "locustfile.py"]
