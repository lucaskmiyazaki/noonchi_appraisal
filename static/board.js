import { nodes } from './state.js';
import { deleteNode } from './node-base.js';
import { addEdge } from './edges.js';
import { serializeGraph } from './serialize.js';
import { setCounterFloor } from './utils.js';
import { createNodeBase } from './node-base.js';
import { createAgentNode } from './nodes/agent.js';
import { createGoalNode } from './nodes/goal.js';
import { createBlockerNode } from './nodes/blocker.js';
import { createFollowupNode } from './nodes/followup.js';

export const boards = [];
export let activeBoardId = null;
let boardCounter = 0;
let reflectionCounter = 0;

const factories = {
  agent: createAgentNode,
  goal: createGoalNode,
  blocker: createBlockerNode,
  followup: createFollowupNode,
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
      reflectionNodes.push({
        id,
        type: 'reflection',
        title: source.type === 'question' ? 'Reflection Question' : 'Reflection Note',
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
      });
    });
  });

  return {
    nodes: reflectionNodes,
    edges: reflectionEdges,
  };
}

function createReflectionNode(saved) {
  const node = createNodeBase({
    id: saved.id,
    type: 'reflection',
    title: saved.title || 'Reflection',
    x: saved.x || 0,
    y: saved.y || 0,
    badge: saved.badge || 'reflection',
  });

  node.querySelectorAll('.port').forEach((port) => port.remove());
  const deleteButton = node.querySelector('.delete-btn');
  if (deleteButton) deleteButton.remove();

  const body = node.querySelector('.node-body');
  body.innerHTML = '';

  const textEl = document.createElement('div');
  textEl.className = 'reflection-text';
  textEl.textContent = saved.data?.text || '';
  body.appendChild(textEl);

  const options = saved.data?.options || [];
  if (options.length) {
    const optionsTitle = document.createElement('div');
    optionsTitle.className = 'reflection-options-title';
    optionsTitle.textContent = 'Options';
    body.appendChild(optionsTitle);

    const optionsList = document.createElement('ul');
    optionsList.className = 'reflection-options';
    options.forEach((option) => {
      const item = document.createElement('li');
      item.textContent = option.label || '(no label)';
      optionsList.appendChild(item);
    });
    body.appendChild(optionsList);
  }
}

function applyData(node, type, data, badge) {
  const tag = node.querySelector('.small-tag');
  if (tag && badge) tag.textContent = badge;

  if (type === 'agent') {
    const nameInput = node.querySelector('input[type="text"]');
    if (nameInput) nameInput.value = data.name || '';
    const sliders = node.querySelectorAll('.slider-row input');
    const outputs = node.querySelectorAll('.slider-row output');
    [data.valence ?? 0, data.arousal ?? 0, data.dominance ?? 0].forEach((val, i) => {
      if (sliders[i]) sliders[i].value = val;
      if (outputs[i]) outputs[i].value = Number(val).toFixed(2);
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

export function createReflectionBoard(tree) {
  boardCounter += 1;
  reflectionCounter += 1;
  const id = `board-${boardCounter}`;
  const board = {
    id,
    name: `Reflection ${reflectionCounter}`,
    kind: 'reflection',
    graph: buildReflectionGraph(tree),
  };
  boards.push(board);
  return board;
}

export function saveCurrentBoard() {
  if (!activeBoardId) return;
  const board = getBoardById(activeBoardId);
  if (board && board.kind === 'graph') board.graph = serializeGraph();
}

export function loadGraph(graph) {
  clearBoard();

  graph.nodes.forEach((saved) => {
    if (saved.type === 'reflection') {
      createReflectionNode(saved);
      return;
    }

    const factory = factories[saved.type];
    if (!factory) return;

    // Ensure the counter won't generate an ID that collides with restored IDs
    const num = parseInt(String(saved.id).split('-').pop(), 10);
    if (!isNaN(num)) setCounterFloor(num);

    const args = { x: saved.x || 0, y: saved.y || 0, _id: saved.id };
    if (saved.type === 'agent') args.role = saved.badge || 'speaker';
    if (saved.type === 'followup') args.mode = saved.badge || 'actionable';
    factory(args);

    const node = nodes.get(saved.id);
    if (node) applyData(node, saved.type, saved.data || {}, saved.badge);
  });

  graph.edges.forEach((edge) => {
    addEdge(edge.fromId, edge.toId, edge.fromSide, edge.toSide);
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
