FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV ANONYMIZED_TELEMETRY=False

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warm up'])"

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'

COPY --from=docker:27.3.1-cli /usr/local/bin/docker /usr/local/bin/docker

COPY . .
