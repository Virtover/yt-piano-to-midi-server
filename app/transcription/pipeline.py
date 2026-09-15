import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.transcription.piano_transcription import (
    transcribe_piano,
)


ProgressCallback = Callable[[float], None]
TitleCallback = Callable[[str], None]


@dataclass
class DownloadedAudio:
    path: Path
    title: str


def download_audio(
    youtube_url: str,
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
            youtube_url,
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
        title=title,
    )


def transcribe_youtube(
    youtube_url: str,
    output_dir: Path,
    progress_callback: ProgressCallback | None = None,
    title_callback: TitleCallback | None = None,
) -> Path:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if progress_callback:
        progress_callback(0.05)

    downloaded = download_audio(
        youtube_url,
        output_dir,
    )

    if title_callback:
        title_callback(
            downloaded.title
        )

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