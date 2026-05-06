/**
 * meeting-widget.js
 *
 * Single persistent component — one HTML element, two states.
 *
 * Idle      → [Start Meeting]  [Desktop | Watch]
 *
 * Recording → same pill, fixed + draggable:
 *               [logo]  [Transcript | Icon]  [Desktop | Watch]  [⠿]
 *               [transcript panel — visible when Transcript tab active]
 *               [● timer ─────────────────────────────────────── Stop]
 *
 * Audio recording starts via MediaRecorder on Start Meeting.
 * Live transcription via Web Speech API populates the transcript panel.
 */
(function () {
  'use strict';

  const STYLE_ID = 'mw-injected-styles';

  const CSS = /* css */`
    .mw-widget {
      display: inline-flex;
      flex-direction: column;
      gap: 8px;
      background: rgba(226, 232, 240, 0.94);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border-radius: 8px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.13), 0 2px 8px rgba(0,0,0,0.07);
      padding: 10px 14px 10px 10px;
      user-select: none;
    }
    .mw-widget.is-fixed {
      position: fixed;
      z-index: 9999;
    }
    .mw-top-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .mw-logo {
      width: 52px;
      height: 52px;
      flex-shrink: 0;
      margin-right: 4px;
      object-fit: contain;
    }
    /* ── Large dark button (Start Meeting) ───────────────────────── */
    .mw-btn {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 7px;
      width: 82px;
      height: 72px;
      background: #1c1b1f;
      color: #fff;
      border: 0;
      border-radius: 8px;
      font-size: 11px;
      font-weight: 600;
      font-family: 'Source Code Pro', monospace;
      cursor: pointer;
      flex-shrink: 0;
      transition: opacity 0.14s;
    }
    .mw-btn:hover { opacity: 0.82; }
    .mw-btn svg {
      width: 22px; height: 22px;
      stroke: currentColor; fill: none;
      stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
    }
    /* ── Segmented toggles (shared) ──────────────────────────────── */
    .mw-seg-wrap {
      display: flex;
      background: rgba(0,0,0,0.07);
      border-radius: 4px;
      padding: 4px;
      gap: 2px;
      align-items: center;
    }
    .mw-seg-btn {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 6px;
      width: 68px;
      height: 72px;
      background: transparent;
      color: #374151;
      border: 0;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      font-family: 'Source Code Pro', monospace;
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
    }
    .mw-seg-btn--view {
      width: auto;
      min-width: 90px;
      padding: 0 6px;
    }
    .mw-seg-btn--transcript {
      min-width: 90px;
    }
    .mw-seg-btn svg {
      width: 22px; height: 22px;
      stroke: currentColor; fill: none;
      stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
    }
    .mw-seg-btn.is-active {
      background: #1c1b1f;
      color: #fff;
      box-shadow: 0 2px 8px rgba(0,0,0,0.18);
      border-radius: 4px;
    }
    /* ── Drag handle ─────────────────────────────────────────────── */
    .mw-drag-handle {
      margin-left: 4px;
      cursor: grab;
      padding: 6px 4px;
      display: flex;
      align-items: center;
      color: #6b7280;
      flex-shrink: 0;
      border-radius: 6px;
      transition: background 0.12s;
    }
    .mw-drag-handle:hover { background: rgba(0,0,0,0.06); }
    .mw-drag-handle:active { cursor: grabbing; }
    /* ── Transcript panel ────────────────────────────────────────── */
    .mw-transcript-panel {
      width: var(--mw-content-width, 340px);
      margin-left: var(--mw-content-offset, 0px);
      min-height: 90px;
      max-height: 200px;
      overflow-y: auto;
      background: #fff;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 13px;
      line-height: 1.55;
      color: #1c1b1f;
      word-break: break-word;
      box-sizing: border-box;
    }
    .mw-transcript-interim {
      color: #6b7280;
    }
    .mw-transcript-interim.mw-q-active {
      background: #fef2b6;
      color: #1c1b1f;
      border-radius: 3px;
      padding: 0 2px;
    }
    .mw-transcript-highlight {
      background: #fef2b6;
      color: #1c1b1f;
      border-radius: 3px;
      padding: 0 2px;
    }
    .mw-transcript-empty {
      color: #94a3b8;
      font-style: italic;
    }
    /* ── Elevation card ────────────────────────────────────────── */
    .mw-elevation-card {
      width: var(--mw-content-width, 340px);
      margin-left: var(--mw-content-offset, 0px);
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: #ffe53a;
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 13px;
      font-weight: 600;
      color: #1f503b;
      box-sizing: border-box;
      margin-top: 4px;
    }
    .mw-elevation-card svg {
      width: 18px;
      height: 18px;
      flex-shrink: 0;
      display: block;
    }
    /* ── Name modal ──────────────────────────────────────────────── */
    .mw-modal-backdrop {
      position: fixed; inset: 0; z-index: 9999;
      background: rgba(15,23,42,0.45);
      display: flex; align-items: center; justify-content: center;
      padding: 24px;
    }
    .mw-modal-backdrop.mw-hidden { display: none; }
    .mw-modal {
      width: min(400px, 100%);
      background: #fff;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 20px 60px rgba(15,23,42,0.22);
      display: flex; flex-direction: column; gap: 16px;
    }
    .mw-modal-title {
      font-size: 17px; font-weight: 700; margin: 0;
    }
    .mw-modal-input {
      width: 100%; box-sizing: border-box;
      border: 1.5px solid #e2e8f0; border-radius: 4px;
      padding: 10px 12px; font: inherit; font-size: 14px;
      outline: none; transition: border-color 0.15s;
    }
    .mw-modal-input:focus { border-color: #1c1b1f; }
    .mw-modal-actions {
      display: flex; gap: 8px; justify-content: flex-end;
    }
    .mw-modal-cancel {
      border: 1px solid #e2e8f0; border-radius: 4px;
      background: #fff; color: #6b7280;
      padding: 8px 16px; font: inherit; font-size: 13px;
      font-weight: 500; cursor: pointer;
    }
    .mw-modal-confirm {
      border: 0; border-radius: 4px;
      background: #1c1b1f; color: #fff;
      padding: 8px 16px; font: inherit; font-size: 13px;
      font-weight: 600; cursor: pointer;
    }
    .mw-modal-confirm:disabled { opacity: 0.45; cursor: not-allowed; }
    /* ── Recording bar ───────────────────────────────────────────── */
    .mw-rec-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      width: var(--mw-content-width, 340px);
      margin-left: var(--mw-content-offset, 0px);
      padding: 0;
      box-sizing: border-box;
    }
    .mw-rec-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #ef4444;
      flex-shrink: 0;
      animation: mw-blink 1.2s ease-in-out infinite;
    }
    @keyframes mw-blink {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.35; }
    }
    .mw-rec-time {
      font-size: 13px;
      font-weight: 600;
      font-family: 'Source Code Pro', monospace;
      color: #1c1b1f;
      min-width: 68px;
    }
    .mw-stop-btn {
      background: #ef4444;
      color: #fff;
      border: 0;
      border-radius: 4px;
      padding: 6px 20px;
      font-size: 13px;
      font-weight: 700;
      font-family: 'Source Code Pro', monospace;
      cursor: pointer;
      transition: background 0.14s;
    }
    .mw-stop-btn:hover { background: #dc2626; }
    .mw-hidden { display: none !important; }
  `;

  /* ------------------------------------------------------------------ */

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  function pad2(n) { return String(n).padStart(2, '0'); }
  function formatTime(s) {
    return pad2(Math.floor(s / 3600)) + ':' + pad2(Math.floor((s % 3600) / 60)) + ':' + pad2(s % 60);
  }

  const SVG_DOCUMENT = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0121 8.414V19a2 2 0 01-2 2z"/></svg>`;
  const SVG_MIC      = `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="2" width="6" height="11" rx="3" ry="3"/><path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`;
  const SVG_DESKTOP  = `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`;
  const SVG_WATCH    = `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="2" width="10" height="20" rx="2" ry="2"/><line x1="5" y1="8" x2="3" y2="8"/><line x1="5" y1="12" x2="1" y2="12"/><line x1="5" y1="16" x2="3" y2="16"/><line x1="19" y1="8" x2="21" y2="8"/><line x1="19" y1="12" x2="23" y2="12"/><line x1="19" y1="16" x2="21" y2="16"/></svg>`;
  const SVG_ICON     = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>`;
  const SVG_ELEVATION = `<svg viewBox="0 0 23.6522 32" fill="none" aria-hidden="true"><path d="M21.2638 2.48451C21.2638 2.48451 16.4204 1.37238 14.7459 3.32667C13.0714 5.28095 11.3519 8.97881 11.3519 8.97881C11.3519 8.97881 15.4143 8.88842 17.8698 8.13665C20.3252 7.38487 21.2638 2.48451 21.2638 2.48451Z" fill="#1F503B"/><ellipse cx="11.8261" cy="20.1741" rx="11.8261" ry="11.8259" fill="#F45520"/></svg>`;
  const SVG_DRAG     = `<svg viewBox="0 0 10 18" width="10" height="18" fill="currentColor" aria-hidden="true"><circle cx="2.5" cy="2.5" r="1.5"/><circle cx="7.5" cy="2.5" r="1.5"/><circle cx="2.5" cy="9" r="1.5"/><circle cx="7.5" cy="9" r="1.5"/><circle cx="2.5" cy="15.5" r="1.5"/><circle cx="7.5" cy="15.5" r="1.5"/></svg>`;

  /* ------------------------------------------------------------------ */

  class MeetingWidget {
    constructor(mountEl, options) {
      this._mount = mountEl;
      this._user  = (options && options.user) || '';
      this._onDeviceChange = (options && options.onDeviceChange) || null;
      this._device = (options && options.device) || 'smartwatch';
      this._timerInterval = null;
      this._seconds = 0;
      this._view = 'transcript'; // 'transcript' | 'icon'
      this._finalSegments = []; // [{text, highlighted}]
      this._highlightPending = false;
      this._qMarked = false;
      this._meetingName = '';
      this._recorder = null;
      this._stream = null;
      this._recognition = null;
      this._chunks = [];

      injectStyles();
      this._build();
    }

    async _persistDeviceSelection(device) {
      const user = String(this._user || '').trim();
      if (!user) return;

      try {
        const response = await fetch(`/api/users/${encodeURIComponent(user)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ nudge_device: device }),
        });

        if (!response.ok) {
          throw new Error(`Failed to save device selection: ${response.status}`);
        }
      } catch (error) {
        console.error('Failed to persist meeting widget device selection', error);
      }
    }

    _build() {
      this._mount.innerHTML = '';

      const pill = document.createElement('div');
      pill.className = 'mw-widget';
      this._pill = pill;

      /* ── Top row ── */
      const row = document.createElement('div');
      row.className = 'mw-top-row';

      /* Logo — recording only */
      const logo = document.createElement('img');
      logo.className = 'mw-logo mw-hidden';
      logo.src = '/static/images/logo.svg';
      logo.alt = 'Noonchi';
      logo.draggable = false;
      this._logo = logo;

      /* Start Meeting button — idle only */
      const startBtn = document.createElement('button');
      startBtn.className = 'mw-btn';
      startBtn.type = 'button';
      startBtn.innerHTML = SVG_MIC + '<span>Start Meeting</span>';
      startBtn.addEventListener('click', () => {
        this._modalInput.value = '';
        this._modalBackdrop.classList.remove('mw-hidden');
        setTimeout(() => this._modalInput.focus(), 50);
      });
      this._startBtn = startBtn;

      /* Transcript | Icon toggle — recording only */
      const viewToggle = document.createElement('div');
      viewToggle.className = 'mw-seg-wrap mw-hidden';
      this._viewToggle = viewToggle;

      const transcriptTabBtn = document.createElement('button');
      transcriptTabBtn.className = 'mw-seg-btn mw-seg-btn--view mw-seg-btn--transcript is-active';
      transcriptTabBtn.type = 'button';
      transcriptTabBtn.innerHTML = SVG_DOCUMENT + '<span>Transcript</span>';
      this._transcriptTabBtn = transcriptTabBtn;

      const iconTabBtn = document.createElement('button');
      iconTabBtn.className = 'mw-seg-btn mw-seg-btn--view';
      iconTabBtn.type = 'button';
      iconTabBtn.innerHTML = SVG_ICON + '<span>Banner</span>';
      this._iconTabBtn = iconTabBtn;

      transcriptTabBtn.addEventListener('click', () => this._setView('transcript'));
      iconTabBtn.addEventListener('click',       () => this._setView('icon'));

      viewToggle.appendChild(transcriptTabBtn);
      viewToggle.appendChild(iconTabBtn);

      /* Desktop | Watch device toggle — always visible */
      const segWrap = document.createElement('div');
      segWrap.className = 'mw-seg-wrap';
      this._segWrap = segWrap;

      const desktopBtn = document.createElement('button');
      desktopBtn.className = 'mw-seg-btn';
      desktopBtn.type = 'button';
      desktopBtn.dataset.mwDevice = 'desktop';
      desktopBtn.innerHTML = SVG_DESKTOP + '<span>Desktop</span>';
      this._desktopSegBtn = desktopBtn;

      const watchBtn = document.createElement('button');
      watchBtn.className = 'mw-seg-btn';
      watchBtn.type = 'button';
      watchBtn.dataset.mwDevice = 'smartwatch';
      watchBtn.innerHTML = SVG_WATCH + '<span>Watch</span>';
      this._watchSegBtn = watchBtn;

      [desktopBtn, watchBtn].forEach(btn => {
        btn.addEventListener('click', async () => {
          const nextDevice = btn.dataset.mwDevice;
          if (!nextDevice || nextDevice === this._device) {
            return;
          }

          this._device = nextDevice;
          this._syncSeg();

          await this._persistDeviceSelection(this._device);

          if (this._onDeviceChange) {
            this._onDeviceChange(this._device);
          }
        });
      });
      segWrap.appendChild(desktopBtn);
      segWrap.appendChild(watchBtn);
      this._syncSeg();

      /* Drag handle — recording only */
      const dragHandle = document.createElement('div');
      dragHandle.className = 'mw-drag-handle mw-hidden';
      dragHandle.setAttribute('aria-label', 'Drag widget');
      dragHandle.innerHTML = SVG_DRAG;
      this._dragHandle = dragHandle;

      row.appendChild(logo);
      row.appendChild(startBtn);
      row.appendChild(viewToggle);
      row.appendChild(segWrap);
      row.appendChild(dragHandle);

      /* ── Transcript panel — recording + transcript tab only ── */
      const transcriptPanel = document.createElement('div');
      transcriptPanel.className = 'mw-transcript-panel mw-hidden';
      transcriptPanel.setAttribute('aria-live', 'polite');
      transcriptPanel.innerHTML = '<span class="mw-transcript-empty">Listening…</span>';
      this._transcriptPanel = transcriptPanel;

      /* ── Recording bar — recording only ── */
      const recBar = document.createElement('div');
      recBar.className = 'mw-rec-bar mw-hidden';
      this._recBar = recBar;

      const dot = document.createElement('span');
      dot.className = 'mw-rec-dot';
      dot.setAttribute('aria-hidden', 'true');

      const timeEl = document.createElement('span');
      timeEl.className = 'mw-rec-time';
      timeEl.textContent = '00:00:00';
      this._timeEl = timeEl;

      const stopBtn = document.createElement('button');
      stopBtn.className = 'mw-stop-btn';
      stopBtn.type = 'button';
      stopBtn.textContent = 'Stop';
      stopBtn.addEventListener('click', () => this._stopRecording());

      recBar.appendChild(dot);
      recBar.appendChild(timeEl);
      recBar.appendChild(stopBtn);

      pill.appendChild(row);
      pill.appendChild(transcriptPanel);
      pill.appendChild(recBar);

      const elevationCard = document.createElement('div');
      elevationCard.className = 'mw-elevation-card mw-hidden';
      elevationCard.innerHTML = `${SVG_ELEVATION}<span>Elevation</span>`;
      this._elevationCard = elevationCard;
      pill.appendChild(elevationCard);

      this._mount.appendChild(pill);

      /* ── Name modal (appended to body so it's truly full-screen) ── */
      const backdrop = document.createElement('div');
      backdrop.className = 'mw-modal-backdrop mw-hidden';
      const modal = document.createElement('div');
      modal.className = 'mw-modal';
      const modalTitle = document.createElement('p');
      modalTitle.className = 'mw-modal-title';
      modalTitle.textContent = 'Name this meeting';
      const modalInput = document.createElement('input');
      modalInput.className = 'mw-modal-input';
      modalInput.type = 'text';
      modalInput.placeholder = 'e.g. Product review';
      modalInput.maxLength = 80;
      const modalActions = document.createElement('div');
      modalActions.className = 'mw-modal-actions';
      const cancelBtn = document.createElement('button');
      cancelBtn.className = 'mw-modal-cancel';
      cancelBtn.type = 'button';
      cancelBtn.textContent = 'Cancel';
      const confirmBtn = document.createElement('button');
      confirmBtn.className = 'mw-modal-confirm';
      confirmBtn.type = 'button';
      confirmBtn.textContent = 'Start';
      modalActions.appendChild(cancelBtn);
      modalActions.appendChild(confirmBtn);
      modal.appendChild(modalTitle);
      modal.appendChild(modalInput);
      modal.appendChild(modalActions);
      backdrop.appendChild(modal);
      document.body.appendChild(backdrop);
      this._modalBackdrop = backdrop;
      this._modalInput = modalInput;
      this._modalConfirmBtn = confirmBtn;

      cancelBtn.addEventListener('click', () => backdrop.classList.add('mw-hidden'));
      backdrop.addEventListener('click', (e) => { if (e.target === backdrop) backdrop.classList.add('mw-hidden'); });
      modalInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') confirmBtn.click(); });
      confirmBtn.addEventListener('click', () => {
        const name = modalInput.value.trim();
        if (!name) return;
        this._meetingName = name;
        backdrop.classList.add('mw-hidden');
        this._startRecording();
      });

      /* Replace startBtn click to open modal instead */
      startBtn.removeEventListener('click', () => this._startRecording());
      startBtn._mwHandler && startBtn.removeEventListener('click', startBtn._mwHandler);

      this._makeDraggable(pill, dragHandle);
    }

    _syncRecordingLayout() {
      if (!this._pill || !this._logo || !this._segWrap) return;
      const pillRect = this._pill.getBoundingClientRect();
      const logoRect = this._logo.getBoundingClientRect();
      const segRect = this._segWrap.getBoundingClientRect();
      if (!pillRect.width || !logoRect.width || !segRect.width) return;

      const contentOffset = Math.max(0, Math.round(logoRect.left - pillRect.left));
      const contentWidth = Math.max(260, Math.round(segRect.right - logoRect.left));

      this._pill.style.setProperty('--mw-content-offset', `${contentOffset}px`);
      this._pill.style.setProperty('--mw-content-width', `${contentWidth}px`);
    }

    _syncSeg() {
      this._desktopSegBtn.classList.toggle('is-active', this._device === 'desktop');
      this._watchSegBtn.classList.toggle('is-active',   this._device === 'smartwatch');
    }

    setDevice(device) {
      this._device = device;
      this._syncSeg();
    }

    _setView(view) {
      this._view = view;
      this._transcriptTabBtn.classList.toggle('is-active', view === 'transcript');
      this._iconTabBtn.classList.toggle('is-active',       view === 'icon');
      this._transcriptPanel.classList.toggle('mw-hidden',  view !== 'transcript');
    }

    /* ── Start ─────────────────────────────────────────────────── */

    _startRecording() {
      this._seconds = 0;
      this._finalSegments = [];
      this._highlightPending = false;
      this._chunks = [];
      this._view = 'transcript';

      /* Fix pill position */
      const rect = this._pill.getBoundingClientRect();
      this._pill.classList.add('is-fixed');
      this._pill.style.top  = rect.top  + 'px';
      this._pill.style.left = rect.left + 'px';

      /* Swap UI */
      this._startBtn.classList.add('mw-hidden');
      this._logo.classList.remove('mw-hidden');
      this._viewToggle.classList.remove('mw-hidden');
      this._transcriptTabBtn.classList.add('is-active');
      this._iconTabBtn.classList.remove('is-active');
      this._dragHandle.classList.remove('mw-hidden');
      this._transcriptPanel.classList.remove('mw-hidden');
      this._transcriptPanel.innerHTML = '<span class="mw-transcript-empty">Listening…</span>';
      this._recBar.classList.remove('mw-hidden');
      this._pill.classList.add('is-recording');
      this._syncRecordingLayout();
      this._onResize = () => this._syncRecordingLayout();
      window.addEventListener('resize', this._onResize);

      /* Timer */
      this._timerInterval = setInterval(() => {
        this._seconds++;
        this._timeEl.textContent = formatTime(this._seconds);
      }, 1000);

      /* Q-key: hold shows card + highlights interim; card stays after release until phrase commits */
      this._onKeyDown = (e) => {
        if (e.key !== 'q' && e.key !== 'Q') return;
        this._qMarked = true;
        this._highlightPending = true;
        this._elevationCard.classList.remove('mw-hidden');
        this._renderTranscript(this._currentInterim || '');
      };
      this._onKeyUp = (e) => {
        if (e.key !== 'q' && e.key !== 'Q') return;
        this._highlightPending = false; // interim stays yellow via _qMarked below
        this._renderTranscript(this._currentInterim || '');
        // card + _qMarked stay until phrase finalizes
      };
      document.addEventListener('keydown', this._onKeyDown);
      document.addEventListener('keyup',   this._onKeyUp);

      /* MediaRecorder */
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices.getUserMedia({ audio: true })
          .then(stream => {
            this._stream = stream;
            try {
              this._recorder = new MediaRecorder(stream);
              this._recorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) this._chunks.push(e.data);
              };
              this._recorder.start(1000);
            } catch (err) {
              console.warn('MediaRecorder error:', err);
            }
          })
          .catch(err => console.warn('getUserMedia denied:', err));
      }

      /* Web Speech API */
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SR) {
        const rec = new SR();
        rec.continuous = true;
        rec.interimResults = true;
        rec.lang = 'en-US';
        rec.onresult = (e) => {
          let interim = '';
          for (let i = e.resultIndex; i < e.results.length; i++) {
            const t = e.results[i][0].transcript;
            if (e.results[i].isFinal) {
              this._finalSegments.push({ text: t + ' ', highlighted: this._qMarked });
              this._qMarked = false;
              this._highlightPending = false;
              this._elevationCard.classList.add('mw-hidden');
            } else {
              interim += t;
            }
          }
          this._currentInterim = interim;
          this._renderTranscript(interim);
        };
        rec.onerror = (e) => {
          if (e.error !== 'no-speech') console.warn('SpeechRecognition error:', e.error);
        };
        /* Auto-restart on end while still recording */
        rec.onend = () => {
          if (this._recognition === rec) {
            try { rec.start(); } catch (_) {}
          }
        };
        rec.start();
        this._recognition = rec;
      }
    }

    /* ── Stop ──────────────────────────────────────────────────── */

    _stopRecording() {
      const meetingName = this._meetingName || 'meeting';
      this._meetingName = '';

      clearInterval(this._timerInterval);
      this._timerInterval = null;
      this._seconds = 0;
      this._timeEl.textContent = '00:00:00';

      /* Stop speech recognition */
      if (this._recognition) {
        const r = this._recognition;
        this._recognition = null; /* prevent onend restart */
        try { r.stop(); } catch (_) {}
      }

      /* Remove Q-key listeners */
      if (this._onKeyDown) {
        document.removeEventListener('keydown', this._onKeyDown);
        document.removeEventListener('keyup',   this._onKeyUp);
        this._onKeyDown = null;
        this._onKeyUp   = null;
      }
      this._highlightPending = false;
      this._qMarked = false;
      this._currentInterim = '';
      this._elevationCard.classList.add('mw-hidden');

      /* Stop MediaRecorder — use onstop so we get the final chunk too */
      const recorder = this._recorder;
      const stream   = this._stream;
      this._recorder = null;
      this._stream   = null;

      if (recorder && recorder.state !== 'inactive') {
        recorder.onstop = () => {
          /* All dataavailable events have fired before onstop */
          const chunks = this._chunks.slice();
          this._chunks = [];
          if (stream) stream.getTracks().forEach(t => t.stop());
          this._confirmSave(chunks, meetingName);
        };
        try { recorder.stop(); } catch (_) {
          if (stream) stream.getTracks().forEach(t => t.stop());
          const chunks = this._chunks.slice();
          this._chunks = [];
          this._confirmSave(chunks, meetingName);
        }
      } else {
        if (stream) stream.getTracks().forEach(t => t.stop());
        const chunks = this._chunks.slice();
        this._chunks = [];
        if (chunks.length) this._confirmSave(chunks, meetingName);
      }

      /* Restore pill */
      this._pill.classList.remove('is-fixed');
      this._pill.style.top  = '';
      this._pill.style.left = '';

      /* Restore UI */
      this._logo.classList.add('mw-hidden');
      this._viewToggle.classList.add('mw-hidden');
      this._dragHandle.classList.add('mw-hidden');
      this._transcriptPanel.classList.add('mw-hidden');
      this._recBar.classList.add('mw-hidden');
      this._startBtn.classList.remove('mw-hidden');
      this._pill.classList.remove('is-recording');
      this._pill.style.removeProperty('--mw-content-offset');
      this._pill.style.removeProperty('--mw-content-width');
      if (this._onResize) {
        window.removeEventListener('resize', this._onResize);
        this._onResize = null;
      }

      this._syncSeg();
    }

    _confirmSave(chunks, meetingName) {
      if (!chunks.length) return; /* nothing recorded */

      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:100000;display:flex;align-items:center;justify-content:center';

      const box = document.createElement('div');
      box.style.cssText = 'background:#fff;border-radius:8px;padding:28px 32px;max-width:340px;width:90%;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.18)';

      const title = document.createElement('p');
      title.style.cssText = 'margin:0 0 8px;font-size:17px;font-weight:600;color:#111';
      title.textContent = 'Save this meeting?';

      const sub = document.createElement('p');
      sub.style.cssText = 'margin:0 0 24px;font-size:14px;color:#555';
      sub.textContent = `"${meetingName}" will be transcribed and analysed.`;

      const btnRow = document.createElement('div');
      btnRow.style.cssText = 'display:flex;gap:12px;justify-content:center';

      const discardBtn = document.createElement('button');
      discardBtn.style.cssText = 'padding:9px 22px;border-radius:4px;border:1px solid #ddd;background:#f5f5f5;font-size:14px;cursor:pointer;color:#555';
      discardBtn.textContent = 'Discard';

      const saveBtn = document.createElement('button');
      saveBtn.style.cssText = 'padding:9px 22px;border-radius:4px;border:none;background:#1c1b1f;color:#fff;font-size:14px;cursor:pointer;font-weight:600';
      saveBtn.textContent = 'Save & Process';

      btnRow.append(discardBtn, saveBtn);
      box.append(title, sub, btnRow);
      overlay.appendChild(box);
      document.body.appendChild(overlay);

      const close = () => document.body.removeChild(overlay);

      discardBtn.addEventListener('click', close);
      saveBtn.addEventListener('click', () => {
        close();
        this._uploadAndProcess(chunks, meetingName);
      });
    }

    async _uploadAndProcess(chunks, meetingName) {
      const blob = new Blob(chunks, { type: 'audio/webm' });
      const safeSession = (meetingName || 'meeting').replace(/[^a-z0-9_-]/gi, '_').toLowerCase();
      const formData = new FormData();
      formData.append('audio', blob, safeSession + '.webm');
      formData.append('session_name', meetingName || 'meeting');
      if (this._user) formData.append('username', this._user);

      window.dispatchEvent(new CustomEvent('mw:processing', {
        detail: { meetingName, phase: 'upload', progress: 0, total: 8, message: 'Uploading\u2026' }
      }));

      try {
        const res = await fetch('/api/audio/process', { method: 'POST', body: formData });
        if (!res.ok) throw new Error('Upload failed: ' + res.status);
        const { job_id: jobId } = await res.json();

        /* Save to localStorage so dashboard can reconnect after page refresh */
        try { localStorage.setItem('mw_process_job', JSON.stringify({ jobId, meetingName })); } catch (_) {}

        /* Notify dashboard of the job_id so it can also connect SSE */
        window.dispatchEvent(new CustomEvent('mw:processing', {
          detail: { jobId, meetingName, phase: 'transcribe', progress: 0, total: 8, message: 'Transcribing\u2026' }
        }));

        const finalData = await this._followSSE(
          `/api/audio/process/job/${encodeURIComponent(jobId)}/stream`,
          (data) => window.dispatchEvent(new CustomEvent('mw:processing', {
            detail: { jobId, meetingName, phase: data.phase || 'pipeline', progress: data.progress || 0, total: data.total || 8, message: data.message || '' }
          })),
          (data) => data.phase === 'done' || data.phase === 'error'
        );

        try { localStorage.removeItem('mw_process_job'); } catch (_) {}

        if (finalData.phase === 'done') {
          window.dispatchEvent(new CustomEvent('mw:processingDone', { detail: { meetingName, recordId: finalData.record_id } }));
        } else {
          throw new Error(finalData.message || 'Processing failed');
        }

      } catch (err) {
        try { localStorage.removeItem('mw_process_job'); } catch (_) {}
        console.error('Meeting processing error:', err);
        window.dispatchEvent(new CustomEvent('mw:processingError', { detail: { meetingName, error: err.message } }));
      }
    }

        _followSSE(url, onMessage, isDone) {
      return new Promise((resolve, reject) => {
        const es = new EventSource(url);
        es.onmessage = (e) => {
          let data;
          try { data = JSON.parse(e.data); } catch (_) { return; }
          onMessage(data);
          if (isDone(data)) {
            es.close();
            resolve(data);
          }
        };
        es.onerror = () => { es.close(); reject(new Error('SSE error: ' + url)); };
      });
    }

    _renderTranscript(interim) {
      let html = this._finalSegments.map(seg =>
        seg.highlighted
          ? '<mark class="mw-transcript-highlight">' + this._escHtml(seg.text) + '</mark>'
          : '<span>' + this._escHtml(seg.text) + '</span>'
      ).join('');
      if (interim) {
        const cls = this._highlightPending || this._qMarked
          ? 'mw-transcript-interim mw-q-active'
          : 'mw-transcript-interim';
        html += '<span class="' + cls + '">' + this._escHtml(interim) + '</span>';
      }
      if (!html) html = '<span class="mw-transcript-empty">Listening…</span>';
      this._transcriptPanel.innerHTML = html;
      this._transcriptPanel.scrollTop = this._transcriptPanel.scrollHeight;
    }

    _escHtml(str) {
      return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    /* ── Drag ──────────────────────────────────────────────────── */

    _makeDraggable(floatEl, handleEl) {
      let startX, startY, startLeft, startTop;

      const onMove = (cx, cy) => {
        floatEl.style.left = (startLeft + cx - startX) + 'px';
        floatEl.style.top  = (startTop  + cy - startY) + 'px';
      };

      const onMouseMove = (e) => onMove(e.clientX, e.clientY);
      const onMouseUp   = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup',   onMouseUp);
      };

      handleEl.addEventListener('mousedown', (e) => {
        if (!floatEl.classList.contains('is-fixed')) return;
        e.preventDefault();
        const r   = floatEl.getBoundingClientRect();
        startX    = e.clientX;
        startY    = e.clientY;
        startLeft = r.left;
        startTop  = r.top;
        floatEl.style.right = 'auto';
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup',   onMouseUp);
      });

      handleEl.addEventListener('touchstart', (e) => {
        if (!floatEl.classList.contains('is-fixed')) return;
        const t   = e.touches[0];
        const r   = floatEl.getBoundingClientRect();
        startX    = t.clientX;
        startY    = t.clientY;
        startLeft = r.left;
        startTop  = r.top;
        floatEl.style.right = 'auto';
      }, { passive: true });

      handleEl.addEventListener('touchmove', (e) => {
        if (!floatEl.classList.contains('is-fixed')) return;
        e.preventDefault();
        onMove(e.touches[0].clientX, e.touches[0].clientY);
      }, { passive: false });
    }
  }

  /* ------------------------------------------------------------------ */

  window.initMeetingWidget = function (el, opts) {
    return new MeetingWidget(el, opts || {});
  };

}());

