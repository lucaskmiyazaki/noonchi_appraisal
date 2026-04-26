import { tabBar, addTabBtn } from './state.js';
import { boards, activeBoardId, createBoard, createReflectionBoard, createIntentBoard, setActiveBoard, getActiveBoard, removeBoard } from './board.js';

function syncReflectionBoardNames() {
  let reflectionIndex = 0;
  boards.forEach((board) => {
    if (board.kind !== 'reflection') return;
    reflectionIndex += 1;
    board.name = `Reflection ${reflectionIndex}`;
  });
}

async function deleteIntentBoard(board) {
  const intentFile = board?.metadata?.intentFile;
  if (!intentFile) {
    return;
  }
  try {
    const response = await fetch(`/api/audio/intent/${encodeURIComponent(intentFile)}`, {
      method: 'DELETE',
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || 'Failed to delete intent.');
    }
    removeBoard(board.id);
    renderTabs();
  } catch (error) {
    console.error(error);
    window.alert(error.message || 'Failed to delete intent.');
  }
}

async function deleteReflectionBoard(board) {
  const reflectionFile = board?.metadata?.reflectionFile;
  if (!reflectionFile) {
    return;
  }
  try {
    const response = await fetch(`/api/audio/reflection/${encodeURIComponent(reflectionFile)}`, {
      method: 'DELETE',
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || 'Failed to delete reflection.');
    }
    removeBoard(board.id);
    syncReflectionBoardNames();
    renderTabs();
  } catch (error) {
    console.error(error);
    window.alert(error.message || 'Failed to delete reflection.');
  }
}


function renderTabs() {
  syncReflectionBoardNames();
  tabBar.innerHTML = '';
  boards.forEach((board) => {
    const tab = document.createElement('div');
    tab.className = 'tab-item';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tab-button' + (board.id === activeBoardId ? ' active' : '');
    if (board.kind === 'reflection') btn.classList.add('reflection');
    if (board.kind === 'intent') btn.classList.add('intent');
    btn.textContent = board.name;
    btn.onclick = () => {
      setActiveBoard(board.id);
      renderTabs();
    };

    tab.appendChild(btn);

    if (board.kind === 'reflection' || board.kind === 'intent') {
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'tab-close-button' + (board.id === activeBoardId ? ' active' : '');
      closeBtn.setAttribute('aria-label', `Delete ${board.name}`);
      closeBtn.textContent = '×';
      closeBtn.onclick = async (event) => {
        event.stopPropagation();
        if (board.kind === 'reflection') {
          await deleteReflectionBoard(board);
        } else if (board.kind === 'intent') {
          await deleteIntentBoard(board);
        }
      };
      tab.appendChild(closeBtn);
    }

    tabBar.appendChild(tab);
  });
}
// --- Intent Tab Support ---
export function createIntentTab(intent, metadata = {}) {
  // Ensure intentFile is set in metadata
  const meta = { ...metadata };
  if (!meta.intentFile && meta.intent_file) meta.intentFile = meta.intent_file;
  const board = createIntentBoard(intent, meta);
  setActiveBoard(board.id);
  renderTabs();
}

export function syncIntentTabs(intents) {
  const activeBoard = getActiveBoard();
  const fallbackGraphBoard = boards.find((board) => board.kind === 'graph');
  const nextActiveGraphBoard = activeBoard?.kind === 'graph' ? activeBoard : fallbackGraphBoard;

  const graphBoards = boards.filter((board) => board.kind !== 'intent');
  boards.splice(0, boards.length, ...graphBoards);

  intents.forEach((intent, index) => {
    if (!intent?.data) return;
    // Ensure intentFile is set in metadata
    const meta = { ...intent };
    if (!meta.intentFile && meta.intent_file) meta.intentFile = meta.intent_file;
    const board = createIntentBoard(intent.data, meta);
    board.name = `Intent ${index + 1}`;
  });

  if (nextActiveGraphBoard) {
    setActiveBoard(nextActiveGraphBoard.id);
  }

  renderTabs();
}

export function initTabs() {
  addTabBtn.onclick = () => {
    const board = createBoard();
    setActiveBoard(board.id);
    renderTabs();
  };

  const initial = createBoard();
  setActiveBoard(initial.id);
  renderTabs();
}

export function createReflectionTab(tree, metadata = {}) {
  const board = createReflectionBoard(tree, metadata);
  setActiveBoard(board.id);
  renderTabs();
}

export function syncReflectionTabs(reflections) {
  const activeBoard = getActiveBoard();
  const fallbackGraphBoard = boards.find((board) => board.kind === 'graph');
  const nextActiveGraphBoard = activeBoard?.kind === 'graph' ? activeBoard : fallbackGraphBoard;

  const graphBoards = boards.filter((board) => board.kind !== 'reflection');
  boards.splice(0, boards.length, ...graphBoards);

  reflections.forEach((reflection, index) => {
    if (!reflection?.tree) return;

    const board = createReflectionBoard(reflection.tree, reflection);
    board.name = `Reflection ${index + 1}`;
  });

  if (nextActiveGraphBoard) {
    setActiveBoard(nextActiveGraphBoard.id);
  }

  renderTabs();
}
