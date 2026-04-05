import { nextId, createField } from '../utils.js';
import { createNodeBase } from '../node-base.js';
import { addEdge } from '../edges.js';
import { createBlockerNode } from './blocker.js';
import { createFollowupNode } from './followup.js';

export function createGoalNode({ x = 220, y = 180, linkedFromId = null } = {}) {
  const id = nextId('goal');
  const node = createNodeBase({ id, type: 'goal', title: 'Goal', x, y, badge: 'goal' });
  const body = node.querySelector('.node-body');

  body.appendChild(createField('Goal', '<input type="text" placeholder="Type goal">'));
  body.appendChild(createField('Status', '<select><option value="on_going">on going</option><option value="fail">fail</option><option value="success">success</option></select>'));

  const buttonRow = document.createElement('div');
  buttonRow.className = 'button-row';

  const blockerBtn = document.createElement('button');
  blockerBtn.className = 'primary';
  blockerBtn.textContent = 'Add blocker';
  blockerBtn.onclick = () => {
    const left = parseFloat(node.style.left) || x;
    const top = parseFloat(node.style.top) || y;
    createBlockerNode({ x: left + 320, y: top + 20, linkedFromId: id });
  };

  const followupBtn = document.createElement('button');
  followupBtn.className = 'followup-button';
  followupBtn.textContent = 'Add action/question';
  followupBtn.onclick = () => {
    const left = parseFloat(node.style.left) || x;
    const top = parseFloat(node.style.top) || y;
    createFollowupNode({ x: left + 320, y: top + 100, linkedFromId: id });
  };

  buttonRow.appendChild(blockerBtn);
  buttonRow.appendChild(followupBtn);
  body.appendChild(buttonRow);

  if (linkedFromId) addEdge(linkedFromId, id);
  return node;
}

export function getGoalData(node) {
  const textInput = node.querySelector('input[type="text"]');
  const statusSelect = node.querySelector('select');

  return {
    text: textInput?.value || '',
    status: statusSelect?.value || 'on_going',
  };
}
