FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/ioc

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && mkdir -p /data/chroma /data/models /home/ioc \
 && chmod -R 0777 /data /home/ioc

COPY p1 ./p1
COPY p2 ./p2
COPY p3 ./p3
COPY bonus ./bonus

EXPOSE 8000
CMD ["python", "p3/serve.py", "/workspace"]
