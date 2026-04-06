const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

const sidebarPlayBtn = document.getElementById("sidebarPlayBtn");
const sidebarStopBtn = document.getElementById("sidebarStopBtn");
const sidebarClearBtn = document.getElementById("sidebarClearBtn");
const transcriptStatus = document.getElementById("transcriptStatus");
const transcriptList = document.getElementById("transcriptList");

let recognition = null;
let mediaRecorder = null;
let mediaStream = null;

let isRecording = false;
let isUploading = false;
let sessionStartTime = 0;
let lastFinalEndMs = 0;

let finalSegments = [];
let interimText = "";
let audioChunks = [];
let mimeType = "";

function setTranscriptStatus(text) {
  transcriptStatus.textContent = text;
}

function nowMs() {
  return Date.now() - sessionStartTime;
}

function formatMs(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function pickMimeType() {
  if (window.MediaRecorder?.isTypeSupported("audio/webm;codecs=opus")) {
    return "audio/webm;codecs=opus";
  }
  if (window.MediaRecorder?.isTypeSupported("audio/webm")) {
    return "audio/webm";
  }
  if (window.MediaRecorder?.isTypeSupported("audio/ogg;codecs=opus")) {
    return "audio/ogg;codecs=opus";
  }
  return "";
}

function buildSessionName() {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `recording_${timestamp}`;
}

function renderTranscript() {
  transcriptList.innerHTML = "";

  if (!finalSegments.length && !interimText) {
    transcriptList.innerHTML = `<div class="transcript-empty">No transcript yet.</div>`;
    return;
  }

  for (const seg of finalSegments) {
    const box = document.createElement("div");
    box.className = `transcript-segment ${seg.selected ? "selected" : ""}`;
    box.innerHTML = `
      <div class="transcript-meta">
        <span>${formatMs(seg.startMs)} – ${formatMs(seg.endMs)}</span>
        <span>${seg.selected ? "selected" : "click to select"}</span>
      </div>
      <div class="transcript-text">${escapeHtml(seg.text)}</div>
    `;

    box.addEventListener("click", () => {
      seg.selected = !seg.selected;
      renderTranscript();
    });

    transcriptList.appendChild(box);
  }

  if (interimText) {
    const interimBox = document.createElement("div");
    interimBox.className = "transcript-segment interim";
    interimBox.innerHTML = `
      <div class="transcript-meta">
        <span>interim</span>
      </div>
      <div class="transcript-text">${escapeHtml(interimText)}</div>
    `;
    transcriptList.appendChild(interimBox);
  }

  transcriptList.scrollTop = transcriptList.scrollHeight;
}

async function uploadWholeRecording() {
  if (!audioChunks.length) {
    setTranscriptStatus("Stopped.\nNo audio chunks to upload.");
    return;
  }

  const ext = mimeType.includes("ogg") ? "ogg" : "webm";
  const fullBlob = new Blob(audioChunks, { type: mimeType });

  const form = new FormData();
  form.append("audio", fullBlob, `full_recording.${ext}`);
  form.append("session_name", buildSessionName());

  isUploading = true;
  setTranscriptStatus(
    `Uploading recording...\n${finalSegments.length} transcript boxes.\n${audioChunks.length} audio chunks recorded.`
  );

  try {
    const res = await fetch("http://127.0.0.1:5001/save_recording", {
      method: "POST",
      body: form,
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || "Upload failed");
    }

    setTranscriptStatus(
      `Stopped and uploaded.\n${finalSegments.length} transcript boxes.\n${audioChunks.length} audio chunks recorded.\nSaved: ${data.filename || "ok"}`
    );
  } catch (err) {
    console.error("Upload error:", err);
    setTranscriptStatus(
      `Stopped, but upload failed.\n${finalSegments.length} transcript boxes.\n${audioChunks.length} audio chunks recorded.`
    );
  } finally {
    isUploading = false;
  }
}

async function startTranscriptRecording() {
  if (!SpeechRecognition) {
    setTranscriptStatus("SpeechRecognition not supported in this browser.");
    return;
  }

  mimeType = pickMimeType();
  if (!mimeType) {
    setTranscriptStatus("No supported audio recording format found.");
    return;
  }

  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });

  mediaRecorder = new MediaRecorder(mediaStream, { mimeType });
  audioChunks = [];
  finalSegments = [];
  interimText = "";
  lastFinalEndMs = 0;
  sessionStartTime = Date.now();

  mediaRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) {
      audioChunks.push(event.data);
    }
  };

  mediaRecorder.start(1000);

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    isRecording = true;
    sidebarPlayBtn.disabled = true;
    sidebarStopBtn.disabled = false;
    sidebarClearBtn.disabled = true;
    setTranscriptStatus("Listening...");
  };

  recognition.onresult = (event) => {
    interimText = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const text = event.results[i][0].transcript.trim();
      if (!text) continue;

      if (event.results[i].isFinal) {
        const endMs = nowMs();
        const startMs = lastFinalEndMs;

        finalSegments.push({
          text,
          startMs,
          endMs,
          selected: false,
        });

        lastFinalEndMs = endMs;
      } else {
        interimText += (interimText ? " " : "") + text;
      }
    }

    renderTranscript();
  };

  recognition.onerror = (event) => {
    console.error("Speech recognition error:", event.error);
    setTranscriptStatus(`Error: ${event.error}`);
  };

  recognition.onend = () => {
    if (isRecording) {
      try {
        recognition.start();
      } catch (err) {
        console.error(err);
      }
    } else if (!isUploading) {
      sidebarPlayBtn.disabled = false;
      sidebarStopBtn.disabled = true;
      sidebarClearBtn.disabled = false;
      setTranscriptStatus(
        `Stopped.\n${finalSegments.length} transcript boxes.\n${audioChunks.length} audio chunks recorded.`
      );
    }
  };

  recognition.start();
  renderTranscript();
}

async function stopTranscriptRecording() {
  isRecording = false;

  if (recognition) {
    try {
      recognition.stop();
    } catch (err) {
      console.error(err);
    }
  }

  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    await new Promise((resolve) => {
      mediaRecorder.onstop = resolve;
      mediaRecorder.stop();
    });
  }

  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }

  sidebarPlayBtn.disabled = false;
  sidebarStopBtn.disabled = true;
  sidebarClearBtn.disabled = false;

  renderTranscript();
  await uploadWholeRecording();
}

function clearTranscriptSidebar() {
  if (isRecording || isUploading) return;

  finalSegments = [];
  interimText = "";
  audioChunks = [];
  lastFinalEndMs = 0;
  renderTranscript();
  setTranscriptStatus("Idle");
}

sidebarPlayBtn?.addEventListener("click", async () => {
  try {
    await startTranscriptRecording();
  } catch (err) {
    console.error(err);
    setTranscriptStatus("Failed to start.");
  }
});

sidebarStopBtn?.addEventListener("click", async () => {
  try {
    await stopTranscriptRecording();
  } catch (err) {
    console.error(err);
    setTranscriptStatus("Failed to stop.");
  }
});

sidebarClearBtn?.addEventListener("click", () => {
  clearTranscriptSidebar();
});

renderTranscript();