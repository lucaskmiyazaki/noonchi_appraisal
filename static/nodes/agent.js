import { nextId, createField, createSliderRow } from '../utils.js';
import { createNodeBase } from '../node-base.js';
import { addEdge } from '../edges.js';
import { createGoalNode } from './goal.js';

const EMOTIONS = {
  excited:      { valence:  1, arousal: 1, dominance: 1 },
  surprised:    { valence:  1, arousal: 1, dominance: 0 },
  enjoyment:    { valence:  1, arousal: 0, dominance: 1 },
  relaxed:      { valence:  1, arousal: 0, dominance: 0 },
  angry:        { valence: -1, arousal: 1, dominance: 1 },
  anxious:      { valence: -1, arousal: 1, dominance: 0 },
  disappointed: { valence: -1, arousal: 0, dominance: 1 },
  sad:          { valence: -1, arousal: 0, dominance: 0 },
};

function nameFromPad(v, a, d) {
  if (v > 0) {
    if (a > 0.5) return d > 0.5 ? 'excited' : 'surprised';
    return d > 0.5 ? 'enjoyment' : 'relaxed';
  } else {
    if (a > 0.5) return d > 0.5 ? 'angry' : 'anxious';
    return d > 0.5 ? 'disappointed' : 'sad';
  }
}

export function createAgentNode({ x = 80, y = 100, role = 'speaker', linkedFromId = null, _id = null } = {}) {
  const id = _id || nextId('agent');
  const node = createNodeBase({ id, type: 'agent', title: 'Agent', x, y, badge: role });
  const body = node.querySelector('.node-body');

  body.appendChild(createField('Participant name', '<input type="text" placeholder="Type participant name">'));

  // --- Feeling picker ---
  const feelingField = document.createElement('div');
  feelingField.className = 'field';
  feelingField.innerHTML = '<label>Feeling</label>';

  const chipGrid = document.createElement('div');
  chipGrid.className = 'emotion-chips';

  const chips = {};
  for (const [name, pad] of Object.entries(EMOTIONS)) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = `emotion-chip ${pad.valence > 0 ? 'positive' : 'negative'}`;
    chip.textContent = name;
    chip.dataset.emotion = name;
    chip.addEventListener('click', () => {
      pSlider.value = pad.valence;
      aSlider.value = pad.arousal;
      dSlider.value = pad.dominance;
      pOutput.value = pad.valence.toFixed(2);
      aOutput.value = pad.arousal.toFixed(2);
      dOutput.value = pad.dominance.toFixed(2);
      updateActiveChip(name);
    });
    chips[name] = chip;
    chipGrid.appendChild(chip);
  }

  feelingField.appendChild(chipGrid);
  body.appendChild(feelingField);

  // --- PAD sliders ---
  const padField = document.createElement('div');
  padField.className = 'field';
  padField.innerHTML = '<label>PAD</label>';

  const pRow = createSliderRow('P', { min: -1, max: 1, value: 0 });
  const aRow = createSliderRow('A', { min: 0,  max: 1, value: 0.5 });
  const dRow = createSliderRow('D', { min: 0,  max: 1, value: 0.5 });
  padField.appendChild(pRow);
  padField.appendChild(aRow);
  padField.appendChild(dRow);
  body.appendChild(padField);

  const pSlider = pRow.querySelector('input');
  const aSlider = aRow.querySelector('input');
  const dSlider = dRow.querySelector('input');
  const pOutput = pRow.querySelector('output');
  const aOutput = aRow.querySelector('output');
  const dOutput = dRow.querySelector('output');

  function updateActiveChip(activeName) {
    for (const [name, chip] of Object.entries(chips)) {
      chip.classList.toggle('active', name === activeName);
    }
  }

  function syncChipFromSliders() {
    const name = nameFromPad(
      parseFloat(pSlider.value),
      parseFloat(aSlider.value),
      parseFloat(dSlider.value),
    );
    updateActiveChip(name);
  }

  pSlider.addEventListener('input', syncChipFromSliders);
  aSlider.addEventListener('input', syncChipFromSliders);
  dSlider.addEventListener('input', syncChipFromSliders);

  // --- Add goal button ---
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
