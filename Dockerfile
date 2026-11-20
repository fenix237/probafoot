FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROBAFOOT_DB=/app/data/probafoot.sqlite

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY probafoot ./probafoot
COPY static ./static
COPY docker/refresh.sh docker/capture.sh /usr/local/bin/

# Utilisateur sans privilèges ; /app/data (SQLite + CSV bruts) est le seul dossier inscriptible.
RUN useradd --system --uid 10001 --home-dir /app probafoot \
    && mkdir -p /app/data \
    && chown -R probafoot:probafoot /app/data \
    && chmod +x /usr/local/bin/refresh.sh /usr/local/bin/capture.sh
USER probafoot
VOLUME ["/app/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "probafoot.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
