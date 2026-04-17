import { addAgentBtn, addGoalBtn, addBlockerBtn, addFollowupBtn, playBtn } from './state.js';
import { createAgentNode, createGoalNode, createBlockerNode, createFollowupNode } from './nodes.js';
import { updateAllEdges } from './edges.js';
import { serializeGraph } from './serialize.js';
import { getActiveBoard } from './board.js';
import { initTabs, createReflectionTab } from './tabs.js';
import { getSelectedTimeRange } from './sidebar-upload.js';

initTabs();

function isGraphBoardActive() {
  const board = getActiveBoard();
  return !board || board.kind === 'graph';
}

function syncToolbarState() {
  const enabled = isGraphBoardActive();
  addAgentBtn.disabled = !enabled;
  addGoalBtn.disabled = !enabled;
  addBlockerBtn.disabled = !enabled;
  addFollowupBtn.disabled = !enabled;
  playBtn.disabled = !enabled;
}

window.addEventListener('board:changed', syncToolbarState);
syncToolbarState();

addAgentBtn.onclick = () => {
  if (!isGraphBoardActive()) return;
  createAgentNode({
    x: 80 + Math.random() * 120,
    y: 120 + Math.random() * 80,
    role: 'speaker',
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
  if (!isGraphBoardActive()) return;
  const graph = serializeGraph();
  const timeRange = getSelectedTimeRange();
  const payload = timeRange ? { ...graph, ...timeRange } : graph;
  console.log('sending graph', payload);

  try {
    const response = await fetch('/play_graph', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    const result = await response.json();
    console.log('server response', result);

    if (result?.reflection_tree) {
      createReflectionTab(result.reflection_tree);
    }
  } catch (error) {
    console.error('failed to send graph', error);
  }
};

window.addEventListener('resize', updateAllEdges);
