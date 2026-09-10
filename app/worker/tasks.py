import json
import shutil
from pathlib import Path

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from redis import Redis

from app.config import settings


JOB_TTL = 60 * 60  # 1 hour


broker = RedisBroker(
    url=settings.redis_url,
)

dramatiq.set_broker(broker)


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


def cleanup_expired_jobs():
    jobs_dir = Path(settings.data_dir) / "jobs"

    if not jobs_dir.exists():
        return

    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue

        job_id = job_dir.name

        if not redis.exists(job_key(job_id)):
            shutil.rmtree(job_dir)
            print(f"Removed expired job: {job_id}")


@dramatiq.actor
def transcribe_job(job_id: str, youtube_url: str):
    try:
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

        redis.expire(
            job_key(job_id),
            JOB_TTL,
        )

    except Exception as e:
        update_job(
            job_id,
            status="failed",
            error=str(e),
        )

        redis.expire(
            job_key(job_id),
            JOB_TTL,
        )