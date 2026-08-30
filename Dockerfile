# The Mailroom — API + /office/ floor UI
FROM python:3.11.16-slim-bookworm as builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Keep repo layout so office_dir() and demo fixtures resolve (editable install).
COPY pyproject.toml README.md ./
COPY src ./src
COPY office ./office
COPY fixtures ./fixtures

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -e ".[pdf]" \
 && find /usr/local/lib/python3.11/site-packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Runtime stage
FROM python:3.11.16-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MAILROOM_HOST=0.0.0.0 \
    MAILROOM_PORT=8000 \
    MAILROOM_BASE_DIR=/app/data

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Create non-root user
RUN mkdir -p /app/data \
 && useradd --create-home --uid 10001 mailroom \
 && chown -R mailroom:mailroom /app/data

USER mailroom

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=3)" || exit 1

CMD ["python", "-m", "agent_mailroom"]
