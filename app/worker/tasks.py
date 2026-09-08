import json
from pathlib import Path

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from redis import Redis

from app.config import settings


# Configure Dramatiq to use the Redis container.
broker = RedisBroker(
    url=settings.redis_url,
)

dramatiq.set_broker(broker)


# Redis client for storing job state.
redis = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
)


def job_key(job_id: str) -> str:
    return f"transcription:{job_id}"


def update_job(job_id: str, **values):
    redis.hset(
        job_key(job_id),
        mapping={
            key: json.dumps(value)
            if not isinstance(value, str)
            else value
            for key, value in values.items()
        },
    )


@dramatiq.actor
def transcribe_job(job_id: str, youtube_url: str):
    try:
        # Keep Basic Pitch out of the API image.
        from app.transcription.pipeline import transcribe_youtube

        update_job(
            job_id,
            status="processing",
            progress="0.0",
        )

        output_dir = (
            Path(settings.data_dir)
            / "jobs"
            / job_id
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        def progress(value: float):
            update_job(
                job_id,
                progress=str(value),
            )

        midi_path = transcribe_youtube(
            youtube_url=youtube_url,
            output_dir=output_dir,
            progress_callback=progress,
        )

        update_job(
            job_id,
            status="completed",
            progress="1.0",
            result=str(midi_path),
        )

    except Exception as e:
        update_job(
            job_id,
            status="failed",
            error=str(e),
        )