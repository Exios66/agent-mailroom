# The Mailroom — API + /office/ floor UI
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MAILROOM_HOST=0.0.0.0 \
    MAILROOM_PORT=8000 \
    MAILROOM_BASE_DIR=/app/data

# Keep repo layout so office_dir() and demo fixtures resolve (editable install).
COPY pyproject.toml README.md ./
COPY src ./src
COPY office ./office
COPY fixtures ./fixtures

RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir -e ".[pdf]" \
 && mkdir -p /app/data \
 && useradd --create-home --uid 10001 mailroom \
 && chown -R mailroom:mailroom /app/data

USER mailroom

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=3)"

CMD ["python", "-m", "agent_mailroom"]
