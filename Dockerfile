FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Dependencies change rarely, so they come before the code (Docker caches each step).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the embedding model now, so the container works offline later.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warm up'])"

# The code changes all the time, so it comes last. .dockerignore decides what is copied.
COPY . .
