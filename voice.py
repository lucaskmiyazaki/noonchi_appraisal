import os
import json
import base64
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from flask import Flask, render_template_string, request, jsonify
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

# ------------------------------------------------------------
# Minimal pseudo-live transcript + diarization app
# ------------------------------------------------------------
# How it works:
# - Browser records audio chunks with MediaRecorder
# - Every few seconds, browser POSTs one chunk to Flask
# - Flask stores chunk files and appends transcript results after processing
# - Browser polls /transcript/<session_id> every 2s and updates sidebar
#
# Requirements:
#   pip install flask faster-whisper pyannote.audio
#   sudo apt install ffmpeg
#
# Env:
#   export HUGGINGFACE_TOKEN=hf_xxx
#   export WHISPER_MODEL=base.en
#   export WHISPER_DEVICE=cpu
#   export WHISPER_COMPUTE_TYPE=int8
# ------------------------------------------------------------

app = Flask(__name__)

HF_TOKEN = os.environ.get("HUGGINGFACE_TOKEN")
if not HF_TOKEN:
    raise RuntimeError("Set HUGGINGFACE_TOKEN before running this app.")

WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL", "base.en")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

print("Loading Whisper...")
whisper_model = WhisperModel(
    WHISPER_MODEL_NAME,
    device=WHISPER_DEVICE,
    compute_type=WHISPER_COMPUTE_TYPE,
)

print("Loading pyannote...")
diarization_pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-community-1",
    token=HF_TOKEN,
)

HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pseudo-live Transcript</title>
  <style>
    body { margin: 0; font-family: Inter, Arial, sans-serif; background: #0f172a; color: #e5e7eb; }
    .wrap { display: grid; grid-template-columns: 1fr 360px; height: 100vh; }
    .main { padding: 24px; }
    .sidebar { border-left: 1px solid #334155; background: #111827; overflow: hidden; display:flex; flex-direction:column; }
    .head { padding: 16px; border-bottom: 1px solid #334155; }
    .transcript { padding: 12px; overflow-y: auto; flex:1; display:flex; flex-direction:column; gap:10px; }
    .seg { background:#1f2937; border:1px solid #334155; border-radius:14px; padding:10px; }
    .meta { display:flex; justify-content:space-between; font-size:12px; color:#94a3b8; margin-bottom:6px; }
    .speaker { font-weight:700; color:#e5e7eb; }
    button { border:none; border-radius:999px; padding:12px 18px; font-weight:700; cursor:pointer; margin-right:10px; }
    .start { background:#22c55e; color:#052e16; }
    .stop { background:#ef4444; color:white; }
    #status { margin-top:14px; color:#94a3b8; }
    .note { margin-top:16px; color:#94a3b8; max-width:600px; line-height:1.5; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="main">
      <h1>Pseudo-live transcript</h1>
      <button id="startBtn" class="start">Start</button>
      <button id="stopBtn" class="stop" disabled>Stop</button>
      <div id="status">Idle</div>
      <div class="note">Every 4 seconds, the browser sends one audio chunk to Flask. The server processes each chunk and the sidebar refreshes by polling.</div>
    </div>
    <aside class="sidebar">
      <div class="head">
        <strong>Transcript</strong>
      </div>
      <div id="transcript" class="transcript"></div>
    </aside>
  </div>

  <script>
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const statusEl = document.getElementById('status');
    const transcriptEl = document.getElementById('transcript');

    let mediaRecorder = null;
    let stream = null;
    let pollTimer = null;
    let sessionId = null;

    function setStatus(s) { statusEl.textContent = s; }
    function t(sec) {
      const m = String(Math.floor(sec / 60)).padStart(2, '0');
      const s = String(Math.floor(sec % 60)).padStart(2, '0');
      return `${m}:${s}`;
    }

    function renderTranscript(segments) {
      transcriptEl.innerHTML = '';
      if (!segments.length) {
        transcriptEl.innerHTML = '<div class="seg">No transcript yet.</div>';
        return;
      }
      for (const seg of segments) {
        const el = document.createElement('div');
        el.className = 'seg';
        el.innerHTML = `
          <div class="meta">
            <span class="speaker">${escapeHtml(seg.speaker_label)}</span>
            <span>${t(seg.start)}–${t(seg.end)}</span>
          </div>
          <div>${escapeHtml(seg.text)}</div>
        `;
        transcriptEl.appendChild(el);
      }
      transcriptEl.scrollTop = transcriptEl.scrollHeight;
    }

    function escapeHtml(str) {
      return String(str)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    async function pollTranscript() {
      if (!sessionId) return;
      const res = await fetch(`/transcript/${sessionId}`);
      const data = await res.json();
      renderTranscript(data.segments || []);
    }

    async function startRecording() {
      sessionId = crypto.randomUUID();
      await fetch('/start_session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      });

      stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      let mimeType = '';
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        mimeType = 'audio/webm;codecs=opus';
      } else if (MediaRecorder.isTypeSupported('audio/webm')) {
        mimeType = 'audio/webm';
      } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
        mimeType = 'audio/ogg;codecs=opus';
      } else {
        throw new Error('No supported audio recorder format found');
      }

      mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorder.ondataavailable = async (event) => {
        if (!event.data || event.data.size === 0) return;
        const form = new FormData();
        form.append('session_id', sessionId);
        form.append('audio', event.data, `chunk.${mimeType.includes('ogg') ? 'ogg' : 'webm'}`);
        await fetch('/upload_chunk', { method: 'POST', body: form });
      };

      mediaRecorder.start(4000);
      pollTimer = setInterval(pollTranscript, 2000);
      startBtn.disabled = true;
      stopBtn.disabled = false;
      setStatus('Recording');
    }

    async function stopRecording() {
      if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
      if (stream) stream.getTracks().forEach(track => track.stop());
      stream = null;
      await fetch('/stop_session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      });
      await pollTranscript();
      clearInterval(pollTimer);
      startBtn.disabled = false;
      stopBtn.disabled = true;
      setStatus('Stopped');
    }

    startBtn.onclick = async () => {
      try {
        await startRecording();
      } catch (e) {
        console.error(e);
        setStatus('Failed to start');
      }
    };

    stopBtn.onclick = stopRecording;
    renderTranscript([]);
  </script>
</body>
</html>
"""


class SessionState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.dir = Path(tempfile.mkdtemp(prefix=f"pseudo_live_{session_id}_"))
        self.next_chunk_index = 0
        self.segments: List[Dict[str, Any]] = []
        self.speaker_map: Dict[str, str] = {}
        self.next_speaker_number = 1


sessions: Dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    if session_id not in sessions:
        sessions[session_id] = SessionState(session_id)
    return sessions[session_id]


def convert_to_wav(src_path: Path, dst_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(src_path),
        "-ac", "1", "-ar", "16000", str(dst_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)


def transcribe_chunk(wav_path: Path) -> List[Dict[str, Any]]:
    segments, _ = whisper_model.transcribe(
        str(wav_path),
        beam_size=1,
        best_of=1,
        vad_filter=True,
        word_timestamps=False,
    )
    out = []
    for s in segments:
        text = (s.text or "").strip()
        if text:
            out.append({"start": float(s.start), "end": float(s.end), "text": text})
    return out


def diarize_chunk(wav_path: Path) -> List[Dict[str, Any]]:
    diar = diarization_pipeline(str(wav_path))
    out = []
    for turn, _, speaker in diar.itertracks(yield_label=True):
        out.append({"start": float(turn.start), "end": float(turn.end), "speaker": str(speaker)})
    return out


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def label_chunk(session: SessionState, transcript: List[Dict[str, Any]], diar: List[Dict[str, Any]], offset: float) -> List[Dict[str, Any]]:
    labeled = []
    for seg in transcript:
        best_speaker = None
        best_overlap = 0.0
        for d in diar:
            ov = overlap(seg["start"], seg["end"], d["start"], d["end"])
            if ov > best_overlap:
                best_overlap = ov
                best_speaker = d["speaker"]

        if best_speaker is None:
            speaker_label = "Unknown"
        else:
            if best_speaker not in session.speaker_map:
                session.speaker_map[best_speaker] = f"Speaker {session.next_speaker_number}"
                session.next_speaker_number += 1
            speaker_label = session.speaker_map[best_speaker]

        labeled.append({
            "start": seg["start"] + offset,
            "end": seg["end"] + offset,
            "text": seg["text"],
            "speaker_label": speaker_label,
        })
    return labeled


@app.route("/")
def index():
    return render_template_string(HTML)


@app.post("/start_session")
def start_session():
    data = request.get_json(force=True)
    session_id = data["session_id"]
    sessions[session_id] = SessionState(session_id)
    return jsonify({"ok": True})


@app.post("/upload_chunk")
def upload_chunk():
    session_id = request.form["session_id"]
    session = get_session(session_id)
    file = request.files["audio"]

    ext = Path(file.filename).suffix or ".webm"
    raw_path = session.dir / f"chunk_{session.next_chunk_index:04d}{ext}"
    wav_path = session.dir / f"chunk_{session.next_chunk_index:04d}.wav"
    file.save(raw_path)

    convert_to_wav(raw_path, wav_path)
    transcript = transcribe_chunk(wav_path)
    diar = diarize_chunk(wav_path)

    offset = session.next_chunk_index * 4.0
    labeled = label_chunk(session, transcript, diar, offset)
    session.segments.extend(labeled)
    session.next_chunk_index += 1

    return jsonify({"ok": True, "added": len(labeled)})


@app.get("/transcript/<session_id>")
def get_transcript(session_id: str):
    session = get_session(session_id)
    return jsonify({"segments": session.segments})


@app.post("/stop_session")
def stop_session():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5008, debug=True)
