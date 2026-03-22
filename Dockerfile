FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package definition first for layer caching
COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src
RUN python -m pip install --no-cache-dir .

# Copy remaining files (config.yaml, assets, etc.)
COPY . /app/

EXPOSE 8094

CMD ["mail-mcp", "serve-http"]
