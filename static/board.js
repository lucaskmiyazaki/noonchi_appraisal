import { nodes } from './state.js';
import { deleteNode } from './node-base.js';
import { addEdge } from './edges.js';
import { serializeGraph } from './serialize.js';
import { setCounterFloor } from './utils.js';
import { createAgentNode } from './nodes/agent.js';
import { createGoalNode } from './nodes/goal.js';
import { createBlockerNode } from './nodes/blocker.js';
import { createFollowupNode } from './nodes/followup.js';

export const boards = [];
export let activeBoardId = null;
let boardCounter = 0;

const factories = {
  agent: createAgentNode,
  goal: createGoalNode,
  blocker: createBlockerNode,
  followup: createFollowupNode,
};

function getBoardById(id) {
  return boards.find((b) => b.id === id);
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
  const board = { id, name: name || `Board ${boardCounter}`, graph: { nodes: [], edges: [] } };
  boards.push(board);
  return board;
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
  if (board) loadGraph(board.graph);
}
