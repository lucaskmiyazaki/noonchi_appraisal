import { nodes } from './state.js';
import { deleteNode } from './node-base.js';
import { addEdge } from './edges.js';
import { serializeGraph } from './serialize.js';
import { setCounterFloor } from './utils.js';
import { createAgentNode } from './nodes/agent.js';
import { createGoalNode } from './nodes/goal.js';
import { createBlockerNode } from './nodes/blocker.js';
import { createFollowupNode } from './nodes/followup.js';
import { createReflectionNode } from './nodes/reflection.js';

function normalizeAgentRole(role, fallback = 'participants') {
  const normalized = String(role || '').trim().toLowerCase();
  if (!normalized) return fallback;
  if (normalized === 'listener') return 'participants';
  if (normalized === 'passive') return 'external';
  if (['wearer', 'participants', 'external'].includes(normalized)) return normalized;
  return fallback;
}

export const boards = [];
export let activeBoardId = null;
let boardCounter = 0;
let reflectionCounter = 0;

const factories = {
  agent: createAgentNode,
  goal: createGoalNode,
  blocker: createBlockerNode,
  followup: createFollowupNode,
  reflection: createReflectionNode,
};

function getBoardById(id) {
  return boards.find((b) => b.id === id);
}

function buildReflectionGraph(tree) {
  const treeNodes = tree?.nodes || {};
  const startNodeId = tree?.start_node;
  const ids = Object.keys(treeNodes);
  if (!ids.length) return { nodes: [], edges: [] };

  const levels = new Map();
  const visited = new Set();
  const queue = [];

  const rootId = startNodeId && treeNodes[startNodeId] ? startNodeId : ids[0];
  queue.push({ id: rootId, depth: 0 });
  visited.add(rootId);

  while (queue.length) {
    const { id, depth } = queue.shift();
    if (!levels.has(depth)) levels.set(depth, []);
    levels.get(depth).push(id);

    const options = treeNodes[id]?.options || [];
    options.forEach((option) => {
      const nextId = option?.next;
      if (!nextId || !treeNodes[nextId] || visited.has(nextId)) return;
      visited.add(nextId);
      queue.push({ id: nextId, depth: depth + 1 });
    });
  }

  let maxDepth = levels.size ? Math.max(...levels.keys()) : 0;
  ids.forEach((id) => {
    if (visited.has(id)) return;
    maxDepth += 1;
    levels.set(maxDepth, [id]);
  });

  const reflectionNodes = [];
  const sortedDepths = Array.from(levels.keys()).sort((a, b) => a - b);
  sortedDepths.forEach((depth) => {
    const levelIds = levels.get(depth);
    levelIds.forEach((id, index) => {
      const source = treeNodes[id] || {};
      const reflectionTitle = source.type === 'question'
        ? 'Reflection Question'
        : source.type === 'audio'
          ? 'Reflection audio'
          : source.type === 'practice'
            ? 'Reflection practice'
            : source.type === 'journaling'
              ? 'Reflection journaling'
              : 'Reflection Note';
      reflectionNodes.push({
        id,
        type: 'reflection',
        title: reflectionTitle,
        badge: source.type || 'reflection',
        x: 120 + index * 340,
        y: 120 + depth * 220,
        data: {
          text: source.text || '',
          options: source.options || [],
        },
      });
    });
  });

  const reflectionEdges = [];
  ids.forEach((id) => {
    const options = treeNodes[id]?.options || [];
    options.forEach((option) => {
      const nextId = option?.next;
      if (!nextId || !treeNodes[nextId]) return;
      reflectionEdges.push({
        fromId: id,
        toId: nextId,
        fromSide: 'bottom',
        toSide: 'top',
        label: option.label || '',
      });
    });
  });

  return {
    nodes: reflectionNodes,
    edges: reflectionEdges,
  };
}

