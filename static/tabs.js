import { tabBar, addTabBtn } from './state.js';
import { boards, activeBoardId, createBoard, setActiveBoard } from './board.js';

function renderTabs() {
  tabBar.innerHTML = '';
  boards.forEach((board) => {
    const btn = document.createElement('button');
    btn.className = 'tab-button' + (board.id === activeBoardId ? ' active' : '');
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
