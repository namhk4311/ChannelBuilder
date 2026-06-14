# VNG Insider — backend (FastAPI + ffmpeg) cho AgentBase Runtime.
# Contract AgentBase: nghe port 8080 + GET /health trả 200.
FROM python:3.12-slim

# ffmpeg + ffprobe cho Producer (ghép clip + đọc metadata video)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài deps trước để tận dụng layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source (.dockerignore loại .venv / data_raw / .env ...)
COPY . .

EXPOSE 8080

# AgentBase route mọi traffic về 8080. Producer chạy job nền trong-process → 1 worker.
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
