import io
import uuid

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings

_client = None


def get_client():
    global _client
    if _client is None:
        scheme = "https" if settings.minio_secure else "http"
        _client = boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_root_user,
            aws_secret_access_key=settings.minio_root_password,
            config=BotoConfig(signature_version="s3v4"),
        )
    return _client


def ensure_bucket() -> None:
    client = get_client()
    try:
        client.head_bucket(Bucket=settings.minio_bucket)
    except ClientError:
        client.create_bucket(Bucket=settings.minio_bucket)


def upload_bytes(data: bytes, filename: str, content_type: str) -> str:
    key = f"{uuid.uuid4()}/{filename}"
    get_client().upload_fileobj(
        io.BytesIO(data),
        settings.minio_bucket,
        key,
        ExtraArgs={"ContentType": content_type or "application/octet-stream"},
    )
    return key


def download_bytes(key: str) -> bytes:
    buf = io.BytesIO()
    get_client().download_fileobj(settings.minio_bucket, key, buf)
    return buf.getvalue()
