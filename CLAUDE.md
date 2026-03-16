# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered Minutes of Meeting (MoM) generator. Upload a meeting recording → transcribed locally via faster-whisper → structured MoM generated via GPT-4o.

## Development Commands

### Backend (FastAPI / Python)
```bash
# Install dependencies (requires ffmpeg system package)
pip install -r backend/requirements.txt

# Run dev server (from repo root)
cd backend && uvicorn main:app --reload --port 8000
```

### Frontend (Next.js / TypeScript)
```bash
cd frontend
npm install
npm run dev       # dev server on localhost:3000
npm run build     # production build
npm run lint      # ESLint
```

## Environment Setup

**Backend** — create `backend/.env`:
```
OPENAI_API_KEY=sk-...
DEEPGRAM_API_KEY=...   # free tier (200 hrs/month) at deepgram.com
```

**Frontend** — create `frontend/.env.local` for non-local backends:
```
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```
Defaults to `http://localhost:8000` if unset.

**System dependency**: `ffmpeg` must be installed (`brew install ffmpeg` on macOS).

## Architecture

### Request Flow
1. Frontend pings `GET /health` to wake up the server (handles Render free-tier cold starts)
2. Frontend posts file to `POST /meeting/{id}/upload` — returns immediately with `202`
3. FastAPI runs a `BackgroundTask` (`process_audio_task`): extract/compress audio → transcribe → generate MoM
4. Frontend polls `GET /meeting/{id}/status` every 3 seconds until `completed` or `failed`

### Backend (`backend/`)
- `main.py` — FastAPI app; CORS config (allows `localhost:3000` and `*.onrender.com`); global exception handlers that always attach CORS headers
- `api/routes/meeting.py` — three endpoints: `POST /meeting/create`, `POST /meeting/{id}/upload`, `GET /meeting/{id}/status`; in-memory `meetings` dict (no database — wiped on restart)
- `services/transcriber.py` — calls **Deepgram Nova-2** API with speaker diarization; returns `(plain_transcript, speaker_transcript)` tuple; `speaker_transcript` has `"Speaker N: …"` lines used by the MoM generator
- `services/mom_generator.py` — calls GPT-4o with `response_format={"type": "json_object"}`; prompt enforces specific JSON schema with `meeting_name`, `meeting_date`, `attendees`, `discussion_points`, `action_items` (grouped by team)
- `services/audio_extractor.py` — uses `ffmpeg-python` to extract/compress to 32kbps mono 16kHz MP3 (keeps files under 25MB)
- `services/file_handler.py` — saves uploads to `tmp/uploads/`, audio outputs to `tmp/audio/`; cleans up temp files after processing

### Frontend (`frontend/`)
- Single page app — `app/page.tsx` contains all UI state and logic
- `lib/api.ts` — all API calls (`wakeUpBackend`, `uploadRecording`, `getMeetingStatus`); `BACKEND_URL` from `NEXT_PUBLIC_API_URL`
- No component library; uses inline styles + a few CSS classes in `globals.css`
- `next.config.ts` proxies `/api/*` → backend (not currently used by the main flow)

## Key Constraints

- **Transcription is cloud-only**: Deepgram Nova-2 is called via HTTP — no GPU/RAM constraint on Render. `DEEPGRAM_API_KEY` must be set.
- **In-memory state**: The `meetings` dict in `meeting.py` is lost on every server restart. This is intentional for the MVP.
- **Render cold starts**: The frontend `wakeUpBackend()` function retries `/health` for up to 2 minutes. Any upload attempted before the server is awake will appear as a CORS error in the browser.
- **Supported formats**: `.mp3`, `.wav`, `.m4a` (audio) and `.mp4`, `.mov`, `.mkv` (video).

## Deployment

Hosted on Render. The backend `build.sh` installs `ffmpeg` via `apt-get` then runs `pip install -r requirements.txt`. Start command should be `uvicorn main:app --host 0.0.0.0 --port $PORT`.
