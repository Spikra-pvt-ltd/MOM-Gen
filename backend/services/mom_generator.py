import os
import json
import re
import anthropic

# ── OpenAI client (commented out — kept for easy rollback) ────────────────────
# from openai import OpenAI
#
# def _get_openai_client() -> OpenAI:
#     api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         raise RuntimeError("OPENAI_API_KEY is not set.")
#     return OpenAI(api_key=api_key)
# ─────────────────────────────────────────────────────────────────────────────


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Please add it to backend/.env."
        )
    return anthropic.Anthropic(api_key=api_key)


_MODEL = "claude-sonnet-4-6"


def _claude(client: anthropic.Anthropic, system: str, user: str, temperature: float = 0.0) -> str:
    """Single helper for all Claude calls. Returns the text content."""
    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text.strip()


def _parse_json_response(raw: str) -> dict | list:
    """
    Parse JSON from Claude's response.
    Strips markdown code fences (```json ... ```) if present.
    """
    # Remove optional ```json ... ``` wrapper
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned.strip())


# ---------------------------------------------------------------------------
# Step 1 — Speaker resolution
# ---------------------------------------------------------------------------
_SPEAKER_RESOLUTION_PROMPT = """You are analysing a diarized meeting transcript.
Speakers are labelled "Speaker 0", "Speaker 1", etc.

Your ONLY task: map each Speaker ID to the real name of that person.

Apply these three rules IN ORDER to every utterance in the transcript:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULE 1 — SELF-IDENTIFICATION (highest confidence)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If a speaker says any of:
  "I'm [Name]", "I am [Name]", "This is [Name]", "My name is [Name]",
  "Hi, [Name] here", "It's [Name]"
→ that Speaker ID = that Name.

Example:
  Speaker 2: Hi, I'm Charan from the Spikra team.
  → {"2": "Charan"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULE 2 — DIRECT ADDRESS + NEXT RESPONSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If Speaker A says "[Name], [question or request]" and the VERY NEXT utterance
is from Speaker B, then Speaker B = Name.

Example:
  Speaker 0: Shini, can you walk us through the warehouse process?
  Speaker 1: Sure, so once items arrive at the warehouse...
  → {"1": "Shini"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULE 3 — POST-SPEECH ACKNOWLEDGMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If Speaker A says "Thanks [Name]", "Good point [Name]", "Exactly [Name]",
or "[Name], that's right" IMMEDIATELY AFTER Speaker B finished speaking,
then Speaker B = Name.

Example:
  Speaker 3: ...so the data sync should run every three hours.
  Speaker 0: Good point, Aditya. We'll factor that in.
  → {"3": "Aditya"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NAME QUALITY RULES — apply before returning any name
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• IGNORE partial or unclear transcriptions such as "screen sir", "sni sir",
  "mam", "sir", "madam", "boss", or any word that is clearly not a real name.
  Use null for that speaker instead.
• NORMALIZE obvious minor transcription errors when the intended name is clear:
    Aditiya  → Aditya
    Minna    → Mina
    Meena    → Mina
    Sree     → Sri
  Only normalise when you are CERTAIN of the intended name. Otherwise use null.
• If the same name appears with slight spelling variations across the transcript,
  normalise all variants to the most likely correct spelling.
• Do NOT guess a name — if you are not reasonably certain, return null.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Apply all three rules across the ENTIRE transcript before producing output.
- If multiple rules conflict for the same ID, prefer Rule 1 > Rule 2 > Rule 3.
- Use null for any speaker whose name genuinely cannot be determined.
- Return ONLY valid JSON, nothing else:
  {"0": "Veena", "1": "Shini", "2": "Charan", "3": null}
"""

