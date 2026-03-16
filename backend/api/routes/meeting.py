from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uuid
import traceback
from pathlib import Path
from typing import Optional, Any

from services.file_handler import save_upload, cleanup_files, is_video
from services.audio_extractor import extract_audio, compress_audio
from services.transcriber import transcribe
from services.mom_generator import generate_mom

router = APIRouter(prefix="/meeting", tags=["meeting"])

# In-memory store (MVP — no database). Wiped on restart; meetings live in frontend state.
# Schemas:
# {
#   "meeting_id": str,
#   "meeting_name": str,
#   "meeting_date": str,
#   "status": "pending" | "processing" | "completed" | "failed",
#   "transcript": str | None,
#   "mom": dict | None,
#   "error": str | None
# }
meetings: dict[str, dict] = {}


class CreateMeetingRequest(BaseModel):
    meeting_name: str
    meeting_date: str


class CreateMeetingResponse(BaseModel):
    meeting_id: str


class UploadAckResponse(BaseModel):
    status: str
    message: str


class MeetingStatusResponse(BaseModel):
    status: str
    transcript: Optional[str] = None
    mom: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@router.post("/create", response_model=CreateMeetingResponse)
async def create_meeting(payload: CreateMeetingRequest):
    meeting_id = str(uuid.uuid4())
    meetings[meeting_id] = {
        "meeting_id": meeting_id,
        "meeting_name": payload.meeting_name,
        "meeting_date": payload.meeting_date,
        "status": "pending",
        "transcript": None,
        "mom": None,
        "error": None
    }
    return CreateMeetingResponse(meeting_id=meeting_id)


ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".mkv"}

def process_audio_task(meeting_id: str, upload_path: Path):
    """Background task to process audio, transcribe, and generate MoM."""
    audio_path: Path | None = None
    try:
        if meeting_id not in meetings:
            print(f"[process_audio_task] Meeting {meeting_id} not found — aborting.", flush=True)
            return

        meetings[meeting_id]["status"] = "processing"
        print(f"[process_audio_task] Starting processing for meeting {meeting_id}", flush=True)

        # Step 1: Extract / compress audio — always stay under Whisper's 25 MB limit
        if is_video(upload_path):
            print(f"[process_audio_task] Extracting audio from video: {upload_path}", flush=True)
            audio_path = extract_audio(upload_path)
        else:
            print(f"[process_audio_task] Compressing audio: {upload_path}", flush=True)
            audio_path = compress_audio(upload_path)
        print(f"[process_audio_task] Audio ready at {audio_path}", flush=True)

        # Step 2: Transcribe
        # transcribe() returns (plain_text, speaker_labelled_text).
        # We display plain_text in the UI and feed speaker_labelled_text to the
        # MoM generator so it can accurately identify attendees.
        print(f"[process_audio_task] Starting transcription…", flush=True)
        plain_transcript, speaker_transcript = transcribe(audio_path)
        print(f"[process_audio_task] Transcription done ({len(plain_transcript)} chars)", flush=True)

        # Step 3: Generate MoM
        print(f"[process_audio_task] Generating MoM…", flush=True)
        mom = generate_mom(speaker_transcript)
        print(f"[process_audio_task] MoM generation done", flush=True)

        meetings[meeting_id]["transcript"] = plain_transcript
        meetings[meeting_id]["mom"] = mom
        meetings[meeting_id]["status"] = "completed"
        print(f"[process_audio_task] Meeting {meeting_id} completed successfully", flush=True)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[process_audio_task] ERROR for meeting {meeting_id}: {e}", flush=True)
        if meeting_id in meetings:
            meetings[meeting_id]["status"] = "failed"
            meetings[meeting_id]["error"] = str(e)
    finally:
        # Always clean up temp files
        cleanup_files(upload_path, audio_path)


@router.post("/{meeting_id}/upload", response_model=UploadAckResponse)
async def upload_recording(meeting_id: str, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # Create the meeting dynamically if it wasn't pre-created to avoid 404s
    if meeting_id not in meetings:
        meetings[meeting_id] = {
            "meeting_id": meeting_id,
            "meeting_name": "New Meeting",
            "meeting_date": "Today",
            "status": "pending",
            "transcript": None,
            "mom": None,
            "error": None
        }

    # Validate file extension
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    try:
        # Read & save file synchronously so the file handle isn't closed when returning
        file_bytes = await file.read()
        upload_path = save_upload(file_bytes, filename)
        
        # Queue the background task
        background_tasks.add_task(process_audio_task, meeting_id, upload_path)

        return UploadAckResponse(status="processing", message="File uploaded, processing started in the background")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{meeting_id}/status", response_model=MeetingStatusResponse)
async def get_meeting_status(meeting_id: str):
    if meeting_id not in meetings:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    m = meetings[meeting_id]
    return MeetingStatusResponse(
        status=m["status"],
        transcript=m["transcript"],
        mom=m["mom"],
        error=m["error"]
    )

