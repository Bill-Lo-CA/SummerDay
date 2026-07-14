from dataclasses import dataclass
from pathlib import Path
import wave

from services.audio.hashing import sha256_file
from services.audio.models import AudioAssetRef
from services.audio.storage import resolve_media_path


@dataclass(frozen=True)
class WavMetadata:
    sample_rate: int
    frames: int
    duration_ms: int


def wav_metadata(path: Path) -> WavMetadata:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"audio asset is missing or empty: {path}")
    try:
        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            frames = wav_file.getnframes()
    except (EOFError, OSError, wave.Error) as exc:
        raise ValueError(f"audio asset is not a valid WAV file: {path}") from exc
    if not 8_000 <= sample_rate <= 192_000:
        raise ValueError(f"audio asset has an unreasonable sample rate: {path}")
    if frames <= 0:
        raise ValueError(f"audio asset has no frames: {path}")
    return WavMetadata(sample_rate, frames, max(1, round(frames * 1000 / sample_rate)))


def validate_audio_asset(asset: AudioAssetRef, media_root: Path) -> Path:
    path = resolve_media_path(media_root, asset.path)
    if not path.is_file():
        raise ValueError(f"audio asset is missing: {asset.path}")
    actual_hash = sha256_file(path)
    if actual_hash != asset.sha256:
        raise ValueError(f"audio asset hash mismatch: {asset.path}")
    wav_metadata(path)
    return path
