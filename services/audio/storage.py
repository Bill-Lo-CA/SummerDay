from pathlib import Path


def resolve_media_path(media_root: Path, relative_path: str) -> Path:
    root = media_root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("audio path must remain inside the media root") from exc
    return candidate
