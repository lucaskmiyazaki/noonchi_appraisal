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
      border-radius: 20px;
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
      width: 28px;
      height: 34px;
      flex-shrink: 0;
      margin-right: 2px;
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
      background: #111827;
      color: #fff;
      border: 0;
      border-radius: 14px;
      font-size: 11px;
      font-weight: 600;
      font-family: inherit;
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
      border-radius: 12px;
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
      height: 64px;
      background: transparent;
      color: #374151;
      border: 0;
      border-radius: 9px;
      font-size: 11px;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
    }
    .mw-seg-btn svg {
      width: 22px; height: 22px;
      stroke: currentColor; fill: none;
      stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
    }
    .mw-seg-btn.is-active {
      background: #111827;
      color: #fff;
      box-shadow: 0 2px 8px rgba(0,0,0,0.18);
      border-radius: 8px;
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
      width: 340px;
      min-height: 90px;
      max-height: 200px;
      overflow-y: auto;
      background: rgba(255,255,255,0.7);
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 13px;
      line-height: 1.55;
      color: #111827;
      word-break: break-word;
      box-sizing: border-box;
    }
    .mw-transcript-interim {
      color: #6b7280;
    }
    .mw-transcript-empty {
      color: #94a3b8;
      font-style: italic;
    }
    /* ── Recording bar ───────────────────────────────────────────── */
    .mw-rec-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 4px;
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
      font-family: 'Courier New', monospace;
      color: #111827;
      min-width: 68px;
    }
    .mw-stop-btn {
      margin-left: auto;
      background: #ef4444;
      color: #fff;
      border: 0;
      border-radius: 8px;
      padding: 6px 20px;
      font-size: 13px;
      font-weight: 700;
      font-family: inherit;
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
      this._finalTranscript = '';
      this._recorder = null;
      this._stream = null;
      this._recognition = null;
      this._chunks = [];

      injectStyles();
      this._build();
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
      startBtn.addEventListener('click', () => this._startRecording());
      this._startBtn = startBtn;

      /* Transcript | Icon toggle — recording only */
      const viewToggle = document.createElement('div');
      viewToggle.className = 'mw-seg-wrap mw-hidden';
      this._viewToggle = viewToggle;

      const transcriptTabBtn = document.createElement('button');
      transcriptTabBtn.className = 'mw-seg-btn is-active';
      transcriptTabBtn.type = 'button';
      transcriptTabBtn.innerHTML = SVG_DOCUMENT + '<span>Transcript</span>';
      this._transcriptTabBtn = transcriptTabBtn;

      const iconTabBtn = document.createElement('button');
      iconTabBtn.className = 'mw-seg-btn';
      iconTabBtn.type = 'button';
      iconTabBtn.innerHTML = SVG_ICON + '<span>Icon</span>';
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
        btn.addEventListener('click', () => {
          this._device = btn.dataset.mwDevice;
          this._syncSeg();
          if (this._onDeviceChange) this._onDeviceChange(this._device);
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
      this._mount.appendChild(pill);

      this._makeDraggable(pill, dragHandle);
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
      this._finalTranscript = '';
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

      /* Timer */
      this._timerInterval = setInterval(() => {
        this._seconds++;
        this._timeEl.textContent = formatTime(this._seconds);
      }, 1000);

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
              this._finalTranscript += t + ' ';
            } else {
              interim += t;
            }
          }
          this._transcriptPanel.innerHTML =
            (this._finalTranscript
              ? '<span>' + this._escHtml(this._finalTranscript) + '</span>'
              : '') +
            (interim
              ? '<span class="mw-transcript-interim">' + this._escHtml(interim) + '</span>'
              : '');
          this._transcriptPanel.scrollTop = this._transcriptPanel.scrollHeight;
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

      /* Stop MediaRecorder + stream */
      if (this._recorder && this._recorder.state !== 'inactive') {
        try { this._recorder.stop(); } catch (_) {}
      }
      if (this._stream) {
        this._stream.getTracks().forEach(t => t.stop());
        this._stream = null;
      }
      this._recorder = null;

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

      this._syncSeg();
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

