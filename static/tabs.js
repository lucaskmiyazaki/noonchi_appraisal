import { tabBar, addTabBtn } from './state.js';
import { boards, activeBoardId, createBoard, createReflectionBoard, setActiveBoard, getActiveBoard, removeBoard } from './board.js';

function syncReflectionBoardNames() {
  let reflectionIndex = 0;
  boards.forEach((board) => {
    if (board.kind !== 'reflection') return;
    reflectionIndex += 1;
    board.name = `Reflection ${reflectionIndex}`;
  });
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
    btn.textContent = board.name;
    btn.onclick = () => {
      setActiveBoard(board.id);
      renderTabs();
    };

    tab.appendChild(btn);

    if (board.kind === 'reflection') {
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'tab-close-button' + (board.id === activeBoardId ? ' active' : '');
      closeBtn.setAttribute('aria-label', `Delete ${board.name}`);
      closeBtn.textContent = '×';
      closeBtn.onclick = async (event) => {
        event.stopPropagation();
        await deleteReflectionBoard(board);
      };
      tab.appendChild(closeBtn);
    }

    tabBar.appendChild(tab);
  });
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
