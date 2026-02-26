"""
Application settings loaded from environment variables via Pydantic BaseSettings.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "tennis-coach-videos"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/tennis_coach"

    # Job TTL in seconds (24 hours)
    job_ttl: int = 86400

    # Presigned URL expiry in seconds (1 hour)
    presigned_url_expiry: int = 3600

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Module-level singleton
settings = Settings()  # type: ignore[call-arg]
