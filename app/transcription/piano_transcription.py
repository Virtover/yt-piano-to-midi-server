from pathlib import Path
from urllib.request import urlretrieve

import librosa
import torch

from piano_transcription_inference import (
    PianoTranscription,
    sample_rate,
)


CHECKPOINT_DIR = Path("/data/models")

CHECKPOINT_PATH = (
    CHECKPOINT_DIR
    / "note_F1=0.9677_pedal_F1=0.9186.pth"
)

CHECKPOINT_URL = (
    "https://huggingface.co/xavriley/midi-transcription-models/"
    "resolve/main/note_F1%3D0.9677_pedal_F1%3D0.9186.pth"
)


def transcribe_piano(
    audio_path: Path,
    output_path: Path,
) -> Path:

    CHECKPOINT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not CHECKPOINT_PATH.exists():
        print("Downloading piano transcription checkpoint...")

        urlretrieve(
            CHECKPOINT_URL,
            CHECKPOINT_PATH,
        )

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print(f"Using {device} for inference")

    audio, _ = librosa.load(
        str(audio_path),
        sr=sample_rate,
        mono=True,
    )

    transcriptor = PianoTranscription(
        device=device,
        checkpoint_path=str(CHECKPOINT_PATH),
    )

    transcriptor.transcribe(
        audio,
        str(output_path),
    )

    if not output_path.exists():
        raise RuntimeError(
            "Piano transcription did not produce a MIDI file"
        )

    return output_path