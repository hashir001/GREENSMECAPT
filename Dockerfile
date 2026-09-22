FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update \
    && apt-get install --yes --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

COPY config ./config

RUN useradd --create-home --uid 10001 greensmecapt \
    && mkdir -p /app/data/documents \
    && chown -R greensmecapt:greensmecapt /app

USER greensmecapt

EXPOSE 8000

CMD ["sh", "-c", "uvicorn greensmecapt.api.app:app --host 0.0.0.0 --port ${PORT}"]
