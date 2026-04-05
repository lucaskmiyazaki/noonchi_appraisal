import { canvas, svg, nodes } from './state.js';
import { addEdge } from './edges.js';
import { getNodeUnderPoint, getOppositeSide, clearTargetHighlights } from './utils.js';

let connectionDraft = null;

export function startConnection(event, fromId, fromSide) {
  event.stopPropagation();
  event.preventDefault();
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  line.setAttribute('stroke', '#111827');
  line.setAttribute('stroke-width', '2.5');
  line.setAttribute('stroke-dasharray', '6 4');
  line.setAttribute('stroke-linecap', 'round');
  svg.appendChild(line);

  connectionDraft = { fromId, fromSide, line, mouseX: event.clientX, mouseY: event.clientY };
  updateDraftLine(event.clientX, event.clientY);
}

export function updateDraftLine(clientX, clientY) {
  if (!connectionDraft) return;

  connectionDraft.mouseX = clientX;
  connectionDraft.mouseY = clientY;

  const fromNode = nodes.get(connectionDraft.fromId);
  if (!fromNode) return;

  const start = fromNode ? fromNode : null;
  const canvasRect = canvas.getBoundingClientRect();
  const endX = clientX - canvasRect.left;
  const endY = clientY - canvasRect.top;

  const p1 = fromNode.getBoundingClientRect();
  const base = {
    left: p1.left - canvasRect.left,
    top: p1.top - canvasRect.top,
    right: p1.right - canvasRect.left,
    bottom: p1.bottom - canvasRect.top,
    cx: p1.left - canvasRect.left + p1.width / 2,
    cy: p1.top - canvasRect.top + p1.height / 2,
  };

  let source;
  if (connectionDraft.fromSide === 'top') source = { x: base.cx, y: base.top };
  else if (connectionDraft.fromSide === 'right') source = { x: base.right, y: base.cy };
  else if (connectionDraft.fromSide === 'bottom') source = { x: base.cx, y: base.bottom };
  else source = { x: base.left, y: base.cy };

  connectionDraft.line.setAttribute('x1', source.x);
  connectionDraft.line.setAttribute('y1', source.y);
  connectionDraft.line.setAttribute('x2', endX);
  connectionDraft.line.setAttribute('y2', endY);
}

window.addEventListener('mousemove', (e) => {
  if (!connectionDraft) return;
  updateDraftLine(e.clientX, e.clientY);
  clearTargetHighlights();

  const node = getNodeUnderPoint(e.clientX, e.clientY);
  if (node && node.dataset.id !== connectionDraft.fromId) {
    node.classList.add('link-target');
  }
});

window.addEventListener('mouseup', (e) => {
  if (!connectionDraft) return;

  const draft = connectionDraft;
  const targetNode = getNodeUnderPoint(e.clientX, e.clientY);
  if (targetNode && targetNode.dataset.id !== draft.fromId) {
    addEdge(draft.fromId, targetNode.dataset.id, draft.fromSide, getOppositeSide(draft.fromSide));
  }

  if (draft.line.parentNode === svg) {
    svg.removeChild(draft.line);
  }

  connectionDraft = null;
  clearTargetHighlights();
});
