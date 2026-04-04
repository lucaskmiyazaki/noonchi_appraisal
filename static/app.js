const canvas = document.getElementById('canvas');
const svg = document.getElementById('links');
const addAgentBtn = document.getElementById('addAgentBtn');
const addGoalBtn = document.getElementById('addGoalBtn');
const addBlockerBtn = document.getElementById('addBlockerBtn');
const playBtn = document.getElementById('playBtn');

let nodeCounter = 0;
const nodes = new Map();
const edges = [];
let connectionDraft = null;

function nextId(prefix) {
  nodeCounter += 1;
  return `${prefix}-${nodeCounter}`;
}

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

function getPortPoint(node, side) {
  const rect = node.getBoundingClientRect();
  const canvasRect = canvas.getBoundingClientRect();
  const base = {
    left: rect.left - canvasRect.left,
    top: rect.top - canvasRect.top,
    right: rect.right - canvasRect.left,
    bottom: rect.bottom - canvasRect.top,
    cx: rect.left - canvasRect.left + rect.width / 2,
    cy: rect.top - canvasRect.top + rect.height / 2,
  };

  if (side === 'top') return { x: base.cx, y: base.top };
  if (side === 'right') return { x: base.right, y: base.cy };
  if (side === 'bottom') return { x: base.cx, y: base.bottom };
  return { x: base.left, y: base.cy };
}

function createNodeBase({ id, type, title, x, y, badge }) {
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

  const roleTag = node.querySelector('.small-tag');
  if (type === 'agent') {
    const roles = ['speaker', 'listener', 'passive'];

    const advanceRole = (e) => {
      e.stopPropagation();
      const current = roleTag.textContent.trim();
      const currentIndex = roles.indexOf(current);
      const nextIndex = currentIndex === -1 ? 0 : (currentIndex + 1) % roles.length;
      roleTag.textContent = roles[nextIndex];
    };

    roleTag.addEventListener('click', advanceRole);
    roleTag.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        advanceRole(e);
      }
    });
    roleTag.style.cursor = 'pointer';
  }

  node.querySelectorAll('.port').forEach((port) => {
    port.addEventListener('mousedown', (e) => startConnection(e, id, port.dataset.side));
  });

  canvas.appendChild(node);
  makeDraggable(node);
  nodes.set(id, node);
  return node;
}

