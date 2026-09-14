FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# gunicorn + uvicorn worker: หลาย worker process รับ concurrent request ได้จริง
# ปรับ -w ตามจำนวน core ของเครื่อง (GPU embedding model โหลดแยกต่อ worker — ระวัง VRAM ถ้าตั้ง -w สูงบนเครื่อง GPU เดียว)
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "300"]
