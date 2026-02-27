"""
Cloudflare R2 storage service — upload files and generate presigned URLs.

R2 is S3-compatible; boto3 is used with a custom endpoint URL.
"""
from __future__ import annotations

import boto3
from botocore.client import Config

from api.settings import settings


def _r2_client():
    endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def upload_fileobj(file_obj, s3_key: str) -> str:
    """
    Stream *file_obj* directly to R2 at *s3_key*.

    Returns the key on success.
    """
    client = _r2_client()
    client.upload_fileobj(file_obj, settings.r2_bucket_name, s3_key)
    return s3_key


def upload_file(local_path: str, s3_key: str) -> str:
    """
    Upload a local file at *local_path* to R2 at *s3_key*.

    Returns the key on success.
    """
    client = _r2_client()
    client.upload_file(local_path, settings.r2_bucket_name, s3_key)
    return s3_key


def presigned_url(s3_key: str, expiry: int | None = None) -> str:
    """
    Generate a presigned GET URL for *s3_key*.

    *expiry* defaults to settings.presigned_url_expiry (1 hour).
    """
    expiry = expiry if expiry is not None else settings.presigned_url_expiry
    client = _r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": s3_key},
        ExpiresIn=expiry,
    )


def delete_object(s3_key: str) -> None:
    """Delete a single object from R2."""
    client = _r2_client()
    client.delete_object(Bucket=settings.r2_bucket_name, Key=s3_key)
