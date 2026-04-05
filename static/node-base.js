import { canvas, nodes, edges } from './state.js';
import { createField, createSliderRow, clearTargetHighlights } from './utils.js';
import { startConnection } from './connection.js';
import { addEdge, deleteEdge, updateAllEdges } from './edges.js';

export function createNodeBase({ id, type, title, x, y, badge }) {
  const node = document.createElement('div');
  node.className = `node ${type}`;
  node.dataset.id = id;
  node.dataset.type = type;
  node.style.left = `${x}px`;
  node.style.top = `${y}px`;

  node.innerHTML = `
    <div class="port port-top" data-side="top">+</div>
    <div class="port port-right" data-side="right">+</div>
    <div class="port port-bottom" data-side="bottom">+</div>
    <div class="port port-left" data-side="left">+</div>
    <div class="node-header">
      <span>${title}</span>
      <div style="display:flex; gap:8px; align-items:center;">
        <span class="small-tag" role="button" tabindex="0">${badge}</span>
        <span class="delete-btn">✕</span>
      </div>
    </div>
    <div class="node-body"></div>
  `;

  const deleteBtn = node.querySelector('.delete-btn');
  deleteBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    deleteNode(id);
  });

  const tag = node.querySelector('.small-tag');

  if (type === 'agent') {
    const values = ['speaker', 'listener', 'passive'];
    const advance = (e) => {
      e.stopPropagation();
      const current = tag.textContent.trim();
      const currentIndex = values.indexOf(current);
      const nextIndex = currentIndex === -1 ? 0 : (currentIndex + 1) % values.length;
      tag.textContent = values[nextIndex];
    };

    tag.addEventListener('click', advance);
    tag.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        advance(e);
      }
    });
    tag.style.cursor = 'pointer';
  }

  if (type === 'followup') {
    const values = ['actionable', 'question'];
    const advance = (e) => {
      e.stopPropagation();
      const current = tag.textContent.trim();
      const currentIndex = values.indexOf(current);
      const nextIndex = currentIndex === -1 ? 0 : (currentIndex + 1) % values.length;
      tag.textContent = values[nextIndex];
    };

    tag.addEventListener('click', advance);
    tag.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        advance(e);
      }
    });
    tag.style.cursor = 'pointer';
  }

  node.querySelectorAll('.port').forEach((port) => {
    port.addEventListener('mousedown', (e) => startConnection(e, id, port.dataset.side));
  });

  canvas.appendChild(node);
  makeDraggable(node);
  nodes.set(id, node);
  return node;
}

export function deleteNode(id) {
  const node = nodes.get(id);
  if (!node) return;

  for (let i = edges.length - 1; i >= 0; i -= 1) {
    if (edges[i].fromId === id || edges[i].toId === id) {
      deleteEdge(edges[i]);
    }
  }

  node.remove();
  nodes.delete(id);
  clearTargetHighlights();
}

export function makeDraggable(node) {
  const header = node.querySelector('.node-header');
  let dragging = false;
  let offsetX = 0;
  let offsetY = 0;

  header.addEventListener('mousedown', (e) => {
    if (e.target.classList.contains('delete-btn')) return;
    dragging = true;
    const rect = node.getBoundingClientRect();
    offsetX = e.clientX - rect.left;
    offsetY = e.clientY - rect.top;
    node.style.zIndex = String(Date.now());
  });

  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const canvasRect = canvas.getBoundingClientRect();
    const maxX = canvasRect.width - node.offsetWidth;
    const maxY = canvasRect.height - node.offsetHeight;
    const x = Math.max(0, Math.min(maxX, e.clientX - canvasRect.left - offsetX));
    const y = Math.max(0, Math.min(maxY, e.clientY - canvasRect.top - offsetY));
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
    updateAllEdges();
  });

  window.addEventListener('mouseup', () => {
    dragging = false;
  });
}
