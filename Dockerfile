FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY bot ./bot
COPY tests ./tests

RUN pip install --upgrade pip \
    && pip install -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "bot.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
