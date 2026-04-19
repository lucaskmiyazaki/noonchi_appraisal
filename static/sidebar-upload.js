const sidebarAudioInput = document.getElementById("sidebarAudioInput");
const sidebarUploadBtn = document.getElementById("sidebarUploadBtn");
const sidebarBackBtn = document.getElementById("sidebarBackBtn");
const sidebarPlayBtn = document.getElementById("sidebarPlayBtn");
const sidebarClearBtn = document.getElementById("sidebarClearBtn");
const transcriptStatus = document.getElementById("transcriptStatus");
const transcriptFileName = document.getElementById("transcriptFileName");
const sessionList = document.getElementById("sessionList");
const transcriptList = document.getElementById("transcriptList");
const sessionNameInput = document.getElementById("sessionNameInput");

import { syncReflectionTabs } from "./tabs.js";

const audioPlayer = new Audio();

let audioData = null;
let activeChunkId = null;
let sessions = [];
let sidebarView = "list";

function dispatchGraphPlayState() {
  const selectedCount = audioData?.transcript?.filter((segment) => segment.selected).length || 0;
  window.dispatchEvent(new CustomEvent("graph-play-state", {
    detail: {
      hasSession: Boolean(audioData?.id),
      hasSelection: selectedCount > 0,
    },
  }));
}

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

function setSidebarView(view) {
  sidebarView = view;

  if (sessionList) {
    sessionList.hidden = view !== "list";
  }

  if (transcriptList) {
    transcriptList.hidden = view !== "transcript";
  }

  if (sidebarBackBtn) {
    sidebarBackBtn.hidden = view !== "transcript";
  }

  if (sidebarUploadBtn) {
    sidebarUploadBtn.hidden = view !== "list";
  }

  if (sidebarPlayBtn) {
    sidebarPlayBtn.hidden = view !== "transcript";
  }

  if (sidebarClearBtn) {
    sidebarClearBtn.hidden = view !== "transcript";
  }
}

function formatSessionTimestamp(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return date.toLocaleString();
}

function renderSessionList() {
  if (!sessionList) {
    return;
  }

  sessionList.innerHTML = "";

  if (!sessions.length) {
    sessionList.innerHTML = '<div class="session-list-empty">No sessions yet. Upload audio to create one.</div>';
    return;
  }

  for (const session of sessions) {
    const item = document.createElement("div");
    const isActive = session.id === audioData?.id;
    item.className = `session-item ${isActive ? "active" : ""}`.trim();
    item.dataset.id = session.id;
    const metaParts = [session.originalName, `${session.segmentCount || 0} transcript boxes`, formatSessionTimestamp(session.uploadedAt)].filter(Boolean);
    item.innerHTML = `
      <button class="session-item-main" type="button">
        <span class="session-item-title">${escapeHtml(session.sessionName || session.originalName || "Untitled session")}</span>
        <span class="session-item-meta">${escapeHtml(metaParts.join(" • "))}</span>
      </button>
      <button class="session-item-delete" type="button" aria-label="Delete recording" title="Delete recording">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 6h2v8h-2V9zm4 0h2v8h-2V9zM7 9h2v8H7V9zm1 12a2 2 0 0 1-2-2V7h12v12a2 2 0 0 1-2 2H8z"></path>
        </svg>
      </button>
    `;

    const mainButton = item.querySelector(".session-item-main");
    const deleteButton = item.querySelector(".session-item-delete");

    mainButton?.addEventListener("click", async () => {
      await loadAudioById(session.id);
    });

    deleteButton?.addEventListener("click", async (event) => {
      event.stopPropagation();

      const confirmed = window.confirm(`Delete recording "${session.sessionName || session.originalName || "Untitled session"}"? This will also delete its transcript and linked reflections.`);
      if (!confirmed) {
        return;
      }

      deleteButton.disabled = true;

      try {
        const response = await fetch(`/api/audio/${encodeURIComponent(session.id)}`, {
          method: "DELETE",
        });
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
          throw new Error(data.error || "Failed to delete recording.");
        }

        if (audioData?.id === session.id) {
          showSessionListView();
          setTranscriptStatus("Recording deleted.");
        }

        await loadSessions();
      } catch (error) {
        console.error(error);
        setTranscriptStatus(error.message || "Failed to delete recording.");
      } finally {
        deleteButton.disabled = false;
      }
    });

    sessionList.appendChild(item);
  }
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
    renderSessionList();
    renderTranscript();
    setTranscriptStatus("Select a session or upload audio.");
    setSidebarView("list");
    dispatchGraphPlayState();
    return;
  }

  const segmentCount = Array.isArray(data.transcript) ? data.transcript.length : 0;
  setTranscriptStatus(`Loaded transcript.\n${segmentCount} transcript boxes.`);
  renderSessionList();
  renderTranscript();
  setSidebarView("transcript");
  dispatchGraphPlayState();
}

function clearLoadedAudio() {
  setLoadedAudio(null);
}

function showSessionListView() {
  syncReflectionTabs([]);
  clearLoadedAudio();
}

function renderTranscript() {
  transcriptList.innerHTML = "";

  if (!audioData?.transcript?.length) {
    transcriptList.innerHTML = '<div class="transcript-empty">Select a session from the list above or upload audio to create a new one.</div>';
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
      dispatchGraphPlayState();
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

    await loadSessions();
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
    await loadReflectionTabsForAudio(data.id, data.sessionName);
    return true;
  } catch (error) {
    console.error(error);
    return false;
  }
}

async function loadReflectionTabsForAudio(audioId, sessionName) {
  if (!audioId) {
    syncReflectionTabs([]);
    return;
  }

  try {
    const response = await fetch(`/api/audio/${encodeURIComponent(audioId)}/reflections`);
    const data = await response.json();

    if (!response.ok) {
      syncReflectionTabs([]);
      return;
    }

    const reflections = Array.isArray(data.reflections)
      ? data.reflections
          .map((reflection) => ({
            tree: reflection.tree,
            sessionName: data.session || sessionName,
            startMs: Number(reflection.startms),
            endMs: Number(reflection.endms),
            reflectionFile: reflection.reflection_tree_file || '',
          }))
          .filter((reflection) => Boolean(reflection.tree))
      : [];

    syncReflectionTabs(reflections);
  } catch (error) {
    console.error(error);
    syncReflectionTabs([]);
  }
}

async function loadSessions() {
  try {
    const response = await fetch("/api/audio/sessions");
    const data = await response.json();

    if (!response.ok) {
      sessions = [];
      renderSessionList();
      setTranscriptStatus("Could not load sessions.");
      return;
    }

    sessions = Array.isArray(data.sessions) ? data.sessions : [];
    renderSessionList();
  } catch (error) {
    console.error(error);
    sessions = [];
    renderSessionList();
    setTranscriptStatus("Could not load sessions.");
  }
}

sidebarUploadBtn?.addEventListener("click", () => {
  sidebarAudioInput?.click();
});

sidebarBackBtn?.addEventListener("click", () => {
  showSessionListView();
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
  clearLoadedAudio();
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

export function clearSelectedTranscriptSegments() {
  if (!audioData?.transcript?.length) {
    return;
  }

  audioData.transcript.forEach((segment) => {
    segment.selected = false;
  });

  renderTranscript();
  dispatchGraphPlayState();
}

export function getSessionName() {
  return getCurrentSessionName();
}

if (sessionNameInput && !sessionNameInput.value.trim()) {
  syncSessionNameInput("audio");
}

loadSessions();
clearLoadedAudio();
setSidebarView("list");
renderTranscript();
dispatchGraphPlayState();