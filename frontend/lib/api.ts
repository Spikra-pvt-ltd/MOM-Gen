// The backend base URL. In development, it defaults to localhost:8000.
// In production, NEXT_PUBLIC_API_URL should be set to the Render backend URL.
const BACKEND_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');


// ── Types ─────────────────────────────────────────────────────────────────────

export interface ActionItem {
    task: string;
    owner: string | null;
}

export interface ActionGroup {
    team: string;
    items: ActionItem[];
}

export interface MomData {
    meeting_name: string;
    meeting_date: string;
    attendees: string[];
    discussion_points: string[];
    action_items: ActionGroup[];
}

export interface ProcessingResult {
    transcript: string;
    mom: MomData;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function safeParseError(res: Response): Promise<string> {
    try {
        const err = await res.json();
        return err.detail || err.message || `HTTP ${res.status}`;
    } catch {
        return `HTTP ${res.status}: ${res.statusText || 'Server error'}`;
    }
}

/**
 * Pings the backend /health endpoint until it responds (handles Render free-tier cold starts).
 * Render free instances sleep after 15 min of inactivity. The first request can take 30-90s
 * to wake up. If we don't wait for the wake-up before uploading, the browser drops the long
 * connection and misreports it as a "CORS error".
 * @param onProgress Optional callback for status messages to display in the UI
 */
export async function wakeUpBackend(
    onProgress?: (msg: string) => void
): Promise<void> {
    const TIMEOUT_MS = 120_000; // 2 min max wait
    const RETRY_INTERVAL_MS = 3_000;
    const started = Date.now();

    onProgress?.('Waking up server (Render free tier sleeps after inactivity)…');

    while (Date.now() - started < TIMEOUT_MS) {
        try {
            const res = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(5000) });
            if (res.ok) {
                onProgress?.('Server is awake!');
                return;
            }
        } catch {
            // Server not yet responding — keep waiting
        }
        await new Promise(r => setTimeout(r, RETRY_INTERVAL_MS));
        const elapsed = Math.round((Date.now() - started) / 1000);
        onProgress?.(`Server still waking up… (${elapsed}s)`);
    }
    throw new Error('Backend server did not respond within 2 minutes. Please try again.');
}

// ── API calls ─────────────────────────────────────────────────────────────────

export async function createMeeting(
    meeting_name: string,
    meeting_date: string
): Promise<string> {
    const res = await fetch(`${BACKEND_URL}/meeting/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meeting_name, meeting_date }),
    });
    if (!res.ok) throw new Error(await safeParseError(res));
    const data = await res.json();
    return data.meeting_id;
}

export interface UploadAck {
    status: string;
    message: string;
}

export interface MeetingStatus {
    status: 'pending' | 'processing' | 'completed' | 'failed';
    transcript?: string;
    mom?: MomData;
    error?: string;
}

export async function uploadRecording(
    meetingId: string,
    file: File
): Promise<UploadAck> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${BACKEND_URL}/meeting/${meetingId}/upload`, {
        method: 'POST',
        body: formData,
    });
    if (!res.ok) throw new Error(await safeParseError(res));
    return res.json();
}

export async function getMeetingStatus(meetingId: string): Promise<MeetingStatus> {
    const res = await fetch(`${BACKEND_URL}/meeting/${meetingId}/status`);
    if (!res.ok) throw new Error(await safeParseError(res));
    return res.json();
}
