import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.transcription.piano_transcription import (
    transcribe_piano,
)


ProgressCallback = Callable[[float], None]
MetadataCallback = Callable[[dict[str, Any]], None]


@dataclass
class DownloadedAudio:
    path: Path
    metadata: dict[str, Any]


def download_audio(
    source_url: str,
    output_dir: Path,
) -> DownloadedAudio:
    output_template = str(
        output_dir / "download.%(ext)s"
    )

    result = subprocess.run(
        [
            "yt-dlp",
            "--print-json",
            "-x",
            "--audio-format",
            "wav",
            "-o",
            output_template,
            source_url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    json_lines = [
        line
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    if not json_lines:
        raise RuntimeError(
            "yt-dlp did not return video metadata"
        )

    try:
        info = json.loads(json_lines[-1])
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "yt-dlp returned invalid video metadata"
        ) from error

    title = info.get("title")

    if not title:
        raise RuntimeError(
            "yt-dlp did not return a video title"
        )

    downloaded_path = None

    for path in output_dir.glob("download.*"):
        if path.suffix.lower() == ".wav":
            downloaded_path = path
            break

    if downloaded_path is None:
        raise RuntimeError(
            "yt-dlp did not produce a WAV file"
        )

    wav_path = output_dir / "audio.wav"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(downloaded_path),
            "-ar",
            "44100",
            "-ac",
            "1",
            str(wav_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    downloaded_path.unlink()

    return DownloadedAudio(
        path=wav_path,
        metadata={
            "title": title,
            "author": info.get("uploader") or info.get("channel"),
            "channel": info.get("channel"),
            "channel_id": info.get("channel_id"),
            "channel_url": info.get("channel_url"),
            "upload_date": format_upload_date(info.get("upload_date")),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url") or source_url,
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
        },
    )


def format_upload_date(value: str | None) -> str | None:
    if not value or len(value) != 8 or not value.isdigit():
        return None

    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def transcribe_source(
    source_url: str,
    output_dir: Path,
    progress_callback: ProgressCallback | None = None,
    metadata_callback: MetadataCallback | None = None,
) -> Path:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if progress_callback:
        progress_callback(0.05)

    downloaded = download_audio(
        source_url,
        output_dir,
    )

    if metadata_callback:
        metadata_callback(downloaded.metadata)

    midi_path = (
        output_dir
        / "transcription.mid"
    )

    transcribe_piano(
        audio_path=downloaded.path,
        output_path=midi_path,
        progress_callback=progress_callback,
    )

    if not midi_path.exists():
        raise RuntimeError(
            "Piano transcription did not "
            "produce a MIDI file"
        )

    if midi_path.stat().st_size == 0:
        raise RuntimeError(
            "Piano transcription produced "
            "an empty MIDI file"
        )

    if progress_callback:
        progress_callback(1.0)

    return midi_path