# ── OpenAI version (commented out) ───────────────────────────────────────────
# def _resolve_speaker_names(speaker_transcript: str, client: OpenAI) -> dict[str, str]:
#     response = client.chat.completions.create(
#         model="gpt-4o",
#         messages=[
#             {"role": "system", "content": _SPEAKER_RESOLUTION_PROMPT},
#             {"role": "user", "content": f"Apply the three rules to identify each speaker's real name.\n\n{speaker_transcript}"},
#         ],
#         response_format={"type": "json_object"},
#         temperature=0.0,
#     )
#     raw = response.choices[0].message.content
#     try:
#         mapping = json.loads(raw)
#         return {str(k): v for k, v in mapping.items() if isinstance(v, str) and v.strip()}
#     except (json.JSONDecodeError, AttributeError):
#         print(f"[mom_generator] Speaker resolution bad JSON: {raw}", flush=True)
#         return {}
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_speaker_names(speaker_transcript: str, client: anthropic.Anthropic) -> dict[str, str]:
    """
    Claude call: map Speaker IDs to real names using three explicit rules.
    Returns {"0": "Aditya", "1": "Shini", ...} (nulls excluded).
    """
    raw = _claude(
        client,
        system=_SPEAKER_RESOLUTION_PROMPT,
        user=f"Apply the three rules to identify each speaker's real name.\n\n{speaker_transcript}",
        temperature=0.0,
    )
    try:
        mapping = _parse_json_response(raw)
        return {str(k): v for k, v in mapping.items() if isinstance(v, str) and v.strip()}
    except (json.JSONDecodeError, AttributeError, ValueError):
        print(f"[mom_generator] Speaker resolution bad JSON: {raw}", flush=True)
        return {}


# ---------------------------------------------------------------------------
# Step 2 — Directly-addressed names (confirmed attendees fallback)
# ---------------------------------------------------------------------------
_DIRECTLY_ADDRESSED_PROMPT = """You are analysing a diarized meeting transcript.

Your ONLY task: list every person's name that a speaker DIRECTLY ADDRESSES
(i.e., calls by name while speaking to them).

VALID examples of direct address:
  "Shini, can you explain..." → Shini
  "Thanks Aditya, that was helpful" → Aditya
  "Charan, what do you think?" → Charan
  "Good point Veena." → Veena
  "Hi Aditya" or "Hello Mina" (greetings count) → Aditya / Mina

Do NOT include:
  • Names merely mentioned in passing (e.g. "the client mentioned to John" — not a direct address)
  • "sir", "madam", "boss", "speaker", or any non-name honorific without a real name attached
  • Unclear or partially transcribed fragments (e.g. "screen sir", "sni sir") — skip these

NAME NORMALISATION — apply before returning:
  Aditiya → Aditya | Minna → Mina | Meena → Mina | Sree → Sri
  Only normalise when the intended name is CERTAIN. Otherwise omit the entry.

Remove duplicates. Return ONLY a JSON array of unique, correctly-spelled names.
Example: ["Shini", "Aditya", "Charan", "Veena"]
If no clearly-identifiable names are directly addressed, return [].
"""

# ── OpenAI version (commented out) ───────────────────────────────────────────
# def _extract_directly_addressed_names(speaker_transcript: str, client: OpenAI) -> list[str]:
#     response = client.chat.completions.create(
#         model="gpt-4o",
#         messages=[
#             {"role": "system", "content": _DIRECTLY_ADDRESSED_PROMPT},
#             {"role": "user", "content": f"List all names directly addressed by speakers in this transcript.\n\n{speaker_transcript}"},
#         ],
#         temperature=0.0,
#     )
#     raw = response.choices[0].message.content.strip()
#     try:
#         names = json.loads(raw)
#         if isinstance(names, list):
#             return [n for n in names if isinstance(n, str) and n.strip()]
#         for v in names.values():
#             if isinstance(v, list):
#                 return [n for n in v if isinstance(n, str) and n.strip()]
#     except (json.JSONDecodeError, AttributeError):
#         print(f"[mom_generator] Directly-addressed extraction bad JSON: {raw}", flush=True)
#     return []
# ─────────────────────────────────────────────────────────────────────────────

def _extract_directly_addressed_names(speaker_transcript: str, client: anthropic.Anthropic) -> list[str]:
    """
    Claude call: extract names that are directly addressed in the transcript.
    These are confirmed attendees even if their speaker ID is unknown.
    """
    raw = _claude(
        client,
        system=_DIRECTLY_ADDRESSED_PROMPT,
        user=f"List all names directly addressed by speakers in this transcript.\n\n{speaker_transcript}",
        temperature=0.0,
    )
    try:
        names = _parse_json_response(raw)
        if isinstance(names, list):
            return [n for n in names if isinstance(n, str) and n.strip()]
        for v in names.values():
            if isinstance(v, list):
                return [n for n in v if isinstance(n, str) and n.strip()]
    except (json.JSONDecodeError, AttributeError, ValueError):
        print(f"[mom_generator] Directly-addressed extraction bad JSON: {raw}", flush=True)
    return []


