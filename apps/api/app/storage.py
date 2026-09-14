import boto3
from botocore.client import Config

from app.config import settings


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint_url,
        aws_access_key_id=settings.minio_root_user,
        aws_secret_access_key=settings.minio_root_password,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def presigned_put_url(storage_key: str, expires_in: int = 3600) -> str:
    return s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.minio_bucket, "Key": storage_key},
        ExpiresIn=expires_in,
    )


def presigned_get_url(storage_key: str, expires_in: int = 3600) -> str:
    return s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.minio_bucket, "Key": storage_key},
        ExpiresIn=expires_in,
    )
