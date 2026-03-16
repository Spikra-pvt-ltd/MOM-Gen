"use client";

import { useState, useRef, useCallback } from "react";
import { toast } from "sonner";
import { uploadRecording, getMeetingStatus, wakeUpBackend, type MomData, type ProcessingResult } from "@/lib/api";
import {
  Upload, FileAudio, FileVideo, CheckCircle, XCircle,
  Loader2, Circle, Copy, Check, Mic, Sparkles, User,
} from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────────

type StepStatus = "pending" | "active" | "done" | "error";

const STEPS = [
  { id: "waking", label: "Waking up server" },
  { id: "uploading", label: "Uploading file" },
  { id: "extracting", label: "Extracting audio" },
  { id: "transcribing", label: "Transcribing with Whisper" },
  { id: "generating", label: "Generating Minutes of Meeting" },
];

const ACCEPTED = ".mp3,.wav,.m4a,.mp4,.mov,.mkv";
const VIDEO_EXT = ["mp4", "mov", "mkv"];

function isVideo(file: File) {
  return VIDEO_EXT.includes(file.name.split(".").pop()?.toLowerCase() ?? "");
}

function fmtSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [steps, setSteps] = useState<Record<string, StepStatus>>({});
  const [result, setResult] = useState<ProcessingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"mom" | "transcript">("mom");
  const [copied, setCopied] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const setStep = (id: string, status: StepStatus) =>
    setSteps(prev => ({ ...prev, [id]: status }));

  const handleFile = (f: File) => {
    const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
    if (!["mp3", "wav", "m4a", "mp4", "mov", "mkv"].includes(ext)) {
      toast.error(`Unsupported type: .${ext}`);
      return;
    }
    setFile(f);
    setResult(null);
    setError(null);
    setSteps({});
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const handleGenerate = async () => {
    if (!file) return;
    setProcessing(true);
    setResult(null);
    setError(null);
    setSteps({});

    // We use a fake meeting ID since the new flow has no meeting creation step
    const meetingId = `session-${Date.now()}`;

    try {
      // Step 0: Wake up the Render free-tier backend (may be sleeping after inactivity).
      // If the backend is asleep and we upload immediately, the request times out with
      // no response — the browser then misreports this as a CORS error. Pinging /health
      // first ensures the server is alive before we attempt the upload.
      setStep("waking", "active");
      await wakeUpBackend((msg) => {
        // Show the wake-up status in the browser console (visible in DevTools)
        console.info("[wakeUpBackend]", msg);
      });
      setStep("waking", "done");

      // Step 1: Upload file (starts background task)
      setStep("uploading", "active");
      await uploadRecording(meetingId, file);
      setStep("uploading", "done");

      if (isVideo(file)) {
        setStep("extracting", "active");
      } else {
        setStep("extracting", "done");
        setStep("transcribing", "active");
      }

      // Step 2: Poll for status
      // Add a hard timeout so the UI never spins forever (8 minutes max).
      const pollInterval = 3000; // 3 seconds between polls
      const maxPollMs = 8 * 60 * 1000; // 8 minutes
      const pollDeadline = Date.now() + maxPollMs;

      while (true) {
        await new Promise(r => setTimeout(r, pollInterval));

        if (Date.now() > pollDeadline) {
          throw new Error("Processing timed out after 8 minutes. The audio may be too long — please try a shorter clip.");
        }

        const statusData = await getMeetingStatus(meetingId);

        if (statusData.status === 'failed') {
          throw new Error(statusData.error || "Processing failed on server.");
        }

        if (statusData.status === 'completed') {
          setStep("extracting", "done");
          setStep("transcribing", "done");
          setStep("generating", "done");

          if (statusData.transcript && statusData.mom) {
            setResult({ transcript: statusData.transcript, mom: statusData.mom });
            toast.success("Minutes of Meeting generated!");
          }
          break;
        }

        // Still processing — keep updating UI steps to show activity
        if (statusData.status === 'processing') {
          setStep("extracting", "done");
          setStep("transcribing", "active");
        }
      }

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Processing failed";
      setError(msg);
      setSteps(prev => {
        const next = { ...prev };
        for (const k of Object.keys(next))
          if (next[k] === "active") next[k] = "error";
        return next;
      });
      toast.error(msg);
    } finally {
      setProcessing(false);
    }
  };

  const handleCopy = async () => {
    if (!result) return;
    const m = result.mom;
    const lines: string[] = [
      "*Minutes of Meeting",
      " ",
      `Meeting Name: ${m.meeting_name || '[Meeting Name]'}`,
      `Meeting Date: ${m.meeting_date || '[Meeting Date]'}`,
      "Meeting Attendees:",
      ...(m.attendees ?? []).map(a => `- ${a}`),
      " ",
      "Discussion Points:",
      ...(m.discussion_points ?? []).map((p, i) => `${i + 1}. ${p}`),
      " ",
      "Action Items:",
      " ",
      ...(m.action_items ?? []).flatMap((group, idx, arr) => [
        `${group.team}:${idx === arr.length - 1 ? '*' : ''}`,
        ...(group.items ?? []).map(it =>
          `- [ ] ${it.owner ? `${it.owner} to ` : ""}${it.task}`
        ),
        " "
      ]).slice(0, -1) // remove trailing space
    ];
    await navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    toast.success("MoM copied to clipboard!");
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", padding: "0 20px 60px" }}>
      {/* ── Header ── */}
      <header style={{
        maxWidth: 860, margin: "0 auto", padding: "32px 0 24px",
        display: "flex", alignItems: "center", gap: 12,
        borderBottom: "1px solid var(--border)", marginBottom: 32,
      }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10,
          background: "var(--primary)", display: "flex",
          alignItems: "center", justifyContent: "center",
        }}>
          <Mic size={20} color="white" />
        </div>
        <div>
          <h1 style={{ fontSize: "1.25rem", fontWeight: 800, color: "var(--text-primary)", lineHeight: 1.2 }}>
            MoM Generator
          </h1>
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
            AI-powered Minutes of Meeting · GPT-4o + Whisper
          </p>
        </div>
      </header>

      <main style={{ maxWidth: 860, margin: "0 auto" }}>
        {!result ? (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, alignItems: "start" }}>
            {/* ── Upload panel ── */}
            <div>
              <div
                className={`drop-zone ${dragOver ? "drag-over" : ""}`}
                style={{ padding: "48px 28px", textAlign: "center" }}
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                onClick={() => !processing && fileInputRef.current?.click()}
              >
                <input ref={fileInputRef} type="file" accept={ACCEPTED} hidden
                  onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
                <div style={{
                  width: 56, height: 56, borderRadius: "50%",
                  background: "var(--primary-light)", margin: "0 auto 16px",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <Upload size={24} color="var(--primary)" />
                </div>
                {file ? (
                  <>
                    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      {isVideo(file)
                        ? <FileVideo size={18} color="var(--accent)" />
                        : <FileAudio size={18} color="var(--primary)" />}
                      <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.92rem" }}>
                        {file.name}
                      </span>
                    </div>
                    <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {fmtSize(file.size)} · Click to change
                    </p>
                  </>
                ) : (
                  <>
                    <p style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
                      Drop your meeting recording here
                    </p>
                    <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: 14 }}>or click to browse</p>
                    <div style={{ display: "flex", gap: 6, justifyContent: "center", flexWrap: "wrap" }}>
                      {["MP3", "WAV", "M4A", "MP4", "MOV", "MKV"].map(e => (
                        <span key={e} className="chip">{e}</span>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <button
                id="generate-btn"
                className="btn-primary"
                onClick={handleGenerate}
                disabled={!file || processing}
                style={{ width: "100%", justifyContent: "center", marginTop: 14 }}
              >
                {processing
                  ? <><Loader2 size={18} className="spin" /> Processing...</>
                  : <><Sparkles size={18} /> Generate MoM</>}
              </button>
            </div>

            {/* ── Processing status ── */}
            {(processing || Object.keys(steps).length > 0) && (
              <div className="card fade-in" style={{ padding: 24 }}>
                <p style={{ fontSize: "0.75rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 16 }}>
                  Processing Status
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {STEPS.map(s => {
                    const st: StepStatus = steps[s.id] ?? "pending";
                    return (
                      <div key={s.id} className={`step ${st}`}>
                        {st === "pending" && <Circle size={18} />}
                        {st === "active" && <Loader2 size={18} className="spin" />}
                        {st === "done" && <CheckCircle size={18} />}
                        {st === "error" && <XCircle size={18} />}
                        <span>{s.label}</span>
                      </div>
                    );
                  })}
                </div>
                {error && (
                  <div style={{ marginTop: 16, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8 }}>
                    <p style={{ fontSize: "0.82rem", color: "var(--error)" }}>{error}</p>
                  </div>
                )}
              </div>
            )}

            {/* ── Idle hint ── */}
            {!processing && Object.keys(steps).length === 0 && (
              <div className="card fade-in" style={{ padding: 28, textAlign: "center", opacity: 0.7 }}>
                <Sparkles size={32} color="var(--primary)" style={{ margin: "0 auto 12px" }} />
                <p style={{ fontSize: "0.88rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                  Upload your meeting recording and we'll generate a structured MoM with attendees, discussion points, decisions, and action items.
                </p>
              </div>
            )}
          </div>
        ) : (
          /* ── Results ── */
          <div className="fade-in">
            {/* Tab bar */}
            <div style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              marginBottom: 20,
            }}>
              <div style={{ display: "flex", gap: 4, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 4 }}>
                {(["mom", "transcript"] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    style={{
                      padding: "7px 18px", borderRadius: 7, border: "none", cursor: "pointer",
                      fontSize: "0.85rem", fontWeight: 600,
                      background: activeTab === tab ? "var(--primary)" : "transparent",
                      color: activeTab === tab ? "white" : "var(--text-secondary)",
                      transition: "all 0.2s",
                    }}
                  >
                    {tab === "mom" ? "📋 Minutes of Meeting" : "📝 Transcript"}
                  </button>
                ))}
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <button className="btn-copy" id="copy-mom-btn" onClick={handleCopy}>
                  {copied ? <Check size={15} /> : <Copy size={15} />}
                  {copied ? "Copied!" : "Copy MoM"}
                </button>
                <button
                  onClick={() => { setResult(null); setFile(null); setSteps({}); }}
                  style={{
                    padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border)",
                    background: "white", color: "var(--text-secondary)", cursor: "pointer",
                    fontSize: "0.83rem",
                  }}
                >
                  New Recording
                </button>
              </div>
            </div>

            {activeTab === "mom"
              ? <MomDocument mom={result.mom} />
              : <div className="transcript-box">{result.transcript}</div>}
          </div>
        )}
      </main>
    </div>
  );
}

// ── MoM Document Component ────────────────────────────────────────────────────

function MomDocument({ mom }: { mom: MomData }) {
  return (
    <div className="card mom-doc" style={{ padding: 36 }}>
      {/* Header */}
      <div className="mom-section" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 16 }}>
        <h2 style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--primary)", marginBottom: 12 }}>
          Minutes of Meeting
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "8px 16px", fontSize: "0.9rem" }}>
          <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>Meeting Name:</span>
          <span>{mom.meeting_name || '[Meeting Name]'}</span>
          <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>Meeting Date:</span>
          <span>{mom.meeting_date || '[Meeting Date]'}</span>
        </div>
      </div>

      {/* Attendees */}
      <div className="mom-section">
        <div className="mom-section-title">Meeting Attendees</div>
        {!mom.attendees?.length
          ? <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>None identified</p>
          : <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
            {mom.attendees.map(a => (
              <span key={a} className="mom-attendee">
                <User size={12} /> {a}
              </span>
            ))}
          </div>
        }
      </div>

      {/* Discussion Points */}
      <div className="mom-section">
        <div className="mom-section-title">Discussion Points</div>
        {!mom.discussion_points?.length
          ? <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>None recorded</p>
          : <ul className="mom-list">
            {mom.discussion_points.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        }
      </div>

      {/* Action Items */}
      <div className="mom-section">
        <div className="mom-section-title">Action Items</div>
        {!mom.action_items?.length
          ? <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>None recorded</p>
          : mom.action_items.map((group, gi) => (
            <div key={gi} className="action-group">
              {group.team && group.team !== "General" && (
                <div className="action-group-title">{group.team}:</div>
              )}
              {(group.items ?? []).map((item, ii) => (
                <div key={ii} className="action-item">
                  <div className="action-item-check" />
                  <div className="action-item-text">
                    {item.owner && (
                      <span className="action-item-owner">{item.owner}</span>
                    )}
                    {item.owner ? ` to ${item.task}` : item.task}
                  </div>
                </div>
              ))}
            </div>
          ))
        }
      </div>
    </div>
  );
}
