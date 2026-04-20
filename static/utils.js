let nodeCounter = 0;

export function nextId(prefix) {
  nodeCounter += 1;
  return `${prefix}-${nodeCounter}`;
}

export function setCounterFloor(n) {
  if (n > nodeCounter) nodeCounter = n;
}

export function createField(label, inputHtml) {
  const wrapper = document.createElement('div');
  wrapper.className = 'field';
  wrapper.innerHTML = `<label>${label}</label>${inputHtml}`;
  return wrapper;
}

export function createSliderRow(letter, { min = 0, max = 1, value = 0.5 } = {}) {
  const row = document.createElement('div');
  row.className = 'slider-row';
  row.innerHTML = `
    <span>${letter}</span>
    <input type="range" min="${min}" max="${max}" step="0.01" value="${value}">
    <output>${Number(value).toFixed(2)}</output>
  `;

  const input = row.querySelector('input');
  const output = row.querySelector('output');
  input.addEventListener('input', () => {
    output.value = Number(input.value).toFixed(2);
  });
  return row;
}

export function getPortPoint(node, side) {
  const rect = node.getBoundingClientRect();
  const canvasRect = document.getElementById('canvas').getBoundingClientRect();
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

export function getOppositeSide(side) {
  if (side === 'top') return 'bottom';
  if (side === 'bottom') return 'top';
  if (side === 'left') return 'right';
  return 'left';
}

export function getNodeUnderPoint(clientX, clientY) {
  const el = document.elementFromPoint(clientX, clientY);
  if (!el) return null;
  return el.closest('.node');
}

export function clearTargetHighlights() {
  document.querySelectorAll('.node').forEach((node) => node.classList.remove('link-target'));
}
