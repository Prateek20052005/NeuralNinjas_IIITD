# One container: FastAPI serves the API and the built phone app on the same address.
# Build:  docker build -t udyam-digital .
# Run:    docker run --env-file .env -p 7860:7860 udyam-digital      then open http://localhost:7860
# The Groq key comes from --env-file / the host's secret settings at run time; it is never baked into the image.

# ---- 1. build the phone app ----
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. API + local OCR ----
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=7860 APP_TODAY=2026-07-15
# OpenCV and ONNX Runtime need these two system libraries on slim images
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
# fetch the OCR models now, so the first document a customer uploads isn't slow
RUN python -c "from rapidocr import RapidOCR; RapidOCR()"
COPY backend backend
COPY data/*.csv data/
COPY --from=web /web/dist frontend/dist
# run as a normal user, not root (Hugging Face Spaces also expects uid 1000)
RUN useradd -m -u 1000 app && chown -R app /app
USER app
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/api/health')"
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
