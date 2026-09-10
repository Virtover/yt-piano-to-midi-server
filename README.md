# YouTube Piano to MIDI Server

A small FastAPI service that downloads a YouTube piano performance, transcribes it with Basic Pitch, and returns a MIDI file asynchronously.

## Requirements

- Docker Desktop with Docker Compose and Linux containers enabled
- NVIDIA drivers and NVIDIA Container Toolkit, because the worker runs in a CUDA image and requests all GPUs
- A public YouTube URL containing an audio or piano performance

The transcription worker needs `ffmpeg`, which is included in the worker image. Redis stores job state; generated files are stored in the shared `data` volume.

The worker is configured for GPU execution through `gpus: all` in `docker-compose.yml`. Verify that Docker can access the GPU before starting the stack:

```powershell
docker run --rm --gpus all nvidia/cuda:12.6.0-cudnn-runtime-ubuntu22.04 nvidia-smi
```

If you do not have an NVIDIA GPU, remove `gpus: all` from the worker service and expect transcription to run more slowly. The CUDA-based worker image may still require additional CPU-only dependency changes depending on the host.

## Run locally with Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The included `.env.example` is already configured for Docker Compose. Keep `REDIS_URL` set to `redis://redis:6379/0` and `DATA_DIR` set to `/data` unless the Compose file is changed to use different service or volume settings. Do not commit local secrets or machine-specific values from `.env`.

The API is available at `http://localhost:8000`. Interactive API documentation is at `http://localhost:8000/docs`.

Check service health:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
```

## API

### Create a transcription

```powershell
$job = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/transcriptions `
  -ContentType 'application/json' `
  -Body '{"youtube_url":"https://www.youtube.com/watch?v=VIDEO_ID"}'
$job
```

The endpoint returns `202 Accepted` with a `job_id` and an initial `queued` status. The URL must be an HTTP(S) URL. The worker downloads the audio and runs Basic Pitch, so processing time depends on the track length and available CPU.

### Poll status

```powershell
Invoke-RestMethod "http://localhost:8000/api/transcriptions/$($job.job_id)"
```

The status response contains `status`, `progress` from `0` to `1`, and an `error` field when processing fails. Possible statuses are `queued`, `processing`, `completed`, and `failed`.

Poll until the status is `completed` or `failed`:

```powershell
do {
  $status = Invoke-RestMethod "http://localhost:8000/api/transcriptions/$($job.job_id)"
  $status
  if ($status.status -in @('completed', 'failed')) { break }
  Start-Sleep -Seconds 2
} while ($true)
```

### Download MIDI

After the status is `completed`:

```powershell
Invoke-WebRequest `
  -Uri "http://localhost:8000/api/transcriptions/$($job.job_id)/midi" `
  -OutFile transcription.mid
```

The download endpoint returns `409` while processing, `404` for an unknown job or missing result, and `500` if the stored result metadata is invalid.

## Configuration

Settings are read from environment variables (or `.env`):

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `DATA_DIR` | `/data` | Directory for job output files |

Compose overrides these values to use the Redis service and shared `/data` volume. The API and worker must use the same `DATA_DIR`.

## Development checks

Run the syntax check from the repository root:

```powershell
python -m compileall -q app
```

Install `requirements.api.txt` for API-only development or `requirements.worker.txt` for transcription-worker development. Running the complete stack with Docker is recommended because the worker also requires `ffmpeg` and a running Redis instance.

## Architecture

- `app/main.py`: FastAPI application and health endpoints
- `app/api/routes/transcriptions.py`: job creation, status polling, and MIDI download
- `app/worker/tasks.py`: Redis-backed Dramatiq task and job state updates
- `app/transcription/pipeline.py`: YouTube download and Basic Pitch transcription
- `app/transcription/piano_transcription.py`: piano transcription model integration
- `docker-compose.yml`: API, worker, Redis, and shared storage

## Limitations

This is an asynchronous transcription service, not a sheet-music editor. Basic Pitch output can require cleanup for dense arrangements, multiple instruments, or noisy recordings. Jobs and generated files currently remain in Redis and the data volume until they are removed manually.
