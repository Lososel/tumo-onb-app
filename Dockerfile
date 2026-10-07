# Single small image: builds the Vue app, then serves it + the API from one uvicorn process.
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app/backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
# Run unprivileged; the app only needs to write its snapshot cache under data/cache.
RUN useradd --create-home --uid 10001 app && mkdir -p data/cache && chown -R app data
USER app
EXPOSE 8000
# Hosts like Render pass the port in $PORT; 8000 locally. For live data set DATA_SOURCE=google,
# GOOGLE_SHEET_ID and mount the service-account key (GOOGLE_CREDENTIALS_FILE) at runtime.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
