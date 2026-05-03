const sidebarAudioInput = document.getElementById("sidebarAudioInput");
const sidebarUploadBtn = document.getElementById("sidebarUploadBtn");
const sidebarBackBtn = document.getElementById("sidebarBackBtn");
const sidebarPlayBtn = document.getElementById("sidebarPlayBtn");
const sidebarClearBtn = document.getElementById("sidebarClearBtn");
const generateReflectionBtn = document.getElementById("generateReflectionBtn");
const transcriptStatus = document.getElementById("transcriptStatus");
const transcriptFileName = document.getElementById("transcriptFileName");
const sessionList = document.getElementById("sessionList");
const transcriptList = document.getElementById("transcriptList");
const sessionNameInput = document.getElementById("sessionNameInput");
const saveSessionNameBtn = document.getElementById("saveSessionNameBtn");
const sessionUserInput = document.getElementById("sessionUserInput");
const emotionSessionBtn = document.getElementById("emotionSessionBtn");
const intentSessionBtn = document.getElementById("intentSessionBtn");
const uploadPanel = document.getElementById("uploadPanel");
const uploadProgressBar = document.getElementById("uploadProgressBar");
const uploadLog = document.getElementById("uploadLog");

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

function syncSessionUserInput(value) {
  if (!sessionUserInput) return;
  sessionUserInput.value = value || '';
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

  syncGenerateReflectionBtn();
}

async function syncGenerateReflectionBtn() {
  if (!generateReflectionBtn) return;
  if (sidebarView !== 'transcript') {
    generateReflectionBtn.hidden = true;
    return;
  }
  const { getActiveBoard } = await import('./board.js');
  const board = getActiveBoard();
  generateReflectionBtn.hidden = board?.kind !== 'intent';
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
        <span class="session-item-title">${escapeHtml((session.displayName || session.sessionName || session.originalName || "Untitled session") + (session.username ? ' — ' + session.username : ''))}</span>
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
      if (document.body.dataset.sessionNav === 'true') {
        const sessionName = session.sessionName || session.originalName || '';
        window.location.href = `/wizard/${encodeURIComponent(sessionName)}`;
        return;
      }
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

function syncSessionNavBtns() {
  // Always use the stable sessionName (not the displayName input) for URL routing
  const session = audioData?.sessionName || getCurrentSessionName();
  if (session && audioData) {
    if (emotionSessionBtn) { emotionSessionBtn.href = `/wizard/${encodeURIComponent(session)}/emotion`; emotionSessionBtn.hidden = false; }
    if (intentSessionBtn) { intentSessionBtn.href = `/wizard/${encodeURIComponent(session)}/intent`; intentSessionBtn.hidden = false; }
  } else {
    if (emotionSessionBtn) emotionSessionBtn.hidden = true;
    if (intentSessionBtn) intentSessionBtn.hidden = true;
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
    syncSessionNameInput(data.displayName || data.sessionName);
  }
  syncSessionUserInput(data?.username || '');

  if (!data) {
    renderSessionList();
    renderTranscript();
    setTranscriptStatus("Select a session or upload audio.");
    setSidebarView("list");
    dispatchGraphPlayState();
    if (typeof window.onPipelineAudioLoaded === "function") {
      window.onPipelineAudioLoaded(null);
    }
    return;
  }

  const segmentCount = Array.isArray(data.transcript) ? data.transcript.length : 0;
  setTranscriptStatus(`Loaded transcript.\n${segmentCount} transcript boxes.`);
  renderSessionList();
  renderTranscript();
  setSidebarView("transcript");
  dispatchGraphPlayState();
  syncSessionNavBtns();
  if (typeof window.onPipelineAudioLoaded === "function") {
    window.onPipelineAudioLoaded(data.id);
  }
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
      import('./board.js').then(({ getActiveBoard, loadGraph }) => {
        const board = getActiveBoard();
        const isIntentBoard = board?.kind === 'intent';

        // On intent boards, only one segment can be selected at a time
        if (isIntentBoard) {
          audioData.transcript.forEach((s) => { s.selected = false; });
          segment.selected = true;
        } else {
          segment.selected = !segment.selected;
        }

        audioPlayer.currentTime = Number(segment.start) || 0;
        activeChunkId = segment.id;
        renderTranscript();
        dispatchGraphPlayState();

        // Show matching intent diagram for this segment
        if (!isIntentBoard || !board.metadata?.intentFile) return;

        let diagrams = null;
        if (Array.isArray(board.metadata?.intentData?.diagrams)) {
          diagrams = board.metadata.intentData.diagrams;
        } else if (Array.isArray(window.lastIntentDiagrams)) {
          diagrams = window.lastIntentDiagrams;
        } else if (Array.isArray(board.graph?.diagrams)) {
          diagrams = board.graph.diagrams;
        }
        if (!diagrams) return;

        const segStartSec = Number(segment.start);
        const found = diagrams.find((d) => {
          const dStart = Number(d.startms) / 1000;
          const dEnd = Number(d.endms) / 1000;
          return segStartSec === dStart || (segStartSec >= dStart && segStartSec < dEnd);
        });
        if (found) {
          loadGraph(found);
          // Update board metadata so Save Intent patches the correct diagram
          board.metadata.diagramStartMs = found.startms ?? null;
          board.metadata.diagramEndMs = found.endms ?? null;
        }
      }).catch((err) => console.error('[Transcript Click] Error:', err));
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

function setUploadProgress(pct) {
  if (!uploadPanel || !uploadProgressBar) return;
  if (pct == null) {
    uploadPanel.hidden = true;
    uploadProgressBar.style.width = "0%";
    if (uploadLog) uploadLog.textContent = "";
    transcriptStatus?.classList.remove("status-transcribing");
  } else {
    uploadPanel.hidden = false;
    uploadProgressBar.style.width = `${Math.min(100, Math.round(pct))}%`;
    transcriptStatus?.classList.add("status-transcribing");
  }
}

function appendUploadLog(text) {
  if (!uploadLog || !text) return;
  const line = document.createElement("div");
  line.textContent = text;
  uploadLog.appendChild(line);
  uploadLog.scrollTop = uploadLog.scrollHeight;
}

const UPLOAD_JOB_KEY = "upload_pending_job_id";

function saveUploadJob(jobId) {
  try { localStorage.setItem(UPLOAD_JOB_KEY, jobId); } catch { /* ignore */ }
}

function clearUploadJob() {
  try { localStorage.removeItem(UPLOAD_JOB_KEY); } catch { /* ignore */ }
}

function getSavedUploadJob() {
  try { return localStorage.getItem(UPLOAD_JOB_KEY) || null; } catch { return null; }
}

/** Listen to an upload SSE stream and update UI. Returns a promise that resolves when done/error. */
function followUploadJob(jobId, startPct = 50) {
  return new Promise((resolve) => {
    setUploadProgress(startPct);
    setTranscriptStatus("Transcribing audio\u2026");
    appendUploadLog("Transcribing audio with Whisper\u2026");

    const es = new EventSource(`/api/audio/upload/job/${encodeURIComponent(jobId)}/stream`);
    let settled = false;

    // clearJob=true: server confirmed done/error → clear localStorage
    // clearJob=false: connection dropped (page unload/refresh) → keep for reconnect
    function finish(clearJob = true) {
      if (!settled) { settled = true; es.close(); if (clearJob) clearUploadJob(); resolve(); }
    }

    es.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        // Job vanished (already finished before page reloaded)
        if (data.status === "error" && data.message === "Job not found") {
          clearUploadJob();
          setUploadProgress(null);
          finish(false);
          return;
        }
        if (data.progress != null) {
          setUploadProgress(startPct + data.progress * ((100 - startPct) / 100));
        }
        if (data.message) {
          setTranscriptStatus(data.message);
          appendUploadLog(data.message);
        }
        if (data.status === "done") {
          setUploadProgress(100);
          loadSessions()
            .then(() => setLoadedAudio(data.record))
            .catch(() => {})
            .finally(() => { setUploadProgress(null); finish(true); });
        } else if (data.status === "error") {
          setTranscriptStatus(data.message || "Transcription failed.");
          setUploadProgress(null);
          finish(true);
        }
      } catch { /* ignore */ }
    });

    // Connection lost — page may be refreshing. Preserve localStorage so the
    // next page load can reconnect via getSavedUploadJob().
    es.addEventListener("error", () => {
      setTranscriptStatus("Transcribing audio\u2026");
      setUploadProgress(null);
      finish(false);
    });
  });
}

