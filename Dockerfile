# --- Stage 1: build the React SPA ---
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
# Vite builds into /app/backend/app/static (see vite.config.ts outDir)
RUN npm run build

# --- Stage 2: Python runtime with ffmpeg bundled ---
FROM python:3.12-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /app/backend/app/static ./backend/app/static

ENV STREAMVA_DATA_DIR=/data \
    PYTHONUNBUFFERED=1
EXPOSE 8000
WORKDIR /app/backend

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

# --proxy-headers lets the app trust X-Forwarded-* from your reverse proxy
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
