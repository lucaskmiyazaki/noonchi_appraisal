import { tabBar, addTabBtn } from './state.js';
import { boards, activeBoardId, createBoard, createReflectionBoard, setActiveBoard, getActiveBoard } from './board.js';

function renderTabs() {
  tabBar.innerHTML = '';
  boards.forEach((board) => {
    const btn = document.createElement('button');
    btn.className = 'tab-button' + (board.id === activeBoardId ? ' active' : '');
    if (board.kind === 'reflection') btn.classList.add('reflection');
    btn.textContent = board.name;
    btn.onclick = () => {
      setActiveBoard(board.id);
      renderTabs();
    };
    tabBar.appendChild(btn);
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

export function createReflectionTab(tree) {
  const board = createReflectionBoard(tree);
  setActiveBoard(board.id);
  renderTabs();
}

export function syncReflectionTabs(trees) {
  const activeBoard = getActiveBoard();
  const fallbackGraphBoard = boards.find((board) => board.kind === 'graph');
  const nextActiveGraphBoard = activeBoard?.kind === 'graph' ? activeBoard : fallbackGraphBoard;

  const graphBoards = boards.filter((board) => board.kind !== 'reflection');
  boards.splice(0, boards.length, ...graphBoards);

  trees.forEach((tree, index) => {
    const board = createReflectionBoard(tree);
    board.name = `Reflection ${index + 1}`;
  });

  if (nextActiveGraphBoard) {
    setActiveBoard(nextActiveGraphBoard.id);
  }

  renderTabs();
}
