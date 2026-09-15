FROM python:3.11-slim

RUN pip install --no-cache-dir mlflow==2.16.2 psycopg2-binary==2.9.9 boto3==1.35.24

EXPOSE 5000

# shell form (ไม่ใช่ exec array) เพราะต้อง expand ${VAR} จาก environment ตอน container start
CMD mlflow server \
    --backend-store-uri postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${MLFLOW_DB} \
    --default-artifact-root s3://${MLFLOW_BUCKET}/ \
    --host 0.0.0.0 --port 5000
