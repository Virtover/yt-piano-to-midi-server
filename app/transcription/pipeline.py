import subprocess
from pathlib import Path
from typing import Callable

from app.transcription.piano_transcription import (
    transcribe_piano,
)


ProgressCallback = Callable[[float], None]


def download_audio(
    youtube_url: str,
    output_dir: Path,
) -> Path:
    output_template = str(
        output_dir / "audio.%(ext)s"
    )

    subprocess.run(
        [
            "yt-dlp",
            "-x",
            "--audio-format",
            "wav",
            "-o",
            output_template,
            youtube_url,
        ],
        check=True,
    )

    wav_path = output_dir / "audio.wav"

    if not wav_path.exists():
        raise RuntimeError(
            "yt-dlp did not produce audio.wav"
        )

    return wav_path


def transcribe_youtube(
    youtube_url: str,
    output_dir: Path,
    progress_callback: ProgressCallback | None = None,
) -> Path:

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------
    # Download audio
    # ---------------------------------------------------------

    if progress_callback:
        progress_callback(0.05)

    audio_path = download_audio(
        youtube_url,
        output_dir,
    )

    if progress_callback:
        progress_callback(0.25)

    # ---------------------------------------------------------
    # Piano transcription
    # ---------------------------------------------------------

    midi_path = (
        output_dir / "transcription.mid"
    )

    transcribe_piano(
        audio_path=audio_path,
        output_path=midi_path,
    )

    if progress_callback:
        progress_callback(0.95)

    # ---------------------------------------------------------
    # Verify result
    # ---------------------------------------------------------

    if not midi_path.exists():
        raise RuntimeError(
            "Piano transcription did not produce a MIDI file"
        )

    if midi_path.stat().st_size == 0:
        raise RuntimeError(
            "Piano transcription produced an empty MIDI file"
        )

    if progress_callback:
        progress_callback(1.0)

    return midi_path