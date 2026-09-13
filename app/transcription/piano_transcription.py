from pathlib import Path
from urllib.request import urlretrieve

import librosa
import numpy as np
import torch

from piano_transcription_inference import (
    PianoTranscription,
    sample_rate,
)
from piano_transcription_inference.pytorch_utils import (
    move_data_to_device,
)
from piano_transcription_inference.utilities import (
    RegressionPostProcessor,
    write_events_to_midi,
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

# Same model behavior as the upstream implementation.
SEGMENT_SAMPLES = 16000 * 10

# Keep this at 1 initially.
# The upstream implementation also uses batch_size=1.
INFERENCE_BATCH_SIZE = 1


def transcribe_piano(
    audio_path: Path,
    output_path: Path,
    progress_callback=None,
) -> Path:

    CHECKPOINT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------
    # Checkpoint
    # ---------------------------------------------------------

    if not CHECKPOINT_PATH.exists():
        print("Downloading piano transcription checkpoint...")

        urlretrieve(
            CHECKPOINT_URL,
            CHECKPOINT_PATH,
        )

    # ---------------------------------------------------------
    # Device
    # ---------------------------------------------------------

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print(f"Using {device} for inference")

    # ---------------------------------------------------------
    # Load audio
    # ---------------------------------------------------------

    audio, _ = librosa.load(
        str(audio_path),
        sr=sample_rate,
        mono=True,
    )

    if progress_callback:
        progress_callback(0.30)

    # ---------------------------------------------------------
    # Create transcriptor
    # ---------------------------------------------------------

    transcriptor = PianoTranscription(
        device=device,
        checkpoint_path=str(CHECKPOINT_PATH),
    )

    if progress_callback:
        progress_callback(0.35)

    # ---------------------------------------------------------
    # Prepare audio exactly like the upstream implementation
    # ---------------------------------------------------------

    audio = audio[None, :]

    audio_len = audio.shape[1]

    pad_len = (
        int(np.ceil(audio_len / SEGMENT_SAMPLES))
        * SEGMENT_SAMPLES
        - audio_len
    )

    audio = np.concatenate(
        (
            audio,
            np.zeros((1, pad_len)),
        ),
        axis=1,
    )

    segments = transcriptor.enframe(
        audio,
        SEGMENT_SAMPLES,
    )

    total_segments = segments.shape[0]

    print(
        f"Transcribing {total_segments} segments"
    )

    # ---------------------------------------------------------
    # Run inference segment by segment
    # ---------------------------------------------------------

    output_chunks = []

    device = next(
        transcriptor.model.parameters()
    ).device

    for start in range(
        0,
        total_segments,
        INFERENCE_BATCH_SIZE,
    ):
        end = min(
            start + INFERENCE_BATCH_SIZE,
            total_segments,
        )

        batch = segments[start:end]

        batch_tensor = move_data_to_device(
            batch,
            device,
        )

        with torch.no_grad():
            transcriptor.model.eval()

            batch_output = transcriptor.model(
                batch_tensor
            )

        batch_output = {
            key: value.detach()
            .cpu()
            .numpy()
            for key, value in batch_output.items()
        }

        if not output_chunks:
            output_chunks = {
                key: []
                for key in batch_output
            }

        for key, value in batch_output.items():
            output_chunks[key].append(value)

        completed = end

        inference_progress = (
            completed / total_segments
        )

        # Inference occupies 35% -> 85%.
        progress = (
            0.35
            + inference_progress * 0.50
        )

        if progress_callback:
            progress_callback(progress)

        print(
            f"Inference: "
            f"{completed}/{total_segments} "
            f"({inference_progress * 100:.1f}%)"
        )

    # ---------------------------------------------------------
    # Combine segment outputs
    # ---------------------------------------------------------

    output_dict = {
        key: np.concatenate(
            values,
            axis=0,
        )
        for key, values in output_chunks.items()
    }

    # ---------------------------------------------------------
    # Deframe
    # ---------------------------------------------------------

    for key in output_dict:
        output_dict[key] = (
            transcriptor.deframe(
                output_dict[key]
            )[0:audio_len]
        )

    if progress_callback:
        progress_callback(0.88)

    # ---------------------------------------------------------
    # Post-processing
    # ---------------------------------------------------------

    post_processor = RegressionPostProcessor(
        transcriptor.frames_per_second,
        classes_num=transcriptor.classes_num,
        onset_threshold=transcriptor.onset_threshold,
        offset_threshold=transcriptor.offset_threshod,
        frame_threshold=transcriptor.frame_threshold,
        pedal_offset_threshold=(
            transcriptor.pedal_offset_threshold
        ),
    )

    (
        est_note_events,
        est_pedal_events,
    ) = post_processor.output_dict_to_midi_events(
        output_dict
    )

    if progress_callback:
        progress_callback(0.93)

    # ---------------------------------------------------------
    # Write MIDI
    # ---------------------------------------------------------

    write_events_to_midi(
        start_time=0,
        note_events=est_note_events,
        pedal_events=est_pedal_events,
        midi_path=str(output_path),
    )

    if progress_callback:
        progress_callback(0.98)

    # ---------------------------------------------------------
    # Verify
    # ---------------------------------------------------------

    if not output_path.exists():
        raise RuntimeError(
            "Piano transcription did not produce a MIDI file"
        )

    if output_path.stat().st_size == 0:
        raise RuntimeError(
            "Piano transcription produced an empty MIDI file"
        )

    if progress_callback:
        progress_callback(1.0)

    return output_path