import os
import requests
from pathlib import Path

# ---------------------------------------------------------------------------
# Deepgram Nova-2 transcription with speaker diarization.
#
# Why Deepgram instead of Whisper API?
#   - Returns speaker-labelled utterances ("Speaker 0: ...", "Speaker 1: ...")
#     so the MoM generator knows exactly how many people spoke and what each
#     one said — eliminating attendee hallucination.
#   - Nova-2 has better proper-noun / name accuracy than Whisper large-v2.
#   - Typical turnaround: 5-15 s for a 1-hour recording (async streaming).
#   - Free tier: 200 hours/month at deepgram.com (no credit card required).
#
# Set DEEPGRAM_API_KEY in backend/.env.
# ---------------------------------------------------------------------------

_DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
_DEEPGRAM_TIMEOUT = 300  # seconds


def transcribe(audio_path: Path) -> tuple[str, str]:
    """
    Transcribe an audio file using Deepgram Nova-2.

    Returns:
        plain_transcript   – flat string, suitable for display in the UI
        speaker_transcript – diarized string with "Speaker N: …" lines,
                             passed to the MoM generator for accurate
                             attendee extraction
    """
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "DEEPGRAM_API_KEY is not set. Add it to backend/.env. "
            "Free tier (200 hrs/month): https://deepgram.com"
        )

    size_kb = audio_path.stat().st_size / 1024
    print(f"[transcriber] Sending {size_kb:.1f} KB to Deepgram Nova-2…", flush=True)

    audio_bytes = audio_path.read_bytes()

    response = requests.post(
        _DEEPGRAM_URL,
        params={
            "model": "nova-2",
            "smart_format": "true",   # punctuation, capitalisation, numerals
            "diarize": "true",        # speaker labels
            "utterances": "true",     # per-utterance speaker + timing
            "punctuate": "true",
            "filler_words": "false",  # strip "um", "uh", etc.
        },
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "audio/mpeg",
        },
        data=audio_bytes,
        timeout=_DEEPGRAM_TIMEOUT,
    )

    if not response.ok:
        raise RuntimeError(
            f"Deepgram API error {response.status_code}: {response.text}"
        )

    data = response.json()

    # ── Plain transcript (no speaker labels) ──────────────────────────────
    plain = (
        data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    )

    # ── Diarized transcript (Speaker N: …) ────────────────────────────────
    utterances = data["results"].get("utterances") or []
    if utterances:
        lines = [
            f"Speaker {u['speaker']}: {u['transcript'].strip()}"
            for u in utterances
        ]
        speaker_transcript = "\n".join(lines)
        n_speakers = len({u["speaker"] for u in utterances})
        print(
            f"[transcriber] Done — {len(plain)} chars, "
            f"{n_speakers} distinct speaker(s) detected.",
            flush=True,
        )
    else:
        # Diarization unavailable; fall back to plain transcript
        speaker_transcript = plain
        print(
            f"[transcriber] Done — {len(plain)} chars (no diarization).",
            flush=True,
        )

    return plain, speaker_transcript