function deleteNode(id) {
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

function deleteEdge(edgeToDelete) {
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

function createField(label, inputHtml) {
  const wrapper = document.createElement('div');
  wrapper.className = 'field';
  wrapper.innerHTML = `<label>${label}</label>${inputHtml}`;
  return wrapper;
}

function createSliderRow(letter, value = 0) {
  const row = document.createElement('div');
  row.className = 'slider-row';
  row.innerHTML = `
    <span>${letter}</span>
    <input type="range" min="-1" max="1" step="0.01" value="${value}">
    <output>${Number(value).toFixed(2)}</output>
  `;

  const input = row.querySelector('input');
  const output = row.querySelector('output');
  input.addEventListener('input', () => {
    output.value = Number(input.value).toFixed(2);
  });
  return row;
}

function edgeExists(fromId, toId) {
  return edges.some((edge) => edge.fromId === fromId && edge.toId === toId);
}

function addEdge(fromId, toId, fromSide = 'right', toSide = 'left') {
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

function updateEdge(edge) {
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

function updateAllEdges() {
  edges.forEach(updateEdge);
  if (connectionDraft) updateDraftLine(connectionDraft.mouseX, connectionDraft.mouseY);
}

function makeDraggable(node) {
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

function startConnection(event, fromId, fromSide) {
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

function updateDraftLine(clientX, clientY) {
  if (!connectionDraft) return;
  connectionDraft.mouseX = clientX;
  connectionDraft.mouseY = clientY;

  const fromNode = nodes.get(connectionDraft.fromId);
  if (!fromNode) return;

  const start = getPortPoint(fromNode, connectionDraft.fromSide);
  const canvasRect = canvas.getBoundingClientRect();
  const endX = clientX - canvasRect.left;
  const endY = clientY - canvasRect.top;

  connectionDraft.line.setAttribute('x1', start.x);
  connectionDraft.line.setAttribute('y1', start.y);
  connectionDraft.line.setAttribute('x2', endX);
  connectionDraft.line.setAttribute('y2', endY);
}

function clearTargetHighlights() {
  nodes.forEach((node) => node.classList.remove('link-target'));
}

function getNodeUnderPoint(clientX, clientY) {
  const el = document.elementFromPoint(clientX, clientY);
  if (!el) return null;
  return el.closest('.node');
}

function getOppositeSide(side) {
  if (side === 'top') return 'bottom';
  if (side === 'bottom') return 'top';
  if (side === 'left') return 'right';
  return 'left';
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

function createAgentNode({ x = 80, y = 100, role = 'speaker', linkedFromId = null } = {}) {
  const id = nextId('agent');
  const node = createNodeBase({ id, type: 'agent', title: 'Agent', x, y, badge: role });
  const body = node.querySelector('.node-body');

  body.appendChild(createField('Participant name', '<input type="text" placeholder="Type participant name">'));

  const pad = document.createElement('div');
  pad.className = 'field';
  pad.innerHTML = '<label>PAD</label>';
  pad.appendChild(createSliderRow('P'));
  pad.appendChild(createSliderRow('A'));
  pad.appendChild(createSliderRow('D'));
  body.appendChild(pad);

  const buttonRow = document.createElement('div');
  buttonRow.className = 'button-row';

  const btn = document.createElement('button');
  btn.className = 'primary';
  btn.textContent = 'Add goal';
  btn.onclick = () => {
    const left = parseFloat(node.style.left) || x;
    const top = parseFloat(node.style.top) || y;
    createGoalNode({ x: left + 320, y: top + 20, linkedFromId: id });
  };

  buttonRow.appendChild(btn);
  body.appendChild(buttonRow);

  if (linkedFromId) addEdge(linkedFromId, id);
  return node;
}

function createGoalNode({ x = 220, y = 180, linkedFromId = null } = {}) {
  const id = nextId('goal');
  const node = createNodeBase({ id, type: 'goal', title: 'Goal', x, y, badge: 'goal' });
  const body = node.querySelector('.node-body');

  body.appendChild(createField('Goal', '<input type="text" placeholder="Type goal">'));
  body.appendChild(createField('Status', '<select><option value="on_going">on going</option><option value="fail">fail</option><option value="success">success</option></select>'));

  const buttonRow = document.createElement('div');
  buttonRow.className = 'button-row';

  const btn = document.createElement('button');
  btn.className = 'primary';
  btn.textContent = 'Add blocker';
  btn.onclick = () => {
    const left = parseFloat(node.style.left) || x;
    const top = parseFloat(node.style.top) || y;
    createBlockerNode({ x: left + 320, y: top + 20, linkedFromId: id });
  };

  buttonRow.appendChild(btn);
  body.appendChild(buttonRow);

  if (linkedFromId) addEdge(linkedFromId, id);
  return node;
}

function createBlockerNode({ x = 360, y = 240, linkedFromId = null } = {}) {
  const id = nextId('blocker');
  const node = createNodeBase({ id, type: 'blocker', title: 'Blocker', x, y, badge: 'blocker' });
  const body = node.querySelector('.node-body');

  body.appendChild(createField('Blocker', '<input type="text" placeholder="Type blocker">'));

  const buttonRow = document.createElement('div');
  buttonRow.className = 'button-row';

  const btn = document.createElement('button');
  btn.className = 'primary';
  btn.textContent = 'Add responsible agent';
  btn.onclick = () => {
    const left = parseFloat(node.style.left) || x;
    const top = parseFloat(node.style.top) || y;
    createAgentNode({ x: left + 320, y: top + 20, role: 'listener', linkedFromId: id });
  };

  buttonRow.appendChild(btn);
  body.appendChild(buttonRow);

  if (linkedFromId) addEdge(linkedFromId, id);
  return node;
}

function getAgentData(node) {
  const nameInput = node.querySelector('input[type="text"]');
  const sliders = node.querySelectorAll('.slider-row input');
  const role = node.querySelector('.small-tag')?.textContent.trim() || 'listener';

  return {
    name: nameInput?.value || '',
    role,
    valence: Number(sliders[0]?.value || 0),
    arousal: Number(sliders[1]?.value || 0),
    dominance: Number(sliders[2]?.value || 0),
  };
}

function getGoalData(node) {
  const textInput = node.querySelector('input[type="text"]');
  const statusSelect = node.querySelector('select');

  return {
    text: textInput?.value || '',
    status: statusSelect?.value || 'on_going',
  };
}

function getBlockerData(node) {
  const textInput = node.querySelector('input[type="text"]');

  return {
    text: textInput?.value || '',
  };
}

function serializeGraph() {
  const serializedNodes = [];

  nodes.forEach((node, id) => {
    const type = node.dataset.type;
    let data = {};

    if (type === 'agent') data = getAgentData(node);
    if (type === 'goal') data = getGoalData(node);
    if (type === 'blocker') data = getBlockerData(node);

    serializedNodes.push({ id, type, data });
  });

  const serializedEdges = edges.map((edge) => ({
    fromId: edge.fromId,
    toId: edge.toId,
    fromSide: edge.fromSide,
    toSide: edge.toSide,
  }));

  return {
    nodes: serializedNodes,
    edges: serializedEdges,
  };
}

addAgentBtn.onclick = () => {
  createAgentNode({
    x: 80 + Math.random() * 120,
    y: 120 + Math.random() * 80,
    role: 'speaker',
  });
};

addGoalBtn.onclick = () => {
  createGoalNode({
    x: 220 + Math.random() * 120,
    y: 180 + Math.random() * 80,
  });
};

addBlockerBtn.onclick = () => {
  createBlockerNode({
    x: 360 + Math.random() * 120,
    y: 240 + Math.random() * 80,
  });
};

playBtn.onclick = async () => {
  const graph = serializeGraph();
  console.log('sending graph', graph);

  try {
    const response = await fetch('/play_graph', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(graph),
    });

    const result = await response.json();
    console.log('server response', result);
  } catch (error) {
    console.error('failed to send graph', error);
  }
};

window.addEventListener('resize', updateAllEdges);

createAgentNode({ x: 80, y: 120, role: 'speaker' });
