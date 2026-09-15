FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8001

# worker เดียวพอ (-w 1) — pipeline หนักที่ embedding model ต่อ container อยู่แล้ว รัน worker เดียว
# กัน VRAM ชนกันเองถ้ามี GPU (เทียบ backend Dockerfile ที่ concurrent request เยอะกว่าเลย -w 2)
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "1", "-b", "0.0.0.0:8001", "--timeout", "300"]
