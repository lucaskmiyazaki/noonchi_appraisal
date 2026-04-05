import { nextId, createField } from '../utils.js';
import { createNodeBase } from '../node-base.js';
import { addEdge } from '../edges.js';
import { createAgentNode } from './agent.js';
import { createFollowupNode } from './followup.js';

export function createBlockerNode({ x = 360, y = 240, linkedFromId = null, _id = null } = {}) {
  const id = _id || nextId('blocker');
  const node = createNodeBase({ id, type: 'blocker', title: 'Blocker', x, y, badge: 'blocker' });
  const body = node.querySelector('.node-body');

  body.appendChild(createField('Blocker', '<input type="text" placeholder="Type blocker">'));

  const buttonRow = document.createElement('div');
  buttonRow.className = 'button-row';

  const agentBtn = document.createElement('button');
  agentBtn.className = 'primary';
  agentBtn.textContent = 'Add responsible agent';
  agentBtn.onclick = () => {
    const left = parseFloat(node.style.left) || x;
    const top = parseFloat(node.style.top) || y;
    createAgentNode({ x: left + 320, y: top + 20, role: 'listener', linkedFromId: id });
  };

  const followupBtn = document.createElement('button');
  followupBtn.className = 'followup-button';
  followupBtn.textContent = 'Add action/question';
  followupBtn.onclick = () => {
    const left = parseFloat(node.style.left) || x;
    const top = parseFloat(node.style.top) || y;
    createFollowupNode({ x: left + 320, y: top + 100, linkedFromId: id });
  };

  buttonRow.appendChild(agentBtn);
  buttonRow.appendChild(followupBtn);
  body.appendChild(buttonRow);

  if (linkedFromId) addEdge(linkedFromId, id);
  return node;
}

export function getBlockerData(node) {
  const textInput = node.querySelector('input[type="text"]');

  return {
    text: textInput?.value || '',
  };
}
