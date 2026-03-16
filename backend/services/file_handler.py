import os
import shutil
import uuid
from pathlib import Path

UPLOAD_DIR = Path("tmp/uploads")
AUDIO_DIR = Path("tmp/audio")


def ensure_temp_dirs():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def save_upload(file_bytes: bytes, original_filename: str) -> Path:
    """Save uploaded bytes to tmp/uploads with a unique name."""
    ensure_temp_dirs()
    ext = Path(original_filename).suffix.lower()
    unique_name = f"{uuid.uuid4()}{ext}"
    dest = UPLOAD_DIR / unique_name
    dest.write_bytes(file_bytes)
    return dest


def cleanup_files(*paths: Path):
    """Delete temporary files after processing."""
    for path in paths:
        try:
            if path and path.exists():
                path.unlink()
        except Exception:
            pass


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS
