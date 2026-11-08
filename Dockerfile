FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/ioc

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && mkdir -p /data/chroma /data/models /home/ioc \
 && chmod -R 0777 /data /home/ioc

COPY p1 ./p1
COPY p2 ./p2

EXPOSE 8000
CMD ["python", "p2/serve.py", "/workspace"]