function applyData(node, type, data, badge) {
  const tag = node.querySelector('.small-tag');
  if (tag && badge) tag.textContent = badge;

  if (type === 'agent') {
    const nameInput = node.querySelector('input[type="text"]');
    if (nameInput) nameInput.value = data.name || '';
    const sliders = node.querySelectorAll('.slider-row input');
    const outputs = node.querySelectorAll('.slider-row output');
    [data.valence ?? 0.5, data.arousal ?? 0.5, data.dominance ?? 0.5].forEach((val, i) => {
      if (sliders[i]) sliders[i].value = val;
      if (outputs[i]) outputs[i].value = Number(val).toFixed(2);
    });
    sliders.forEach((slider) => {
      slider.dispatchEvent(new Event('input'));
    });
  }

  if (type === 'goal') {
    const input = node.querySelector('input[type="text"]');
    if (input) input.value = data.text || '';
    const select = node.querySelector('select');
    if (select) select.value = data.status || 'on_going';
  }

  if (type === 'blocker') {
    const input = node.querySelector('input[type="text"]');
    if (input) input.value = data.text || '';
  }

  if (type === 'followup') {
    const input = node.querySelector('input[type="text"]');
    if (input) input.value = data.text || '';
  }

  if (type === 'reflection') {
    const textEl = node.querySelector('.reflection-text');
    if (textEl) textEl.textContent = data.text || '';
  }
}

export function clearBoard() {
  Array.from(nodes.keys()).forEach((id) => deleteNode(id));
}

export function createBoard(name = null) {
  boardCounter += 1;
  const id = `board-${boardCounter}`;
  const board = {
    id,
    name: name || `Board ${boardCounter}`,
    kind: 'graph',
    graph: { nodes: [], edges: [] },
  };
  boards.push(board);
  return board;
}

export function createReflectionBoard(tree, metadata = {}) {
  boardCounter += 1;
  reflectionCounter += 1;
  const id = `board-${boardCounter}`;
  const board = {
    id,
    name: `Reflection ${reflectionCounter}`,
    kind: 'reflection',
    graph: buildReflectionGraph(tree),
    metadata: {
      wearerName: metadata.wearerName || '',
      sessionName: metadata.sessionName || '',
      startMs: Number.isFinite(Number(metadata.startMs)) ? Number(metadata.startMs) : null,
      endMs: Number.isFinite(Number(metadata.endMs)) ? Number(metadata.endMs) : null,
      reflectionFile: metadata.reflectionFile || '',
    },
  };
  boards.push(board);
  return board;
}

export function removeBoard(boardId) {
  const boardIndex = boards.findIndex((board) => board.id === boardId);
  if (boardIndex === -1) return false;

  const wasActive = activeBoardId === boardId;
  boards.splice(boardIndex, 1);

  if (!boards.length) {
    const board = createBoard();
    activeBoardId = null;
    setActiveBoard(board.id);
    return true;
  }

  if (wasActive) {
    const fallbackGraphBoard = boards.find((board) => board.kind === 'graph');
    const fallbackBoard = fallbackGraphBoard || boards[Math.min(boardIndex, boards.length - 1)];
    activeBoardId = null;
    setActiveBoard(fallbackBoard.id);
  }

  return true;
}

export function saveCurrentBoard() {
  if (!activeBoardId) return;
  const board = getBoardById(activeBoardId);
  if (board) board.graph = serializeGraph();
}

export function loadGraph(graph) {
  clearBoard();

  graph.nodes.forEach((saved) => {
    const factory = factories[saved.type];
    if (!factory) return;

    // Only bump counter for numeric ID formats (prefix-N); reflection IDs are strings
    const num = parseInt(String(saved.id).split('-').pop(), 10);
    if (!isNaN(num)) setCounterFloor(num);

    const args = { x: saved.x || 0, y: saved.y || 0, _id: saved.id };
    if (saved.type === 'agent') args.role = normalizeAgentRole(saved.badge, 'wearer');
    if (saved.type === 'followup') args.mode = saved.badge || 'actionable';
    if (saved.type === 'reflection') {
      args.title = saved.title;
      args.badge = saved.badge;
      args.data = saved.data || {};
    }
    factory(args);

    const node = nodes.get(saved.id);
    if (node) applyData(node, saved.type, saved.data || {}, saved.badge);
  });

  graph.edges.forEach((edge) => {
    addEdge(edge.fromId, edge.toId, edge.fromSide, edge.toSide, edge.label || '');
  });
}

export function setActiveBoard(boardId) {
  if (activeBoardId === boardId) return;
  saveCurrentBoard();
  activeBoardId = boardId;
  const board = getBoardById(boardId);
  if (board) {
    loadGraph(board.graph);
    window.dispatchEvent(new CustomEvent('board:changed', { detail: { board } }));
  }
}

export function getActiveBoard() {
  return getBoardById(activeBoardId);
}
