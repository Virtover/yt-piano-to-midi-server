from fastapi import FastAPI
from fastapi import HTTPException
from redis import Redis

from app.api.routes.transcriptions import router
from app.config import settings

app = FastAPI(
    title="Piano Transcription Server",
    version="0.1.0",
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def readiness():
    try:
        Redis.from_url(settings.redis_url).ping()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Redis is unavailable") from error

    return {"status": "ready"}