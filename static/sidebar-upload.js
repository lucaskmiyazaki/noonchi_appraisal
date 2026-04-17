const sidebarAudioInput = document.getElementById("sidebarAudioInput");
const sidebarUploadBtn = document.getElementById("sidebarUploadBtn");
const sidebarPlayBtn = document.getElementById("sidebarPlayBtn");
const sidebarClearBtn = document.getElementById("sidebarClearBtn");
const transcriptStatus = document.getElementById("transcriptStatus");
const transcriptFileName = document.getElementById("transcriptFileName");
const transcriptList = document.getElementById("transcriptList");
const sessionNameInput = document.getElementById("sessionNameInput");

const audioPlayer = new Audio();

let audioData = null;
let activeChunkId = null;

function setTranscriptStatus(text) {
  transcriptStatus.textContent = text;
}

function formatSeconds(seconds) {
  const totalSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const remainder = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${remainder}`;
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function buildSessionNameFromFilename(filename) {
  const rawName = String(filename || "").trim();
  const withoutExtension = rawName.replace(/\.[^./\\]+$/, "");
  const normalized = withoutExtension
    .replace(/\s+/g, "_")
    .replace(/[^a-zA-Z0-9_-]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");

  return normalized || "audio";
}

function getCurrentSessionName() {
  const rawValue = sessionNameInput?.value.trim();
  return rawValue || "audio";
}

function syncSessionNameInput(value) {
  if (!sessionNameInput) {
    return;
  }

  sessionNameInput.value = value || "audio";
}

function setLoadedAudio(data) {
  audioData = data;
  activeChunkId = null;
  audioPlayer.pause();
  audioPlayer.currentTime = 0;
  audioPlayer.src = data?.audioUrl || "";
  sidebarPlayBtn.disabled = !data?.audioUrl;
  transcriptFileName.textContent = data?.originalName ? `File: ${data.originalName}` : "";
  if (data?.sessionName) {
    syncSessionNameInput(data.sessionName);
  }

  if (!data) {
    renderTranscript();
    setTranscriptStatus("Idle");
    return;
  }

  const segmentCount = Array.isArray(data.transcript) ? data.transcript.length : 0;
  setTranscriptStatus(`Loaded transcript.\n${segmentCount} transcript boxes.`);
  renderTranscript();
}

function clearLoadedAudio() {
  setLoadedAudio(null);
}

function renderTranscript() {
  transcriptList.innerHTML = "";

  if (!audioData?.transcript?.length) {
    transcriptList.innerHTML = '<div class="transcript-empty">Upload audio to generate a transcript. The latest uploaded audio is loaded automatically when available.</div>';
    return;
  }

  for (const segment of audioData.transcript) {
    const box = document.createElement("div");
    const isActive = segment.id === activeChunkId;
    box.className = `transcript-segment ${segment.selected ? "selected" : ""} ${isActive ? "active" : ""}`.trim();
    box.dataset.id = String(segment.id);
    box.innerHTML = `
      <div class="transcript-meta">
        <span>${formatSeconds(segment.start)} - ${formatSeconds(segment.end)}</span>
        <span>${segment.selected ? "selected" : isActive ? "playing" : "click to seek/select"}</span>
      </div>
      <div class="transcript-text">${escapeHtml(segment.text)}</div>
    `;

    box.addEventListener("click", () => {
      segment.selected = !segment.selected;
      audioPlayer.currentTime = Number(segment.start) || 0;
      activeChunkId = segment.id;
      renderTranscript();
    });

    transcriptList.appendChild(box);
  }
}

function updateActiveChunk() {
  if (!audioData?.transcript?.length) {
    activeChunkId = null;
    renderTranscript();
    return;
  }

  const currentTime = audioPlayer.currentTime;
  const activeSegment = audioData.transcript.find((segment) => {
    return currentTime >= Number(segment.start) && currentTime < Number(segment.end);
  });
  const nextActiveId = activeSegment ? activeSegment.id : null;

  if (nextActiveId !== activeChunkId) {
    activeChunkId = nextActiveId;
    renderTranscript();
  }
}

async function uploadAudioFile(file) {
  if (!file) {
    setTranscriptStatus("Select an audio file first.");
    return;
  }

  setTranscriptStatus("Uploading and transcribing audio...");
  sidebarUploadBtn.disabled = true;
  sidebarPlayBtn.disabled = true;

  const formData = new FormData();
  formData.append("audio", file);
  formData.append("session_name", getCurrentSessionName());

  try {
    const response = await fetch("/api/audio/upload", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Upload failed.");
    }

    localStorage.setItem("latestAudioId", data.id);
    setLoadedAudio(data);
  } catch (error) {
    console.error(error);
    setTranscriptStatus(error.message || "Failed to upload audio.");
  } finally {
    sidebarUploadBtn.disabled = false;
    if (sidebarAudioInput) {
      sidebarAudioInput.value = "";
    }
  }
}

async function loadAudioById(audioId) {
  if (!audioId) {
    return false;
  }

  try {
    const response = await fetch(`/api/audio/${encodeURIComponent(audioId)}`);
    const data = await response.json();

    if (!response.ok) {
      return false;
    }

    setLoadedAudio(data);
    return true;
  } catch (error) {
    console.error(error);
    return false;
  }
}

async function loadLatestAudio() {
  const sessionName = getCurrentSessionName();
  const params = new URLSearchParams();
  if (sessionName) {
    params.set("session_name", sessionName);
  }

  try {
    const response = await fetch(`/api/audio/latest?${params.toString()}`);
    const data = await response.json();

    if (!response.ok) {
      clearLoadedAudio();
      setTranscriptStatus("No uploaded audio yet.");
      return;
    }

    localStorage.setItem("latestAudioId", data.id);
    setLoadedAudio(data);
  } catch (error) {
    console.error(error);
    setTranscriptStatus("Could not load latest audio.");
  }
}

sidebarUploadBtn?.addEventListener("click", () => {
  sidebarAudioInput?.click();
});

sidebarAudioInput?.addEventListener("change", async () => {
  const file = sidebarAudioInput.files?.[0];
  if (file) {
    syncSessionNameInput(buildSessionNameFromFilename(file.name));
  }
  await uploadAudioFile(file);
});

sidebarPlayBtn?.addEventListener("click", async () => {
  if (!audioData?.audioUrl) {
    return;
  }

  try {
    if (audioPlayer.paused) {
      await audioPlayer.play();
    } else {
      audioPlayer.pause();
    }
  } catch (error) {
    console.error(error);
    setTranscriptStatus("Audio playback failed.");
  }
});

sidebarClearBtn?.addEventListener("click", () => {
  audioPlayer.pause();
  localStorage.removeItem("latestAudioId");
  clearLoadedAudio();
});

sessionNameInput?.addEventListener("change", () => {
  loadLatestAudio();
});

audioPlayer.addEventListener("play", () => {
  sidebarPlayBtn.textContent = "Pause";
  updateActiveChunk();
});

audioPlayer.addEventListener("pause", () => {
  sidebarPlayBtn.textContent = "Play";
});

audioPlayer.addEventListener("ended", () => {
  activeChunkId = null;
  sidebarPlayBtn.textContent = "Play";
  renderTranscript();
});

audioPlayer.addEventListener("timeupdate", () => {
  updateActiveChunk();
});

export function getSelectedTimeRange() {
  const selected = audioData?.transcript?.filter((segment) => segment.selected) || [];
  if (!selected.length) {
    return null;
  }

  return {
    startMs: Math.min(...selected.map((segment) => Number(segment.start) * 1000)),
    endMs: Math.max(...selected.map((segment) => Number(segment.end) * 1000)),
    sessionName: getCurrentSessionName(),
  };
}

export function getSessionName() {
  return getCurrentSessionName();
}

if (sessionNameInput && !sessionNameInput.value.trim()) {
  syncSessionNameInput("audio");
}

const savedAudioId = localStorage.getItem("latestAudioId");
if (savedAudioId) {
  loadAudioById(savedAudioId).then((loaded) => {
    if (!loaded) {
      loadLatestAudio();
    }
  });
} else {
  loadLatestAudio();
}

renderTranscript();