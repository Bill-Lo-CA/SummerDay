from pathlib import Path

from services.audio.hashing import sha256_file
from services.audio.models import AudioAssetRef
from services.audio.storage import resolve_media_path


def validate_audio_asset(asset: AudioAssetRef, media_root: Path) -> Path:
    path = resolve_media_path(media_root, asset.path)
    if not path.is_file():
        raise ValueError(f"audio asset is missing: {asset.path}")
    actual_hash = sha256_file(path)
    if actual_hash != asset.sha256:
        raise ValueError(f"audio asset hash mismatch: {asset.path}")
    return path
