import { nodes, edges } from './state.js';
import { getAgentData, getGoalData, getBlockerData, getFollowupData } from './nodes.js';

export function serializeGraph() {
  const serializedNodes = [];

  nodes.forEach((node, id) => {
    const type = node.dataset.type;
    let data = {};

    if (type === 'agent') data = getAgentData(node);
    if (type === 'goal') data = getGoalData(node);
    if (type === 'blocker') data = getBlockerData(node);
    if (type === 'followup') data = getFollowupData(node);

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
