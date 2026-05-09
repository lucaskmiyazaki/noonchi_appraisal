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
  const rawText = data.text || '';
  textEl.dataset.rawText = rawText;
  renderReflectionText(textEl, rawText);
  body.appendChild(textEl);

  return node;
}

/**
 * Renders plain text with simple markdown-like formatting into el.
 * Lines starting with "- " are grouped into <ul><li> elements.
 * **text** is rendered as bold.
 * All other non-empty lines become <p> elements.
 */
function applyInlineFormatting(el, text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  for (const part of parts) {
    if (part.startsWith('**') && part.endsWith('**')) {
      const strong = document.createElement('strong');
      strong.textContent = part.slice(2, -2);
      el.appendChild(strong);
    } else {
      el.appendChild(document.createTextNode(part));
    }
  }
}

export function renderReflectionText(el, text) {
  el.innerHTML = '';
  const lines = text.split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith('- ')) {
      const ul = document.createElement('ul');
      while (i < lines.length && lines[i].startsWith('- ')) {
        const li = document.createElement('li');
        applyInlineFormatting(li, lines[i].slice(2));
        ul.appendChild(li);
        i++;
      }
      el.appendChild(ul);
    } else if (line.trim() === '') {
      i++;
    } else {
      const p = document.createElement('p');
      applyInlineFormatting(p, line);
      el.appendChild(p);
      i++;
    }
  }
}

export function getReflectionData(node) {
  const textEl = node.querySelector('.reflection-text');
  return {
    text: textEl?.dataset.rawText || textEl?.textContent || '',
  };
}
