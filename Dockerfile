# Multi-stage build: dependencies are installed into a virtualenv in the
# build stage, the runtime stage ships only that venv plus the source.

FROM python:3.12.7-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pip setuptools


FROM python:3.12.7-slim

LABEL org.opencontainers.image.title="Async Research Assistant"
LABEL org.opencontainers.image.version="1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY ai/ ./ai/
COPY researcher/ ./researcher/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY pytest.ini ./

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/.cache /app/artefacts \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "researcher", "ask", "What is photosynthesis and what are its main stages?"]