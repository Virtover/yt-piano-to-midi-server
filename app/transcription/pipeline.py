import subprocess
from pathlib import Path
from typing import Callable

from basic_pitch.inference import (
    ICASSP_2022_MODEL_PATH,
    predict_and_save,
)

from app.transcription.midi_cleanup import (
    merge_fragmented_notes,
)


ProgressCallback = Callable[[float], None]


def download_audio(
    youtube_url: str,
    output_dir: Path,
) -> Path:
    output_template = str(output_dir / "audio.%(ext)s")

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

    if progress_callback:
        progress_callback(0.05)

    # ---------------------------------------------------------
    # Download audio
    # ---------------------------------------------------------

    audio_path = download_audio(
        youtube_url,
        output_dir,
    )

    if progress_callback:
        progress_callback(0.25)

    # ---------------------------------------------------------
    # Basic Pitch
    # ---------------------------------------------------------

    midi_dir = output_dir / "midi"

    midi_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    predict_and_save(
        [str(audio_path)],
        str(midi_dir),

        save_midi=True,
        sonify_midi=False,
        save_model_outputs=False,
        save_notes=True,

        model_or_model_path=ICASSP_2022_MODEL_PATH,

        # Basic Pitch parameters
        onset_threshold=0.5,
        frame_threshold=0.3,
        minimum_note_length=127.7,
    )

    if progress_callback:
        progress_callback(0.85)

    # ---------------------------------------------------------
    # Find generated MIDI
    # ---------------------------------------------------------

    midi_files = list(
        midi_dir.glob("*.mid")
    )

    if not midi_files:
        raise RuntimeError(
            "Basic Pitch did not produce a MIDI file"
        )

    # Basic Pitch normally creates one MIDI file
    # for the input audio.
    midi_path = midi_files[0]

    # ---------------------------------------------------------
    # Clean up fragmented notes
    # ---------------------------------------------------------

    merge_fragmented_notes(
        midi_path,
        max_gap=0.05,
    )

    if progress_callback:
        progress_callback(0.95)

    # ---------------------------------------------------------
    # Move final result
    # ---------------------------------------------------------

    final_path = (
        output_dir / "transcription.mid"
    )

    midi_path.replace(final_path)

    if progress_callback:
        progress_callback(1.0)

    return final_path