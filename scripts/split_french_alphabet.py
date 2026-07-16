#!/usr/bin/env python3
"""Split a French alphabet recording into A-Z audio files.

The script intentionally depends only on Python's standard library plus FFmpeg.
It trims the recording once near the beginning of the alphabet, detects pauses
with FFmpeg's ``silencedetect`` filter, then exports the first 26 detected speech
segments as A.wav through Z.wav.

Example from the SummerDay repository root:

    uv run python scripts/split_french_alphabet.py \
        data/source/french_alphabet.wav \
        --start 21.0 \
        --output-dir data/media/alphabet \
        --force

If the crop still contains one spoken introduction before A, add ``--skip 1``.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

LETTERS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
SAMPLE_RATE = 16_000

SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class Interval:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Split the first 26 spoken segments after an approximate start time "
            "into French alphabet files A-Z."
        )
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Source audio or video file, such as WAV, M4A, MP3, or WEBM.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/media/alphabet"),
        help="Output directory. Default: data/media/alphabet",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=21.0,
        help=(
            "Approximate absolute start time of the alphabet section, in seconds. "
            "Default: 21.0"
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help=(
            "Optional maximum duration to analyze after --start. The script can "
            "normally ignore the outro automatically, so this is usually omitted."
        ),
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help=(
            "Number of detected speech segments to ignore before assigning A. "
            "Use 1 if a short introduction remains after --start. Default: 0"
        ),
    )
    parser.add_argument(
        "--noise-db",
        type=float,
        default=-35.0,
        help=(
            "FFmpeg silence threshold in dB. More negative is more sensitive to "
            "quiet sound. Default: -35"
        ),
    )
    parser.add_argument(
        "--min-silence",
        type=float,
        default=0.18,
        help=(
            "Minimum silence duration that separates two letters, in seconds. "
            "Default: 0.18"
        ),
    )
    parser.add_argument(
        "--min-speech",
        type=float,
        default=0.12,
        help=(
            "Discard detected speech intervals shorter than this, in seconds. "
            "Default: 0.12"
        ),
    )
    parser.add_argument(
        "--pad",
        type=float,
        default=0.08,
        help=(
            "Extra audio retained before and after each detected letter, in seconds. "
            "Padding is limited so adjacent files never overlap. Default: 0.08"
        ),
    )
    parser.add_argument(
        "--following-gap",
        type=float,
        default=0.1,
        help="Silence retained before the next letter starts. Default: 0.1",
    )
    parser.add_argument(
        "--final-tail",
        type=float,
        default=0.2,
        help="Extra audio retained after Z. Default: 0.2",
    )
    parser.add_argument(
        "--volume",
        type=float,
        default=1.2,
        help="FFmpeg volume multiplier applied to each letter. Default: 1.2",
    )
    parser.add_argument(
        "--format",
        choices=("wav", "mp3"),
        default="wav",
        dest="output_format",
        help="Output format. Default: wav",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing A-Z files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show detected segments without exporting audio files.",
    )
    parser.add_argument(
        "--keep-analysis-wav",
        action="store_true",
        help="Keep the trimmed 16 kHz mono WAV in the output directory.",
    )
    return parser.parse_args()


def run(
    command: Sequence[str],
    *,
    capture: bool = False,
    quiet: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else (subprocess.DEVNULL if quiet else None),
            stderr=subprocess.PIPE if capture else (subprocess.DEVNULL if quiet else None),
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        details = ""
        if exc.stderr:
            details = f"\n{exc.stderr.strip()}"
        raise RuntimeError(
            f"Command failed with exit code {exc.returncode}:\n"
            f"{' '.join(command)}{details}"
        ) from exc


def require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            "Missing required command(s): "
            + ", ".join(missing)
            + ". Install FFmpeg first, for example: sudo apt install ffmpeg"
        )


def validate_args(args: argparse.Namespace) -> None:
    if not args.source.is_file():
        raise FileNotFoundError(f"Source file not found: {args.source.resolve()}")
    if args.start < 0:
        raise ValueError("--start cannot be negative.")
    if args.duration is not None and args.duration <= 0:
        raise ValueError("--duration must be greater than zero.")
    if args.skip < 0:
        raise ValueError("--skip cannot be negative.")
    if args.min_silence <= 0:
        raise ValueError("--min-silence must be greater than zero.")
    if args.min_speech <= 0:
        raise ValueError("--min-speech must be greater than zero.")
    if args.pad < 0:
        raise ValueError("--pad cannot be negative.")
    if args.following_gap < 0:
        raise ValueError("--following-gap cannot be negative.")
    if args.final_tail < 0:
        raise ValueError("--final-tail cannot be negative.")
    if args.volume <= 0:
        raise ValueError("--volume must be greater than zero.")


def convert_for_analysis(
    source: Path,
    destination: Path,
    *,
    start: float,
    duration: float | None,
) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
    ]
    if duration is not None:
        command.extend(["-t", f"{duration:.3f}"])
    command.extend(
        [
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]
    )
    print(f"Preparing analysis audio from {start:.3f}s...")
    run(command)


def probe_duration(path: Path) -> float:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture=True,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Unable to read duration for {path}") from exc
    if duration <= 0:
        raise RuntimeError(f"Invalid audio duration for {path}: {duration}")
    return duration


def detect_silences(
    path: Path,
    *,
    noise_db: float,
    min_silence: float,
    duration: float,
) -> list[Interval]:
    result = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise_db:g}dB:d={min_silence:g}",
            "-f",
            "null",
            "-",
        ],
        capture=True,
    )

    silences: list[Interval] = []
    pending_start: float | None = None

    for line in result.stderr.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            pending_start = max(0.0, float(start_match.group(1)))

        end_match = SILENCE_END_RE.search(line)
        if end_match:
            end = min(duration, max(0.0, float(end_match.group(1))))
            start = 0.0 if pending_start is None else pending_start
            if end > start:
                silences.append(Interval(start, end))
            pending_start = None

    if pending_start is not None and pending_start < duration:
        silences.append(Interval(pending_start, duration))

    silences.sort(key=lambda interval: interval.start)
    return merge_intervals(silences)


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    if not intervals:
        return []

    merged: list[Interval] = [intervals[0]]
    for interval in intervals[1:]:
        previous = merged[-1]
        if interval.start <= previous.end:
            merged[-1] = Interval(previous.start, max(previous.end, interval.end))
        else:
            merged.append(interval)
    return merged


def speech_from_silences(
    silences: list[Interval],
    *,
    duration: float,
    min_speech: float,
) -> list[Interval]:
    speech: list[Interval] = []
    cursor = 0.0

    for silence in silences:
        if silence.start > cursor:
            interval = Interval(cursor, silence.start)
            if interval.duration >= min_speech:
                speech.append(interval)
        cursor = max(cursor, silence.end)

    if cursor < duration:
        interval = Interval(cursor, duration)
        if interval.duration >= min_speech:
            speech.append(interval)

    return speech


def add_safe_padding(
    intervals: list[Interval],
    *,
    duration: float,
    pad: float,
) -> list[Interval]:
    padded: list[Interval] = []

    for index, interval in enumerate(intervals):
        left_limit = 0.0
        right_limit = duration

        if index > 0:
            previous = intervals[index - 1]
            left_limit = (previous.end + interval.start) / 2.0
        if index + 1 < len(intervals):
            following = intervals[index + 1]
            right_limit = (interval.end + following.start) / 2.0

        start = max(left_limit, interval.start - pad)
        end = min(right_limit, interval.end + pad)
        padded.append(Interval(start, end))

    return padded


def extend_letter_tails(
    intervals: list[Interval],
    *,
    following_gap: float,
    final_tail: float,
    duration: float,
) -> list[Interval]:
    extended = [
        Interval(interval.start, following.start - following_gap)
        for interval, following in zip(intervals, intervals[1:])
    ]
    if intervals:
        final = intervals[-1]
        extended.append(Interval(final.start, min(duration, final.end + final_tail)))
    if any(interval.end <= interval.start for interval in extended):
        raise ValueError("--following-gap leaves no audio for at least one letter.")
    return extended


def print_detected(
    intervals: list[Interval],
    *,
    absolute_start: float,
    selected_offset: int,
) -> None:
    print()
    print(f"Detected {len(intervals)} usable speech segments after the start crop.")
    print(f"Skipping {selected_offset}; the following {len(LETTERS)} become A-Z.")
    print()
    print(f"{'#':>3}  {'Name':<5} {'Relative':>19} {'Absolute':>19} {'Length':>8}")
    print("-" * 64)

    for index, interval in enumerate(intervals):
        selected_index = index - selected_offset
        name = LETTERS[selected_index] if 0 <= selected_index < len(LETTERS) else "-"
        absolute_s = absolute_start + interval.start
        absolute_e = absolute_start + interval.end
        print(
            f"{index + 1:>3}  {name:<5} "
            f"{interval.start:>7.3f}-{interval.end:<7.3f} "
            f"{absolute_s:>7.3f}-{absolute_e:<7.3f} "
            f"{interval.duration:>7.3f}s"
        )
    print()


def ensure_outputs_available(
    output_dir: Path,
    *,
    output_format: str,
    force: bool,
) -> None:
    existing = [
        output_dir / f"{letter}.{output_format}"
        for letter in LETTERS
        if (output_dir / f"{letter}.{output_format}").exists()
    ]
    if existing and not force:
        preview = "\n".join(f"  {path}" for path in existing[:5])
        if len(existing) > 5:
            preview += f"\n  ...and {len(existing) - 5} more"
        raise FileExistsError(
            "Output files already exist:\n"
            f"{preview}\n"
            "Run again with --force to overwrite them."
        )


def export_interval(
    source_wav: Path,
    destination: Path,
    interval: Interval,
    *,
    output_format: str,
    volume: float,
) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{interval.start:.3f}",
        "-i",
        str(source_wav),
        "-t",
        f"{interval.duration:.3f}",
        "-vn",
        "-ac",
        "1",
        "-af",
        f"volume={volume:g}",
    ]

    if output_format == "wav":
        command.extend(["-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le"])
    else:
        command.extend(["-c:a", "libmp3lame", "-b:a", "192k"])

    command.append(str(destination))
    run(command, quiet=True)


def write_manifest(
    path: Path,
    selected: list[Interval],
    *,
    source: Path,
    absolute_start: float,
    output_format: str,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "letter",
                "filename",
                "source",
                "relative_start_seconds",
                "relative_end_seconds",
                "absolute_start_seconds",
                "absolute_end_seconds",
                "duration_seconds",
            ]
        )
        for letter, interval in zip(LETTERS, selected, strict=True):
            writer.writerow(
                [
                    letter,
                    f"{letter}.{output_format}",
                    str(source),
                    f"{interval.start:.3f}",
                    f"{interval.end:.3f}",
                    f"{absolute_start + interval.start:.3f}",
                    f"{absolute_start + interval.end:.3f}",
                    f"{interval.duration:.3f}",
                ]
            )


def main() -> int:
    args = parse_args()

    try:
        require_ffmpeg()
        validate_args(args)
        args.output_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="summerday-alphabet-") as temp_dir:
            analysis_wav = Path(temp_dir) / "alphabet_analysis.wav"
            convert_for_analysis(
                args.source,
                analysis_wav,
                start=args.start,
                duration=args.duration,
            )
            duration = probe_duration(analysis_wav)
            silences = detect_silences(
                analysis_wav,
                noise_db=args.noise_db,
                min_silence=args.min_silence,
                duration=duration,
            )
            raw_speech = speech_from_silences(
                silences,
                duration=duration,
                min_speech=args.min_speech,
            )
            padded_speech = add_safe_padding(
                raw_speech,
                duration=duration,
                pad=args.pad,
            )

            print_detected(
                padded_speech,
                absolute_start=args.start,
                selected_offset=args.skip,
            )

            available = len(padded_speech) - args.skip
            if available < len(LETTERS):
                raise RuntimeError(
                    f"Only {available} segments remain after --skip {args.skip}; "
                    f"26 are required.\n"
                    "Try lowering --min-silence, lowering --min-speech, or moving "
                    "--start slightly earlier."
                )

            selected = padded_speech[args.skip : args.skip + len(LETTERS)]
            selected = extend_letter_tails(
                selected,
                following_gap=args.following_gap,
                final_tail=args.final_tail,
                duration=duration,
            )

            if len(padded_speech) > args.skip + len(LETTERS):
                extras = len(padded_speech) - args.skip - len(LETTERS)
                print(f"Ignoring {extras} later speech segment(s), likely the outro.")

            if args.dry_run:
                print("Dry run complete; no audio files were written.")
                return 0

            ensure_outputs_available(
                args.output_dir,
                output_format=args.output_format,
                force=args.force,
            )

            for letter, interval in zip(LETTERS, selected, strict=True):
                destination = args.output_dir / f"{letter}.{args.output_format}"
                export_interval(
                    analysis_wav,
                    destination,
                    interval,
                    output_format=args.output_format,
                    volume=args.volume,
                )
                print(
                    f"{letter}: {interval.start:.3f}-{interval.end:.3f}s "
                    f"→ {destination}"
                )

            manifest = args.output_dir / "segments.csv"
            write_manifest(
                manifest,
                selected,
                source=args.source,
                absolute_start=args.start,
                output_format=args.output_format,
            )
            print(f"Manifest: {manifest}")

            if args.keep_analysis_wav:
                retained = args.output_dir / "_analysis_16k_mono.wav"
                shutil.copy2(analysis_wav, retained)
                print(f"Analysis WAV: {retained}")

        print(
            f"Done. Created {len(LETTERS)} files in "
            f"{args.output_dir.resolve()}"
        )
        return 0

    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
