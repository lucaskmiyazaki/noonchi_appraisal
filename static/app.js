import { addAgentBtn, addGoalBtn, addBlockerBtn, addFollowupBtn, playBtn } from './state.js';
import { saveIntentBtn } from './state.js';
import { createAgentNode, createGoalNode, createBlockerNode, createFollowupNode } from './nodes.js';
import { updateAllEdges } from './edges.js';
import { serializeGraph } from './serialize.js';
import { getActiveBoard } from './board.js';
import { initTabs, createReflectionTab, syncIntentTabs } from './tabs.js';
import { clearSelectedTranscriptSegments, getSelectedTimeRange, getSessionName } from './sidebar-upload.js';
import { getAudioUserId } from './sidebar-upload.js';

const toolbarActions = document.getElementById('toolbarActions');
const reflectionMeta = document.getElementById('reflectionMeta');
const reflectionWearerName = document.getElementById('reflectionWearerName');
const reflectionSessionName = document.getElementById('reflectionSessionName');
const reflectionStartTime = document.getElementById('reflectionStartTime');
const reflectionEndTime = document.getElementById('reflectionEndTime');

let graphPlayState = {
  hasSession: false,
  hasSelection: false,
};


initTabs();



function isGraphBoardActive() {
  const board = getActiveBoard();
  return !board || board.kind === 'graph' || board.kind === 'intent';
}

function formatReflectionTime(value) {
  const totalMs = Number(value);
  if (!Number.isFinite(totalMs) || totalMs < 0) return '-';

  const totalSeconds = Math.floor(totalMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }

  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function syncToolbarState() {
  const board = getActiveBoard();
  const enabled = isGraphBoardActive();
  addAgentBtn.disabled = !enabled;
  addGoalBtn.disabled = !enabled;
  addBlockerBtn.disabled = !enabled;
  addFollowupBtn.disabled = !enabled;
  playBtn.disabled = !enabled;
  playBtn.hidden = !enabled || !graphPlayState.hasSession || !graphPlayState.hasSelection;

  const isReflectionBoard = board?.kind === 'reflection';
  if (toolbarActions) toolbarActions.hidden = isReflectionBoard;
  if (reflectionMeta) reflectionMeta.hidden = !isReflectionBoard;

  if (isReflectionBoard) {
    const metadata = board?.metadata || {};
    if (reflectionWearerName) reflectionWearerName.textContent = metadata.wearerName || '-';
    if (reflectionSessionName) reflectionSessionName.textContent = metadata.sessionName || '-';
    if (reflectionStartTime) reflectionStartTime.textContent = formatReflectionTime(metadata.startMs);
    if (reflectionEndTime) reflectionEndTime.textContent = formatReflectionTime(metadata.endMs);
  }
}

window.addEventListener('board:changed', syncToolbarState);
window.addEventListener('graph-play-state', (event) => {
  graphPlayState = {
    hasSession: Boolean(event.detail?.hasSession),
    hasSelection: Boolean(event.detail?.hasSelection),
  };
  syncToolbarState();
});
syncToolbarState();

addAgentBtn.onclick = () => {
  if (!isGraphBoardActive()) return;
  createAgentNode({
    x: 80 + Math.random() * 120,
    y: 120 + Math.random() * 80,
    role: 'wearer',
  });
};

addGoalBtn.onclick = () => {
  if (!isGraphBoardActive()) return;
  createGoalNode({
    x: 220 + Math.random() * 120,
    y: 180 + Math.random() * 80,
  });
};

addBlockerBtn.onclick = () => {
  if (!isGraphBoardActive()) return;
  createBlockerNode({
    x: 360 + Math.random() * 120,
    y: 240 + Math.random() * 80,
  });
};

addFollowupBtn.onclick = () => {
  if (!isGraphBoardActive()) return;
  createFollowupNode({
    x: 500 + Math.random() * 120,
    y: 320 + Math.random() * 80,
    mode: 'actionable',
  });
};

playBtn.onclick = async () => {
  if (!isGraphBoardActive() || playBtn.hidden) return;
  const graph = serializeGraph();
  const timeRange = getSelectedTimeRange();
  const sessionName = getSessionName();
  const payload = { ...graph, sessionName, ...(timeRange || {}) };

  try {
    const response = await fetch('/play_graph', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    const result = await response.json();

    if (result?.reflection_tree) {
      createReflectionTab(result.reflection_tree, {
        ...(timeRange || {}),
        wearerName: result.username || '',
        reflectionFile: result.reflection_tree_file || '',
      });
      clearSelectedTranscriptSegments();
    }
  } catch (error) {
    console.error('failed to send graph', error);
  }
};

// --- Save Intent Button Logic ---
saveIntentBtn.onclick = async () => {
  const board = getActiveBoard();
  if (!board || (board.kind !== 'graph' && board.kind !== 'intent')) return;
  const intentData = serializeGraph();
  const sessionName = getSessionName();
  const userId = getAudioUserId() || board.metadata?.userId || '';
  const existingFile = board.metadata?.intentFile || '';

  try {
    let response;
    if (existingFile) {
      // Overwrite only the matching diagram in the existing intent file
      response = await fetch(`/api/audio/intent/${encodeURIComponent(existingFile)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          diagram_data: intentData,
          startms: board.metadata?.diagramStartMs ?? null,
        }),
      });
    } else {
      // Create new intent file
      const intentFile = `intent_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
      response = await fetch('/api/audio/session/save_intent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_name: sessionName,
          user_id: userId,
          intent_file: intentFile,
          intent_data: intentData,
        }),
      });
    }
    const result = await response.json();
    if (response.ok) {
      // Re-fetch the updated intent JSON and refresh board metadata
      const savedFile = result.intent_file || existingFile;
      if (savedFile) {
        try {
          const refreshRes = await fetch(`/api/audio/intent/${encodeURIComponent(savedFile)}`);
          const refreshData = await refreshRes.json();
          if (refreshRes.ok && refreshData.data) {
            board.metadata.intentData = refreshData.data;
            board.metadata.intentFile = savedFile;
            if (Array.isArray(refreshData.data.diagrams)) {
              window.lastIntentDiagrams = refreshData.data.diagrams;
            }
          }
        } catch (refreshErr) {
          console.error('Failed to refresh intent data:', refreshErr);
        }
      }
      window.alert('Intent saved successfully!');
    } else {
      window.alert(result.error || 'Failed to save intent.');
    }
  } catch (error) {
    window.alert('Failed to save intent.');
    console.error(error);
  }
};

window.addEventListener('resize', updateAllEdges);
