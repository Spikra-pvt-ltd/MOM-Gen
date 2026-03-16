from dotenv import load_dotenv
load_dotenv()

import os
import sys
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.routes.meeting import router as meeting_router

# ── Startup diagnostics ────────────────────────────────────────────────────────
_openai_key = os.getenv("OPENAI_API_KEY")
if _openai_key:
    print(f"✓ OPENAI_API_KEY loaded: {_openai_key[:8]}...{_openai_key[-4:]} (transcription)", file=sys.stderr)
else:
    print("✗ WARNING: OPENAI_API_KEY is NOT set — Whisper transcription will fail!", file=sys.stderr)
    print("  → Create backend/.env with: OPENAI_API_KEY=sk-...", file=sys.stderr)

_anthropic_key = os.getenv("ANTHROPIC_API_KEY")
if _anthropic_key:
    print(f"✓ ANTHROPIC_API_KEY loaded: {_anthropic_key[:8]}...{_anthropic_key[-4:]} (MoM generation)", file=sys.stderr)
else:
    print("✗ WARNING: ANTHROPIC_API_KEY is NOT set — MoM generation will fail!", file=sys.stderr)
    print("  → Create backend/.env with: ANTHROPIC_API_KEY=sk-ant-...", file=sys.stderr)

_deepgram_key = os.getenv("DEEPGRAM_API_KEY")
if _deepgram_key:
    print(f"✓ DEEPGRAM_API_KEY loaded: {_deepgram_key[:8]}...{_deepgram_key[-4:]} (transcription)", file=sys.stderr)
else:
    print("✗ WARNING: DEEPGRAM_API_KEY is NOT set — transcription will fail!", file=sys.stderr)
    print("  → Create backend/.env with: DEEPGRAM_API_KEY=... (free at deepgram.com)", file=sys.stderr)
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI MoM Generator API",
    description="Generate structured Minutes of Meeting from audio/video recordings.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://mom-frontend-sobw.onrender.com",
        "https://minutesofmeeting-blue.vercel.app",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_origin_regex=r"https://(.*\.onrender\.com|.*\.vercel\.app)",  # covers Render + Vercel preview URLs
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meeting_router)


# ── Global error handlers: always attach CORS header so browser shows the real error ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
        headers={"Access-Control-Allow-Origin": "*"},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={"Access-Control-Allow-Origin": "*"},
    )

@app.get("/health")
def health():
    return {
        "status": "ok",
        "openai_key_loaded": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic_key_loaded": bool(os.getenv("ANTHROPIC_API_KEY")),
        "deepgram_key_loaded": bool(os.getenv("DEEPGRAM_API_KEY")),
    }
