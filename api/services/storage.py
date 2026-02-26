"""
S3 storage service — upload files and generate presigned URLs.
"""
from __future__ import annotations

import boto3
from botocore.client import Config

from api.settings import settings


def _s3_client():
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def upload_fileobj(file_obj, s3_key: str) -> str:
    """
    Stream *file_obj* directly to S3 at *s3_key*.

    Returns the S3 key on success.
    """
    client = _s3_client()
    client.upload_fileobj(file_obj, settings.s3_bucket_name, s3_key)
    return s3_key


def upload_file(local_path: str, s3_key: str) -> str:
    """
    Upload a local file at *local_path* to S3 at *s3_key*.

    Returns the S3 key on success.
    """
    client = _s3_client()
    client.upload_file(local_path, settings.s3_bucket_name, s3_key)
    return s3_key


def presigned_url(s3_key: str, expiry: int | None = None) -> str:
    """
    Generate a presigned GET URL for *s3_key*.

    *expiry* defaults to settings.presigned_url_expiry (1 hour).
    """
    expiry = expiry if expiry is not None else settings.presigned_url_expiry
    client = _s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": s3_key},
        ExpiresIn=expiry,
    )
