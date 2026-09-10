# YouTube Piano to MIDI Server

A small FastAPI service that downloads a YouTube piano performance, transcribes it to MIDI asynchronously, and returns the resulting MIDI file.

The transcription uses a dedicated piano transcription model with CUDA support when an NVIDIA GPU is available.

## Requirements

* Docker Desktop with Docker Compose and Linux containers enabled
* NVIDIA drivers and NVIDIA Container Toolkit, because the transcription worker uses a CUDA image and requests all GPUs
* A public YouTube URL containing an audio or piano performance

The transcription worker needs `ffmpeg`, which is included in the worker image.

Redis stores job state, while generated files are stored in the shared `data` volume.

The worker is configured for GPU execution through `gpus: all` in `docker-compose.yml`.

Verify that Docker can access the GPU before starting the stack:

```powershell
docker run --rm --gpus all nvidia/cuda:12.6.0-cudnn-runtime-ubuntu22.04 nvidia-smi
```

If you do not have an NVIDIA GPU, remove `gpus: all` from the worker service and expect transcription to run more slowly. The CUDA-based worker image may still require additional CPU-only dependency changes depending on the host.

## Run locally with Docker

```powershell
Copy-Item .env.example .env

docker compose up --build
```

The included `.env.example` is already configured for Docker Compose.

Keep:

```env
REDIS_URL=redis://redis:6379/0
DATA_DIR=/data
```

unless the Compose configuration is changed to use different service or volume settings.

Do not commit local secrets or machine-specific values from `.env`.

The API is available at:

`http://localhost:8000`

Interactive API documentation:

`http://localhost:8000/docs`

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

The endpoint returns `202 Accepted` with a `job_id` and an initial `queued` status.

The URL must be an HTTP(S) URL.

The worker downloads the audio and runs the piano transcription model. Processing time depends on the track length and available hardware.

### Poll status

```powershell
Invoke-RestMethod "http://localhost:8000/api/transcriptions/$($job.job_id)"
```

The status response contains:

* `status`
* `progress` from `0` to `1`
* `error` when processing fails

Possible statuses are:

* `queued`
* `processing`
* `completed`
* `failed`

Poll until the status is `completed` or `failed`:

```powershell
do {
    $status = Invoke-RestMethod `
        "http://localhost:8000/api/transcriptions/$($job.job_id)"

    $status

    if ($status.status -in @('completed', 'failed')) {
        break
    }

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

The download endpoint returns:

* `409` while transcription is still processing
* `404` for an unknown job or missing result
* `500` if the stored result metadata is invalid

Completed and failed jobs are retained for a limited time and are then automatically removed.

## Configuration

Settings are read from environment variables or `.env`:

| Variable    | Default                    | Description                    |
| ----------- | -------------------------- | ------------------------------ |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL           |
| `DATA_DIR`  | `/data`                    | Directory for job output files |

Docker Compose overrides these values to use the Redis service and the shared `/data` volume.

The API, worker, and cleanup service must use the same `DATA_DIR`.

## Job cleanup

Job state is stored in Redis and generated files are stored under:

```text
/data/jobs/<job_id>/
```

Jobs are not given a Redis expiration while they are queued or being processed. This prevents a long-running transcription from disappearing simply because no progress update occurred for some time.

When a transcription finishes successfully or fails, its Redis key receives a one-hour TTL.

A separate cleanup service periodically scans the jobs directory. If the corresponding Redis key no longer exists, the cleanup service removes the job directory and its generated files.

The cleanup process runs independently from the transcription worker.

The cleanup interval is currently 10 minutes, so files may remain for a short period after their one-hour retention period expires.

## Development checks

Run the syntax check from the repository root:

```powershell
python -m compileall -q app
```

Install `requirements.api.txt` for API-only development or `requirements.worker.txt` for transcription-worker development.

Running the complete stack with Docker is recommended because the worker also requires:

* `ffmpeg`
* Redis
* the piano transcription model
* PyTorch with CUDA support when using the GPU configuration

## Architecture

```text
                    ┌──────────────┐
                    │    Client    │
                    └──────┬───────┘
                           │ HTTP
                           ▼
                    ┌──────────────┐
                    │   FastAPI    │
                    │     API      │
                    └──────┬───────┘
                           │
                           │ enqueue
                           ▼
                    ┌──────────────┐
                    │    Redis     │
                    │   job state  │
                    └──────┬───────┘
                           │
                           │ Dramatiq
                           ▼
                    ┌──────────────┐
                    │    Worker    │
                    │    CUDA      │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Shared data  │
                    │    volume    │
                    └──────────────┘
                           ▲
                           │
                    ┌──────┴───────┐
                    │   Cleanup    │
                    │   service    │
                    └──────────────┘
```

### Components

* `app/main.py` — FastAPI application and health endpoints
* `app/api/routes/transcriptions.py` — job creation, status polling, and MIDI download
* `app/worker/tasks.py` — Dramatiq transcription task, Redis job state, and cleanup logic
* `app/worker/cleanup.py` — periodic cleanup process
* `app/transcription/pipeline.py` — YouTube audio download and transcription pipeline
* `app/transcription/piano_transcription.py` — piano transcription model integration
* `docker-compose.yml` — API, worker, cleanup, Redis, and shared storage

## Limitations

This is an asynchronous transcription service, not a sheet-music editor.

Transcription quality depends heavily on the source recording. Dense arrangements, multiple instruments, background noise, sustain-pedal effects, and recordings with significant reverberation can result in incorrect or missing notes.

The generated MIDI may require manual cleanup before being used as a final piano arrangement.

The current API accepts a YouTube URL and returns a MIDI file; it does not yet provide interactive editing, sheet-music generation, playback controls, or MIDI performance feedback.
