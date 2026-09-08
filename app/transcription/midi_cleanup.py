from pathlib import Path

import pretty_midi


def merge_fragmented_notes(
    midi_path: Path,
    max_gap: float = 0.05,
) -> None:
    """
    Merge very short gaps between notes of the same pitch.

    Basic Pitch can occasionally split a sustained note into multiple
    MIDI notes because of tiny detection gaps.

    max_gap is in seconds.
    """

    midi = pretty_midi.PrettyMIDI(str(midi_path))

    for instrument in midi.instruments:
        notes_by_pitch: dict[int, list[pretty_midi.Note]] = {}

        for note in instrument.notes:
            notes_by_pitch.setdefault(note.pitch, []).append(note)

        merged_notes: list[pretty_midi.Note] = []

        for pitch_notes in notes_by_pitch.values():
            pitch_notes.sort(key=lambda note: note.start)

            current = None

            for note in pitch_notes:
                if current is None:
                    current = note
                    continue

                gap = note.start - current.end

                if 0 <= gap <= max_gap:
                    # Treat this as a detection dropout rather
                    # than a new note.
                    current.end = max(current.end, note.end)
                    current.velocity = max(
                        current.velocity,
                        note.velocity,
                    )
                else:
                    merged_notes.append(current)
                    current = note

            if current is not None:
                merged_notes.append(current)

        # Keep the original ordering used by MIDI.
        merged_notes.sort(
            key=lambda note: (note.start, note.pitch)
        )

        instrument.notes = merged_notes

    midi.write(str(midi_path))