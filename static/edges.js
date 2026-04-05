import { canvas, svg, nodes, edges } from './state.js';
import { getPortPoint } from './utils.js';

function createEdgeDeleteButton() {
  const button = document.createElement('div');
  button.textContent = '✕';
  button.style.position = 'absolute';
  button.style.width = '22px';
  button.style.height = '22px';
  button.style.borderRadius = '999px';
  button.style.background = '#111827';
  button.style.color = 'white';
  button.style.display = 'flex';
  button.style.alignItems = 'center';
  button.style.justifyContent = 'center';
  button.style.fontSize = '12px';
  button.style.fontWeight = '700';
  button.style.boxShadow = '0 4px 12px rgba(0,0,0,0.18)';
  button.style.cursor = 'pointer';
  button.style.opacity = '0';
  button.style.transform = 'scale(0.8)';
  button.style.transition = 'opacity 0.15s ease, transform 0.15s ease';
  button.style.pointerEvents = 'none';
  button.style.zIndex = '12';
  return button;
}

function ensureArrowMarker() {
  if (document.getElementById('arrowhead')) return;

  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  const arrowPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');

  marker.setAttribute('id', 'arrowhead');
  marker.setAttribute('markerWidth', '10');
  marker.setAttribute('markerHeight', '7');
  marker.setAttribute('refX', '10');
  marker.setAttribute('refY', '3.5');
  marker.setAttribute('orient', 'auto');

  arrowPath.setAttribute('d', 'M0,0 L10,3.5 L0,7 Z');
  arrowPath.setAttribute('fill', '#6b7280');

  marker.appendChild(arrowPath);
  defs.appendChild(marker);
  svg.appendChild(defs);
}

function showEdgeDeleteButton(edge) {
  if (!edge.deleteButton) return;
  edge.deleteButton.style.opacity = '1';
  edge.deleteButton.style.transform = 'scale(1)';
  edge.deleteButton.style.pointerEvents = 'auto';
}

function hideEdgeDeleteButton(edge) {
  if (!edge.deleteButton) return;
  edge.deleteButton.style.opacity = '0';
  edge.deleteButton.style.transform = 'scale(0.8)';
  edge.deleteButton.style.pointerEvents = 'none';
}

export function edgeExists(fromId, toId) {
  return edges.some((edge) => edge.fromId === fromId && edge.toId === toId);
}

export function addEdge(fromId, toId, fromSide = 'right', toSide = 'left') {
  if (!fromId || !toId || fromId === toId || edgeExists(fromId, toId)) return;

  ensureArrowMarker();

  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  line.setAttribute('stroke', '#6b7280');
  line.setAttribute('stroke-width', '2.5');
  line.setAttribute('stroke-linecap', 'round');
  line.setAttribute('marker-end', 'url(#arrowhead)');
  line.style.pointerEvents = 'stroke';
  svg.appendChild(line);

  const deleteButton = createEdgeDeleteButton();
  canvas.appendChild(deleteButton);

  const edge = {
    fromId,
    toId,
    fromSide,
    toSide,
    line,
    deleteButton,
    isHovered: false,
    deleteHovered: false,
  };

  edges.push(edge);
  updateEdge(edge);
  hideEdgeDeleteButton(edge);

  line.addEventListener('mouseenter', () => {
    edge.isHovered = true;
    showEdgeDeleteButton(edge);
  });

  line.addEventListener('mouseleave', () => {
    edge.isHovered = false;
    if (!edge.deleteHovered) hideEdgeDeleteButton(edge);
  });

  deleteButton.addEventListener('mouseenter', () => {
    edge.deleteHovered = true;
    showEdgeDeleteButton(edge);
  });

  deleteButton.addEventListener('mouseleave', () => {
    edge.deleteHovered = false;
    if (!edge.isHovered) hideEdgeDeleteButton(edge);
  });

  deleteButton.addEventListener('click', (e) => {
    e.stopPropagation();
    deleteEdge(edge);
  });
}

export function deleteEdge(edgeToDelete) {
  const index = edges.indexOf(edgeToDelete);
  if (index !== -1) {
    edges.splice(index, 1);
  }

  if (edgeToDelete.line && edgeToDelete.line.parentNode === svg) {
    svg.removeChild(edgeToDelete.line);
  }

  if (edgeToDelete.deleteButton && edgeToDelete.deleteButton.parentNode === canvas) {
    canvas.removeChild(edgeToDelete.deleteButton);
  }
}

export function updateEdge(edge) {
  const fromNode = nodes.get(edge.fromId);
  const toNode = nodes.get(edge.toId);
  if (!fromNode || !toNode) return;

  const p1 = getPortPoint(fromNode, edge.fromSide || 'right');
  const p2 = getPortPoint(toNode, edge.toSide || 'left');

  edge.line.setAttribute('x1', p1.x);
  edge.line.setAttribute('y1', p1.y);
  edge.line.setAttribute('x2', p2.x);
  edge.line.setAttribute('y2', p2.y);

  const midX = (p1.x + p2.x) / 2;
  const midY = (p1.y + p2.y) / 2;
  edge.deleteButton.style.left = `${midX - 11}px`;
  edge.deleteButton.style.top = `${midY - 11}px`;
}

export function updateAllEdges() {
  edges.forEach(updateEdge);
}
