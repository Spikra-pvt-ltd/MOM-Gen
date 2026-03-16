import uuid
import ffmpeg
from pathlib import Path

AUDIO_DIR = Path("tmp/audio")

# 64 kbps mono 16 kHz keeps a 1-hour recording under 30 MB while preserving
# enough frequency detail for accurate transcription of speech and proper nouns.
# (32 kbps was too lossy — cloud APIs recommend ≥ 64 kbps for best accuracy.)
_WHISPER_BITRATE = "64k"
_WHISPER_SAMPLE_RATE = 16000


def _ensure_dir():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def extract_audio(video_path: Path) -> Path:
    """Extract and compress audio from a video file. Returns an mp3."""
    _ensure_dir()
    out = AUDIO_DIR / f"{uuid.uuid4()}.mp3"
    try:
        (
            ffmpeg
            .input(str(video_path))
            .output(
                str(out),
                ac=1,
                ar=_WHISPER_SAMPLE_RATE,
                audio_bitrate=_WHISPER_BITRATE,
                acodec="libmp3lame",
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        raise RuntimeError(f"FFmpeg audio extraction failed: {e.stderr.decode()}")
    return out


def compress_audio(audio_path: Path) -> Path:
    """Re-encode an audio file to a small mp3 safe for the Whisper API (<25 MB)."""
    _ensure_dir()
    out = AUDIO_DIR / f"{uuid.uuid4()}.mp3"
    try:
        (
            ffmpeg
            .input(str(audio_path))
            .output(
                str(out),
                ac=1,
                ar=_WHISPER_SAMPLE_RATE,
                audio_bitrate=_WHISPER_BITRATE,
                acodec="libmp3lame",
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        raise RuntimeError(f"FFmpeg audio compression failed: {e.stderr.decode()}")
    return out

