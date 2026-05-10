# ── Build stage ────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime stage ─────────────────────────────────────────────────
FROM python:3.12-slim

RUN adduser --disabled-password --gecos "" appuser
USER appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY app.py .

ENV GITHUB_WEBHOOK_SECRET=""
ENV UIPATH_URL=""
ENV UIPATH_FOLDER=""
ENV UIPATH_ACCESS_TOKEN=""

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
