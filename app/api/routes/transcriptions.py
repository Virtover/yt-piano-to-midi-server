import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl
from redis import Redis

from app.config import settings
from app.worker.tasks import (
    job_key,
    transcribe_job,
)


router = APIRouter(
    prefix="/transcriptions",
    tags=["transcriptions"],
)

redis = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
)


class CreateTranscriptionRequest(BaseModel):
    youtube_url: HttpUrl


class CreateTranscriptionResponse(BaseModel):
    job_id: str
    status: str


class TranscriptionStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float = Field(ge=0, le=1)
    error: str | None = None


@router.post(
    "",
    response_model=CreateTranscriptionResponse,
    status_code=202,
)
def create_transcription(
    request: CreateTranscriptionRequest,
):
    job_id = str(uuid.uuid4())

    redis.hset(
        job_key(job_id),
        mapping={
            "status": "queued",
            "progress": "0.0",
            "youtube_url": str(request.youtube_url),
        },
    )

    try:
        transcribe_job.send(job_id, str(request.youtube_url))
    except Exception as error:
        redis.delete(job_key(job_id))
        raise HTTPException(
            status_code=503,
            detail="The transcription worker is unavailable",
        ) from error

    return CreateTranscriptionResponse(
        job_id=job_id,
        status="queued",
    )


@router.get("/{job_id}", response_model=TranscriptionStatusResponse)
def get_transcription(job_id: str):
    job = redis.hgetall(job_key(job_id))

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Transcription job not found",
        )

    try:
        progress = float(job.get("progress", 0))
    except ValueError:
        progress = 0

    return TranscriptionStatusResponse(
        job_id=job_id,
        status=job.get("status", "unknown"),
        progress=max(0, min(1, progress)),
        error=job.get("error"),
    )


@router.get("/{job_id}/midi")
def get_midi(job_id: str):
    job = redis.hgetall(job_key(job_id))

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Transcription job not found",
        )

    if job.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail="Transcription is not completed",
        )

    path = job.get("result")

    if not path:
        raise HTTPException(status_code=500, detail="Result path missing")

    result_path = Path(path)
    data_root = Path(settings.data_dir).resolve()
    try:
        result_path.resolve().relative_to(data_root)
    except ValueError as error:
        raise HTTPException(status_code=500, detail="Invalid result path") from error

    if not result_path.is_file():
        raise HTTPException(status_code=404, detail="MIDI result is no longer available")

    return FileResponse(
        result_path,
        media_type="audio/midi",
        filename="transcription.mid",
    )