async function uploadAudioFile(file) {
  if (!file) {
    setTranscriptStatus("Select an audio file first.");
    return;
  }

  setTranscriptStatus("Uploading audio…");
  setUploadProgress(10);
  appendUploadLog("Uploading audio file…");
  sidebarUploadBtn.disabled = true;
  sidebarPlayBtn.disabled = true;

  const formData = new FormData();
  formData.append("audio", file);
  formData.append("session_name", getCurrentSessionName());

  try {
    // Use XHR so we get upload progress events
    const respData = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/audio/upload");

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          // Upload phase = 10–50% of the bar
          setUploadProgress(10 + (e.loaded / e.total) * 40);
        }
      });

      xhr.addEventListener("load", () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 400) reject(new Error(data.error || "Upload failed."));
          else resolve(data);
        } catch {
          reject(new Error("Invalid server response."));
        }
      });

      xhr.addEventListener("error", () => reject(new Error("Network error during upload.")));
      xhr.send(formData);
    });

    const jobId = respData.job_id;
    saveUploadJob(jobId);
    await followUploadJob(jobId, 50);
  } catch (error) {
    console.error(error);
    setTranscriptStatus(error.message || "Failed to upload audio.");
    setUploadProgress(null);
    clearUploadJob();
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

    // Fetch intents for the selected session and sync intent tabs
    if (data.sessionName) {
      try {
        const intentRes = await fetch(`/api/audio/session/${encodeURIComponent(data.sessionName)}/intents`);
        const intentPayload = await intentRes.json();
        if (intentPayload && Array.isArray(intentPayload.intents)) {
          import('./tabs.js').then(({ syncIntentTabs }) => {
            syncIntentTabs(intentPayload.intents);
          });
        }
      } catch (intentErr) {
        console.error('Failed to load intent tabs', intentErr);
      }
    }

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
            wearerName: reflection.wearer_agent || '',
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
    const currentUser = document.body?.dataset?.currentUser || '';
    const url = currentUser
      ? `/api/audio/sessions?username=${encodeURIComponent(currentUser)}`
      : '/api/audio/sessions';
    const response = await fetch(url);
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
  if (document.body.dataset.autoloadSession) {
    window.location.href = "/wizard";
  } else {
    showSessionListView();
  }
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

generateReflectionBtn?.addEventListener("click", async () => {
  const { getActiveBoard } = await import('./board.js');
  const { syncReflectionTabs: syncTabs } = await import('./tabs.js');
  const board = getActiveBoard();
  const intentFile = board?.metadata?.intentFile;
  if (!intentFile) {
    setTranscriptStatus('No intent board active.');
    return;
  }
  generateReflectionBtn.disabled = true;
  setTranscriptStatus('Generating reflections...');
  try {
    const response = await fetch(`/api/audio/intent/${encodeURIComponent(intentFile)}/generate_reflections`, {
      method: 'POST',
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to generate reflections.');
    }
    setTranscriptStatus(`Generated ${data.generated} reflection(s).`);
    // Reload reflection tabs for the current session
    if (audioData?.id) {
      await loadReflectionTabsForAudio(audioData.id, audioData.sessionName);
    }
  } catch (err) {
    console.error(err);
    setTranscriptStatus(err.message || 'Failed to generate reflections.');
  } finally {
    generateReflectionBtn.disabled = false;
  }
});

window.addEventListener("board:changed", () => {
  syncGenerateReflectionBtn();
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
  // Return the stable sessionName key, not the display label
  return audioData?.sessionName || getCurrentSessionName();
}

export function getAudioUserId() {
  return audioData?.userId || '';
}

if (saveSessionNameBtn) {
  saveSessionNameBtn.addEventListener("click", async () => {
    if (!audioData?.id) {
      setTranscriptStatus("No session loaded.");
      return;
    }
    const newName = sessionNameInput?.value.trim();
    if (!newName) {
      setTranscriptStatus("Session name cannot be empty.");
      return;
    }
    saveSessionNameBtn.disabled = true;
    try {
      const newUsername = sessionUserInput?.value.trim();
      let userId = audioData.userId || '';

      if (newUsername) {
        // Resolve or create user by username
        const userRes = await fetch(`/api/users/${encodeURIComponent(newUsername)}`);
        if (userRes.ok) {
          const userData = await userRes.json();
          userId = userData.id || '';
        } else {
          const createRes = await fetch('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: newUsername, name: newUsername }),
          });
          if (createRes.ok) {
            const created = await createRes.json();
            userId = created.id || '';
          }
        }
      }

      const patchBody = { displayName: newName };
      if (userId) patchBody.userId = userId;
      const res = await fetch(`/api/audio/${encodeURIComponent(audioData.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patchBody),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      audioData.displayName = data.displayName;
      if (data.userId) { audioData.userId = data.userId; audioData.username = newUsername; }
      syncSessionNameInput(data.displayName);
      if (newUsername) syncSessionUserInput(newUsername);
      syncSessionNavBtns();
      await loadSessions();
      setTranscriptStatus("Session name saved.");
    } catch (err) {
      setTranscriptStatus("Failed to save session name: " + err.message);
    } finally {
      saveSessionNameBtn.disabled = false;
    }
  });
}

(async () => {
  if (sessionNameInput && !sessionNameInput.value.trim()) {
    syncSessionNameInput("audio");
  }

  await loadSessions();

  // Reconnect to an in-progress transcription job that survived a page refresh.
  // Ask the SERVER for any active job — more reliable than localStorage.
  try {
    const activeRes = await fetch("/api/audio/upload/jobs/active");
    if (activeRes.ok) {
      const activeJob = await activeRes.json();
      if (activeJob.job_id && activeJob.status === "transcribing") {
        setSidebarView("list");
        renderSessionList();
        setTranscriptStatus("Transcribing audio\u2026 (reconnecting)");
        if (uploadPanel) uploadPanel.hidden = false;
        if (uploadProgressBar) uploadProgressBar.style.width = `${activeJob.progress ?? 50}%`;
        if (uploadLog) { uploadLog.textContent = ""; appendUploadLog("Reconnecting to transcription job\u2026"); }
        transcriptStatus?.classList.add("status-transcribing");
        await followUploadJob(activeJob.job_id, activeJob.progress ?? 50);
        return;
      }
    }
  } catch { /* server unreachable — continue normally */ }

  const autoloadSession = document.body.dataset.autoloadSession;
  if (autoloadSession) {
    const match = sessions.find(s => (s.sessionName || s.originalName) === autoloadSession);
    if (match) {
      await loadAudioById(match.id);
      return;
    }
  }

  clearLoadedAudio();
  setSidebarView("list");
  renderTranscript();
  dispatchGraphPlayState();
})();