def _apply_speaker_names(speaker_transcript: str, mapping: dict[str, str]) -> str:
    """Replace 'Speaker N:' labels with resolved names in the transcript."""
    result = speaker_transcript
    for speaker_id, name in sorted(mapping.items(), key=lambda x: -len(x[0])):
        result = re.sub(
            rf"\bSpeaker {re.escape(speaker_id)}:",
            f"{name}:",
            result,
        )
    return result


# ---------------------------------------------------------------------------
# Step 3 — MoM generation
# ---------------------------------------------------------------------------
_MOM_SYSTEM_PROMPT = """You are a precise, factual meeting note-taker.
Generate structured Minutes of Meeting (MoM) from the transcript provided.

The transcript may contain:
• Real speaker names (e.g. "Aditya:", "Mina:")
• Unresolved labels like "Speaker 0", "Speaker 1"

You will also receive a list of CONFIRMED ATTENDEES — people whose presence
is proven because they were directly addressed by name during the meeting.

════════════════════════════════════════
CRITICAL RULE — SPEAKER LABELS
════════════════════════════════════════
Speaker identifiers such as:
  Speaker 0, Speaker 1, Speaker 2, Speaker N

are transcription artifacts.

They MUST NEVER appear in the final MoM output.

Do NOT include them:
• in the attendees list
• in discussion points
• in action items
• anywhere in the output

If a person's name is unknown, refer to them generically:
  "the client"
  "a team member"
  "the warehouse manager"
  "the logistics team"

Never reference a speaker number.

════════════════════════════════════════
ATTENDEE EXTRACTION RULES
════════════════════════════════════════
1. Only include attendee names that are EXPLICITLY present in the transcript
   (as a speaker name OR directly addressed by another participant).

2. NEVER invent, infer, or guess names.

3. NEVER include speaker labels such as:
   Speaker 0, Speaker 1, Speaker 2, etc.

4. If a name is unclear or partially transcribed
   (examples: "screen sir", "sni sir", "sir", "madam"),
   ignore it completely.

5. If a person appears with slight spelling variations,
   include them ONCE using the normalised spelling.

6. Remove all duplicates.

7. Greetings count as valid name mentions:
   "Hi Aditya", "Hello Mina", "Thanks Sri"

8. Only real names should appear in attendees.
   Never include generic roles.

9. If fewer than 2 clearly identifiable names are found,
   set attendees to:
   ["Not clearly identifiable from transcript"]

════════════════════════════════════════
NAME NORMALISATION RULES
════════════════════════════════════════
Correct obvious minor transcription errors only when CERTAIN:

Aditiya → Aditya  
Minna → Mina  
Meena → Mina  
Sree → Sri  

Do NOT guess names that are uncertain.

════════════════════════════════════════
ACTION ITEM TEAM RULES
════════════════════════════════════════
Split action items into exactly two teams:

Client Team
Spikra Team

Use context to determine which team owns the task.

Both teams MUST appear in the output even if empty.

════════════════════════════════════════
MEETING CONTENT RULES
════════════════════════════════════════
1. Do NOT add information that does not appear in the transcript.

2. Do NOT invent systems, tools, or technologies.

3. Summarise discussion clearly and concisely.

4. Do NOT attribute statements to speaker numbers.

5. When referencing participants use neutral wording such as:
   "The client explained..."
   "The team discussed..."
   "The warehouse manager clarified..."

6. Preserve the actual meaning of the conversation.

7. If meeting name or date cannot be determined,
   use:
   "[Meeting Name]"
   "[Meeting Date]"

════════════════════════════════════════
OUTPUT — VALID JSON ONLY
════════════════════════════════════════
{
  "meeting_name": "string",
  "meeting_date": "string",
  "attendees": ["Aditya", "Mina", "Sri"],
  "discussion_points": [
    "concise factual summary"
  ],
  "action_items": [
    {
      "team": "Client Team",
      "items": [{"task": "string", "owner": "name or null"}]
    },
    {
      "team": "Spikra Team",
      "items": [{"task": "string", "owner": "name or null"}]
    }
  ]
}

Return ONLY valid JSON. Do not include markdown or explanations.
"""

