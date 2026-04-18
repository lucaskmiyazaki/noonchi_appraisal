import { createNodeBase } from '../node-base.js';

let reflCounter = 0;

function nextReflectionId() {
  reflCounter += 1;
  return `reflection-${reflCounter}`;
}

function getReflectionTitle(badge) {
  if (badge === 'audio') return 'Reflection audio';
  if (badge === 'practice') return 'Reflection practice';
  if (badge === 'journaling') return 'Reflection journaling';
  if (badge === 'question') return 'Reflection Question';
  return 'Reflection';
}

export function createReflectionNode({ _id = null, title, badge, x = 0, y = 0, data = {} } = {}) {
  const id = _id || nextReflectionId();
  const resolvedBadge = badge || 'message';
  const resolvedTitle = title || getReflectionTitle(resolvedBadge);

  const node = createNodeBase({
    id,
    type: 'reflection',
    title: resolvedTitle,
    x,
    y,
    badge: resolvedBadge,
  });

  // No manual port connections on reflection nodes
  node.querySelectorAll('.port').forEach((port) => port.remove());

  const body = node.querySelector('.node-body');
  body.innerHTML = '';

  const textEl = document.createElement('div');
  textEl.className = 'reflection-text';
  textEl.textContent = data.text || '';
  body.appendChild(textEl);

  return node;
}

export function getReflectionData(node) {
  const textEl = node.querySelector('.reflection-text');
  return {
    text: textEl?.textContent || '',
  };
}
