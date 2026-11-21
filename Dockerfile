FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
# Chroma's anonymous usage telemetry would contact a remote server; everything here stays local.
ENV ANONYMIZED_TELEMETRY=False

# Dependencies change rarely, so they come before the code (Docker caches each step).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the embedding model now, so the container works offline later.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warm up'])"

# Only the docker CLI binary, for the bonus Docker log watch. It talks to the host's Docker only when
# docker-compose.watch.yml mounts /var/run/docker.sock; without the socket it can see no container.
COPY --from=docker:27.3.1-cli /usr/local/bin/docker /usr/local/bin/docker

# The code changes all the time, so it comes last. .dockerignore decides what is copied.
COPY . .
