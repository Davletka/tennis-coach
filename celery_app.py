"""
Celery application instance.

Import this module to get the configured Celery app.
"""
from celery import Celery

from api.settings import settings

app = Celery(
    "tennis_coach",
    broker=settings.redis_url,
    backend=None,  # We manage job state in Redis directly via job_store
    include=["api.tasks.analyze"],
)

app.conf.update(
    # One heavy video job per worker at a time
    worker_prefetch_multiplier=1,
    # Re-queue if worker crashes mid-analysis
    task_acks_late=True,
    # Disable the Celery result backend (state lives in job_store)
    task_ignore_result=True,
    # Serialize tasks as JSON
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
