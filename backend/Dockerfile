# VNG Insider — backend (FastAPI + ffmpeg) cho AgentBase Runtime.
# Contract AgentBase: nghe port 8080 + GET /health trả 200.
FROM python:3.12-slim

# ffmpeg + ffprobe cho Producer (ghép clip + đọc metadata video)
# fonts-liberation (Arial-compatible) + fonts-dejavu-core (đủ dấu Việt) cho phụ đề:
# slim KHÔNG có font hệ thống → PIL render phụ đề rớt về default bitmap (nhỏ xíu).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài deps trước để tận dụng layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browser cho chế độ "Video thông tin" (event_game/render_capture.py
# p.chromium.launch headless). slim KHÔNG có sẵn browser → launch lỗi
# "Executable doesn't exist". --with-deps cài luôn OS libs chromium cần
# (libnss3, libgbm, libasound2...). Phải chạy SAU khi pip cài playwright.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy source (.dockerignore loại .venv / data_raw / .env ...)
COPY . .

EXPOSE 8080

# AgentBase route mọi traffic về 8080. Producer chạy job nền trong-process → 1 worker.
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
