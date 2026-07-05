FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      libglib2.0-0 \
      libsm6 \
      libxext6 \
      libxrender1 \
      libgl1 \
      fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN python -c "import cv2; from pathlib import Path; assert hasattr(cv2, 'CascadeClassifier'), f'OpenCV objdetect missing: {getattr(cv2, \"__file__\", \"unknown\")}'; haar=getattr(getattr(cv2, 'data', None), 'haarcascades', ''); assert haar and Path(haar, 'haarcascade_frontalface_default.xml').exists(), f'OpenCV haarcascades missing: {haar}'"

COPY . .

RUN mkdir -p /app/data/downloads /app/data/outputs /app/data/state

VOLUME ["/app/data"]
EXPOSE 8000

CMD ["python", "-m", "app.main"]
