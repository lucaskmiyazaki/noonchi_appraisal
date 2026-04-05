import { nextId, createField } from '../utils.js';
import { createNodeBase } from '../node-base.js';
import { addEdge } from '../edges.js';
import { createAgentNode } from './agent.js';

export function createFollowupNode({ x = 500, y = 320, linkedFromId = null, mode = 'actionable' } = {}) {
  const id = nextId('followup');
  const node = createNodeBase({ id, type: 'followup', title: 'Action / Question', x, y, badge: mode });
  const body = node.querySelector('.node-body');

  body.appendChild(createField('Text', '<input type="text" placeholder="Type action or question">'));

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

  buttonRow.appendChild(agentBtn);
  body.appendChild(buttonRow);

  if (linkedFromId) addEdge(linkedFromId, id);
  return node;
}

export function getFollowupData(node) {
  const textInput = node.querySelector('input[type="text"]');
  const mode = node.querySelector('.small-tag')?.textContent.trim() || 'actionable';

  return {
    text: textInput?.value || '',
    mode,
  };
}