# ── OpenAI version (commented out) ───────────────────────────────────────────
# def _generate_mom_openai(resolved_transcript: str, attendee_hint: str, client: OpenAI) -> dict:
#     response = client.chat.completions.create(
#         model="gpt-4o",
#         messages=[
#             {"role": "system", "content": _MOM_SYSTEM_PROMPT},
#             {"role": "user", "content": f"Generate Minutes of Meeting from this transcript.{attendee_hint}\n\nTRANSCRIPT:\n{resolved_transcript}"},
#         ],
#         response_format={"type": "json_object"},
#         temperature=0.1,
#     )
#     return json.loads(response.choices[0].message.content)
# ─────────────────────────────────────────────────────────────────────────────


_SPEAKER_LABEL_RE = re.compile(r"\bSpeaker\s+\d+\b", re.IGNORECASE)


def _strip_speaker_labels(mom: dict) -> dict:
    """
    Safety net: recursively replace any surviving 'Speaker N' references
    in the generated MoM with a neutral phrase.
    Attendees that are still 'Speaker N' are dropped entirely.
    """
    def clean_str(s: str) -> str:
        return _SPEAKER_LABEL_RE.sub("a participant", s)

    def clean(val):
        if isinstance(val, str):
            return clean_str(val)
        if isinstance(val, list):
            return [clean(v) for v in val]
        if isinstance(val, dict):
            return {k: clean(v) for k, v in val.items()}
        return val

    result = clean(mom)

    # Drop any attendee entry that is (or became) just "a participant"
    if isinstance(result.get("attendees"), list):
        result["attendees"] = [
            a for a in result["attendees"]
            if a.strip().lower() not in ("a participant", "")
        ]
        if not result["attendees"]:
            result["attendees"] = ["Not clearly identifiable from transcript"]

    return result


def generate_mom(speaker_transcript: str) -> dict:
    """
    Three-step pipeline (Claude claude-sonnet-4-6):
      1. Resolve 'Speaker N' labels to real names using explicit rules.
      2. Extract all directly-addressed names as confirmed attendees.
      3. Generate MoM with the resolved transcript + confirmed attendee list.
      Post-process: strip any surviving 'Speaker N' labels from the output.
    """
    client = _get_client()

    # ── Step 1: speaker ID → name mapping ────────────────────────────────────
    print("[mom_generator] Step 1: Resolving speaker IDs to names…", flush=True)
    name_mapping = _resolve_speaker_names(speaker_transcript, client)
    print(f"[mom_generator] Speaker mapping: {name_mapping}", flush=True)

    resolved_transcript = (
        _apply_speaker_names(speaker_transcript, name_mapping)
        if name_mapping
        else speaker_transcript
    )

    # ── Step 2: confirmed attendees via direct address ────────────────────────
    print("[mom_generator] Step 2: Extracting directly-addressed names…", flush=True)
    confirmed_attendees = _extract_directly_addressed_names(speaker_transcript, client)
    print(f"[mom_generator] Confirmed attendees: {confirmed_attendees}", flush=True)

    # ── Step 3: generate MoM ─────────────────────────────────────────────────
    print("[mom_generator] Step 3: Generating MoM…", flush=True)
    attendee_hint = (
        f"\nCONFIRMED ATTENDEES (directly addressed by name in transcript): "
        f"{', '.join(confirmed_attendees)}"
        if confirmed_attendees
        else ""
    )

    raw = _claude(
        client,
        system=_MOM_SYSTEM_PROMPT,
        user=(
            f"Generate Minutes of Meeting from this transcript.{attendee_hint}\n\n"
            "REMINDER: Never use 'Speaker N' labels anywhere in your output. "
            "If a person's name is unknown, write 'a participant' or use their role.\n\n"
            "TRANSCRIPT:\n"
            f"{resolved_transcript}"
        ),
        temperature=0.1,
    )
    try:
        mom = _parse_json_response(raw)
        # Safety net: remove any 'Speaker N' that slipped through
        mom = _strip_speaker_labels(mom)
        print(f"[mom_generator] Done. Attendees: {mom.get('attendees')}", flush=True)
        return mom
    except (json.JSONDecodeError, ValueError):
        raise RuntimeError(f"Claude returned invalid JSON: {raw}")
