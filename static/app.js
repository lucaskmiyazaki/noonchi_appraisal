import { addAgentBtn, addGoalBtn, addBlockerBtn, addFollowupBtn, playBtn } from './state.js';
import { createAgentNode, createGoalNode, createBlockerNode, createFollowupNode } from './nodes.js';
import { updateAllEdges } from './edges.js';
import { serializeGraph } from './serialize.js';

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

addFollowupBtn.onclick = () => {
  createFollowupNode({
    x: 500 + Math.random() * 120,
    y: 320 + Math.random() * 80,
    mode: 'actionable',
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
