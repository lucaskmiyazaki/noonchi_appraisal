import { nextId, createField, createSliderRow } from '../utils.js';
import { createNodeBase } from '../node-base.js';
import { addEdge } from '../edges.js';
import { createGoalNode } from './goal.js';

export function createAgentNode({ x = 80, y = 100, role = 'speaker', linkedFromId = null } = {}) {
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

export function getAgentData(node) {
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
