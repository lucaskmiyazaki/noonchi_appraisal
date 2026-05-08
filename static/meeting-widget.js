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
      --mw-highlight-bg: #fef2b6;
      display: inline-flex;
      flex-direction: column;
      gap: var(--sp-3);
      background:
        linear-gradient(135deg, rgba(255,255,255,0.52) 0%, rgba(255,255,255,0.45) 100%),
        linear-gradient(135deg, rgba(255,229,58,0.22) 0%, rgba(79,54,215,0.14) 100%);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border-radius: 8px;
      box-shadow: 0 6px 18px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.05);
      padding: var(--sp-4) var(--sp-6) var(--sp-4) var(--sp-4);
      user-select: none;
    }
    .mw-widget.is-fixed {
      position: fixed;
      z-index: 9999;
    }
    .mw-top-row {
      display: flex;
      align-items: center;
      gap: var(--sp-3);
    }
    .mw-logo {
      width: 52px;
      height: 52px;
      flex-shrink: 0;
      margin-right: var(--sp-1);
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
      background: var(--control-active-bg);
      color: var(--control-active-fg);
      border: 1px solid var(--control-border-color);
      border-radius: var(--control-radius);
      font-size: var(--control-font-size);
      font-weight: var(--control-font-weight);
      font-family: var(--control-font-family);
      cursor: pointer;
      flex-shrink: 0;
      box-shadow: var(--control-active-shadow);
      transition: background 0.12s ease, box-shadow 0.12s ease;
    }
    .mw-btn:hover { background: #2a2930; }
    .mw-btn svg {
      width: 22px; height: 22px;
      stroke: currentColor; fill: none;
      stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
    }
    /* Homepage-only: keep widget attached look but show icon inline with text. */
    .mw-widget:not(.is-fixed) .mw-btn {
      flex-direction: row;
      gap: var(--sp-3);
      width: auto;
      min-width: 148px;
      height: 48px;
      padding: 0 var(--sp-6);
    }
    .mw-widget:not(.is-fixed) .mw-seg-btn {
      flex-direction: row;
      gap: var(--sp-3);
      width: auto;
      min-width: 106px;
      height: 48px;
      padding: 0 var(--sp-6);
    }
    /* ── Segmented toggles (shared) ──────────────────────────────── */
    .mw-seg-wrap {
      display: flex;
      background: rgba(255,255,255,0.26);
      border-radius: 4px;
      padding: var(--sp-1);
      gap: 2px;
      align-items: center;
    }
    .mw-seg-btn {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: var(--sp-2);
      width: 68px;
      height: 72px;
      background: rgba(255,255,255,0.55);
      color: var(--control-fg);
      border: 1px solid var(--control-border-color);
      border-radius: var(--control-radius);
      font-size: var(--control-font-size);
      font-weight: var(--control-font-weight);
      font-family: var(--control-font-family);
      cursor: pointer;
      transition: background 0.12s ease, color 0.12s ease, box-shadow 0.12s ease;
    }
    .mw-seg-btn--view {
      width: auto;
      min-width: 90px;
      padding: 0 var(--sp-2);
    }
    .mw-seg-btn--transcript {
      min-width: 90px;
    }
    .mw-seg-btn svg {
      width: 22px; height: 22px;
      stroke: currentColor; fill: none;
      stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
    }
    .mw-watch-icon-wrap {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .mw-watch-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: #ef4444;
      box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.12);
      flex-shrink: 0;
    }
    .mw-watch-status-dot.is-connecting {
      width: 10px;
      height: 10px;
      background: transparent;
      border: 2px solid rgba(107, 114, 128, 0.35);
      border-top-color: #374151;
      box-shadow: none;
      animation: mw-watch-spin 0.8s linear infinite;
    }
    .mw-watch-status-dot.is-connected {
      background: #22c55e;
      box-shadow: 0 0 0 1px rgba(34, 197, 94, 0.25);
    }
    @keyframes mw-watch-spin {
      to {
        transform: rotate(360deg);
      }
    }
    .mw-seg-btn.is-active {
      background: var(--control-active-bg);
      color: var(--control-active-fg);
      box-shadow: var(--control-active-shadow);
    }
    /* ── Drag handle ─────────────────────────────────────────────── */
    .mw-drag-handle {
      margin-left: var(--sp-1);
      cursor: grab;
      padding: var(--sp-2) var(--sp-1);
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
      background: rgba(255,255,255,0.58);
      border: 1px solid rgba(148, 163, 184, 0.45);
      border-radius: 8px;
      padding: var(--sp-4) var(--sp-5);
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
      background: var(--mw-highlight-bg);
      color: #1c1b1f;
      border-radius: 3px;
      padding: 0 2px;
    }
    .mw-transcript-highlight {
      background: var(--mw-highlight-bg);
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
      gap: var(--sp-3);
      background: rgba(255, 229, 58, 0.48);
      border-radius: 8px;
      padding: var(--sp-4) var(--sp-6);
      font-size: 13px;
      font-weight: 600;
      color: #1f503b;
      box-sizing: border-box;
      margin-top: var(--sp-1);
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
      padding: var(--sp-9);
    }
    .mw-modal-backdrop.mw-hidden { display: none; }
    .mw-modal {
      width: min(400px, 100%);
      background: rgba(255,255,255,0.88);
      border-radius: 8px;
      padding: var(--sp-9);
      box-shadow: 0 20px 60px rgba(15,23,42,0.22);
      display: flex; flex-direction: column; gap: var(--sp-7);
    }
    .mw-modal-title {
      font-size: 17px; font-weight: 700; margin: 0;
    }
    .mw-modal-input {
      width: 100%; box-sizing: border-box;
      border: 1.5px solid #e2e8f0; border-radius: 4px;
      padding: var(--sp-4) var(--sp-5); font: inherit; font-size: 14px;
      outline: none; transition: border-color 0.15s;
    }
    .mw-modal-input:focus { border-color: #1c1b1f; }
    .mw-modal-actions {
      display: flex; gap: var(--sp-3); justify-content: flex-end;
    }
    .mw-modal-cancel {
      border: 1px solid var(--control-border-color);
      border-radius: var(--control-radius);
      background: var(--control-bg);
      color: var(--control-fg);
      padding: var(--control-pad-y) var(--control-pad-x);
      font-family: var(--control-font-family);
      font-size: var(--control-font-size);
      font-weight: var(--control-font-weight);
      cursor: pointer;
    }
    .mw-modal-confirm {
      border: 1px solid var(--control-border-color);
      border-radius: var(--control-radius);
      background: var(--control-active-bg);
      color: var(--control-active-fg);
      padding: var(--control-pad-y) var(--control-pad-x);
      font-family: var(--control-font-family);
      font-size: var(--control-font-size);
      font-weight: var(--control-font-weight);
      cursor: pointer;
      box-shadow: var(--control-active-shadow);
    }
    .mw-modal-confirm:disabled { opacity: 0.45; cursor: not-allowed; }
    /* ── Recording bar ───────────────────────────────────────────── */
    .mw-rec-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--sp-3);
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
      font-size: var(--control-font-size);
      font-weight: var(--control-font-weight);
      font-family: var(--control-font-family);
      color: #1c1b1f;
      min-width: 68px;
    }
    .mw-stop-btn {
      background: var(--control-active-bg);
      color: var(--control-active-fg);
      border: 1px solid var(--control-border-color);
      border-radius: var(--control-radius);
      padding: var(--control-pad-y) calc(var(--control-pad-x) + var(--sp-2));
      font-size: var(--control-font-size);
      font-weight: var(--control-font-weight);
      font-family: var(--control-font-family);
      cursor: pointer;
      box-shadow: var(--control-active-shadow);
      transition: background 0.12s ease;
    }
    .mw-stop-btn:hover { background: #2a2930; }
    .mw-confirm-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,.5);
      z-index: 100000;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .mw-confirm-box {
      background: rgba(255,255,255,0.9);
      border-radius: 8px;
      padding: 28px 32px;
      max-width: 340px;
      width: 90%;
      text-align: center;
      box-shadow: 0 8px 32px rgba(0,0,0,.18);
    }
    .mw-confirm-title {
      margin: 0 0 var(--sp-3);
      font-size: var(--fs-h4);
      font-weight: var(--fw-semibold);
      color: #111;
      font-family: var(--font-heading);
    }
    .mw-confirm-sub {
      margin: 0 0 var(--sp-9);
      font-size: var(--fs-body);
      color: #555;
      font-family: var(--font-mono);
    }
    .mw-confirm-actions {
      display: flex;
      gap: var(--sp-5);
      justify-content: center;
    }
    .mw-confirm-discard,
    .mw-confirm-save {
      padding: var(--control-pad-y) calc(var(--control-pad-x) + var(--sp-2));
      border-radius: var(--control-radius);
      font-size: var(--control-font-size);
      font-family: var(--control-font-family);
      font-weight: var(--control-font-weight);
      cursor: pointer;
      line-height: 1;
      min-height: var(--control-height);
    }
    .mw-confirm-discard {
      border: 1px solid var(--control-border-color);
      background: var(--control-bg);
      color: var(--control-fg);
    }
    .mw-confirm-save {
      border: 1px solid var(--control-border-color);
      background: var(--control-active-bg);
      color: var(--control-active-fg);
      box-shadow: var(--control-active-shadow);
    }
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

  const SVG_DOCUMENT = `<svg aria-hidden="true"><use href="#icon-document"></use></svg>`;
  const SVG_MIC      = `<svg aria-hidden="true"><use href="#icon-mic"></use></svg>`;
  const SVG_DESKTOP  = `<svg aria-hidden="true"><use href="#icon-desktop"></use></svg>`;
  const SVG_WATCH    = `<svg aria-hidden="true"><use href="#icon-watch"></use></svg>`;
  const SVG_ICON     = `<svg aria-hidden="true"><use href="#icon-bell"></use></svg>`;
  const SVG_ELEVATION = `<svg viewBox="0 0 23.6522 32" fill="none" aria-hidden="true"><path d="M21.2638 2.48451C21.2638 2.48451 16.4204 1.37238 14.7459 3.32667C13.0714 5.28095 11.3519 8.97881 11.3519 8.97881C11.3519 8.97881 15.4143 8.88842 17.8698 8.13665C20.3252 7.38487 21.2638 2.48451 21.2638 2.48451Z" fill="#1F503B"/><ellipse cx="11.8261" cy="20.1741" rx="11.8261" ry="11.8259" fill="#F45520"/></svg>`;
  const SVG_TONE_DIFFERENCE = `<svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M4.68629 27.3137C6.17203 28.7994 7.93585 29.978 9.87706 30.7821C11.8183 31.5861 13.8988 32 16 32C18.1011 32 20.1817 31.5861 22.1229 30.7821C24.0641 29.978 25.828 28.7994 27.3137 27.3137C28.7994 25.828 29.978 24.0641 30.7821 22.1229C31.5861 20.1817 32 18.1011 32 16C32 13.8988 31.5861 11.8183 30.7821 9.87706C29.978 7.93586 28.7994 6.17203 27.3137 4.68629L16 16L4.68629 27.3137Z" fill="#E34754"/><path d="M4.6863 27.3137C6.17204 28.7994 7.93586 29.978 9.87707 30.7821C11.8183 31.5861 13.8989 32 16 32C18.1012 32 20.1817 31.5861 22.1229 30.7821C24.0641 29.978 25.828 28.7994 27.3137 27.3137C28.7994 25.828 29.978 24.0641 30.7821 22.1229C31.5861 20.1817 32 18.1011 32 16C32 13.8988 31.5861 11.8183 30.7821 9.87706C29.978 7.93585 28.7994 6.17203 27.3137 4.68629L25.2316 6.76839C26.4439 7.9807 27.4056 9.41993 28.0617 11.0039C28.7178 12.5879 29.0555 14.2855 29.0555 16C29.0555 17.7145 28.7178 19.4121 28.0617 20.9961C27.4056 22.5801 26.4439 24.0193 25.2316 25.2316C24.0193 26.4439 22.5801 27.4056 20.9961 28.0617C19.4121 28.7178 17.7145 29.0555 16 29.0555C14.2855 29.0555 12.5879 28.7178 11.0039 28.0617C9.41994 27.4056 7.98071 26.4439 6.7684 25.2316L4.6863 27.3137Z" fill="#6ABB6E"/></svg>`;
  const SVG_UNCLEAR_INTENT = `<svg viewBox="0 0 25.7051 31.9989" fill="none" aria-hidden="true"><path d="M4.41456 0.000551451C4.46091 -0.000251397 9.82002 -0.0877937 11.1577 2.35504C11.7641 3.46249 12.3002 4.94997 12.7065 6.2486C13.1129 4.94995 13.6499 3.46259 14.2564 2.35504C15.5999 -0.0984093 21.0005 0.000551451 21.0005 0.000551451C21.0012 0.0444295 21.0889 5.42822 18.6558 6.77204C17.1299 7.61462 14.8795 8.32265 13.4048 8.7359C13.467 8.98425 13.5024 9.12653 13.5024 9.12653C13.4954 9.12488 13.1931 9.05258 12.7065 8.92438C12.215 9.05388 11.9116 9.12653 11.9116 9.12653C11.9116 9.12653 11.946 8.98364 12.0083 8.73493C10.5337 8.32163 8.28455 7.61425 6.75928 6.77204C4.32586 5.42826 4.41381 0.0436992 4.41456 0.000551451Z" fill="#4C1D95"/><path d="M12.8525 23.4296C15.2185 23.4298 17.1367 25.3485 17.1367 27.7147C17.1366 30.0809 15.2184 31.9987 12.8525 31.9989C10.4865 31.9989 8.56748 30.081 8.56738 27.7147C8.56738 25.3483 10.4864 23.4296 12.8525 23.4296ZM8.56836 15.9393C10.9344 15.9394 12.8525 17.8582 12.8525 20.2245C12.8525 22.5908 10.9344 24.5086 8.56836 24.5087C6.20225 24.5087 4.28425 22.5908 4.28418 20.2245C4.28418 17.8581 6.20221 15.9393 8.56836 15.9393ZM17.1377 15.9393C19.5037 15.9395 21.4219 17.8582 21.4219 20.2245C21.4218 22.5907 19.5036 24.5085 17.1377 24.5087C14.7716 24.5087 12.8536 22.5908 12.8535 20.2245C12.8535 17.8581 14.7715 15.9393 17.1377 15.9393ZM12.8525 8.43933C15.2184 8.43956 17.1366 10.3574 17.1367 12.7235C17.1367 15.0898 15.2185 17.0084 12.8525 17.0087C10.4928 17.0087 8.57777 15.1006 8.56738 12.743C8.55699 15.1006 6.6439 17.0087 4.28418 17.0087C1.91808 17.0086 0 15.0899 0 12.7235C0.000130221 10.3573 1.91816 8.43939 4.28418 8.43933C6.64341 8.43933 8.55621 10.3462 8.56738 12.703C8.57855 10.3462 10.4933 8.43933 12.8525 8.43933ZM21.4209 8.43933C23.787 8.43933 25.7049 10.3572 25.7051 12.7235C25.7051 15.0899 23.787 17.0087 21.4209 17.0087C19.0549 17.0085 17.1367 15.0898 17.1367 12.7235C17.1368 10.3573 19.055 8.43952 21.4209 8.43933Z" fill="#6D28D9"/></svg>`;
  const SVG_EXCELLENT_TONE = `<svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M16 28 C16 28 7 22 7 14 C7 9.5 10.5 6 15 6 C15.7 6 16 6.5 16 6.5 C16 6.5 16.3 6 17 6 C21.5 6 25 9.5 25 14 C25 22 16 28 16 28Z" fill="#16a34a"/><path d="M16 6.5 C16 6.5 16 14 16 28" stroke="#bbf7d0" stroke-width="1.2" stroke-linecap="round"/></svg>`;
  const SVG_NEED_FOR_CLARIFICATION = `<svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><circle cx="16" cy="16" r="16" fill="#2D6BB8"/><path d="M15.5867 11.274C15.7851 10.9824 16.2149 10.9824 16.4133 11.274L17.3414 12.6376C17.4421 12.7855 17.6141 12.8683 17.7925 12.8548L19.4372 12.7302C19.7889 12.7036 20.0569 13.0396 19.9527 13.3765L19.4652 14.9523C19.4123 15.1232 19.4548 15.3094 19.5766 15.4404L20.6995 16.6487C20.9396 16.907 20.844 17.326 20.5155 17.4546L18.9797 18.056C18.813 18.1212 18.694 18.2705 18.6675 18.4474L18.423 20.0786C18.3707 20.4274 17.9834 20.6139 17.6781 20.4373L16.2503 19.6115C16.0955 19.5219 15.9045 19.5219 15.7497 19.6115L14.3219 20.4373C14.0166 20.6139 13.6293 20.4274 13.577 20.0787L13.3325 18.4474C13.306 18.2705 13.187 18.1212 13.0203 18.056L11.4845 17.4546C11.156 17.326 11.0604 16.907 11.3005 16.6487L12.4234 15.4404C12.5452 15.3094 12.5877 15.1232 12.5348 14.9523L12.0473 13.3765C11.9431 13.0396 12.2111 12.7036 12.5628 12.7302L14.2075 12.8548C14.3859 12.8683 14.5579 12.7855 14.6586 12.6376L15.5867 11.274Z" fill="#1C1B1F"/></svg>`;
  const TRIGGER_THEME = {
    tone_difference: { bg: 'var(--trigger-tone-difference-bg)', fg: 'var(--trigger-tone-difference-icon)', icon: SVG_TONE_DIFFERENCE },
    elevation: { bg: 'var(--trigger-elevation-bg)', fg: 'var(--trigger-elevation-icon)', icon: SVG_ELEVATION },
    unclear_intent: { bg: 'var(--trigger-unclear-intent-bg)', fg: 'var(--trigger-unclear-intent-icon)', icon: SVG_UNCLEAR_INTENT },
    excellent_tone: { bg: 'var(--trigger-excellent-tone-bg)', fg: 'var(--trigger-excellent-tone-icon)', icon: SVG_EXCELLENT_TONE },
    need_for_clarification: { bg: 'var(--trigger-clarification-bg)', fg: 'var(--trigger-clarification-icon)', icon: SVG_NEED_FOR_CLARIFICATION },
  };
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
      this._arousalMarked = false;
      this._arousalCooldownUntil = 0;
      this._arousalReleaseTimer = null;
      this._arousalMonitor = null;
      this._nudgeTypeLabel = 'Vibrate';
      this._nudgeTriggerLabel = 'Elevation';
      this._nudgeTriggerKey = 'elevation';
      this._isWatchConnected = false;
      this._isWatchConnecting = false;
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
      watchBtn.innerHTML = '<span class="mw-watch-icon-wrap"><span class="mw-watch-status-dot" aria-hidden="true"></span>' + SVG_WATCH + '</span><span>Watch</span>';
      this._watchSegBtn = watchBtn;
      this._watchStatusDot = watchBtn.querySelector('.mw-watch-status-dot');

      if (!this._onBangleConnectionStatus) {
        this._onBangleConnectionStatus = (event) => {
          this._setWatchConnectionStatus(Boolean(event?.detail?.connected));
        };
        window.addEventListener('bangle:connection', this._onBangleConnectionStatus);
      }
      const isConnected = typeof window.isBangleConnected === 'function' ? window.isBangleConnected() : false;
      this._setWatchConnectionStatus(isConnected);

      [desktopBtn, watchBtn].forEach(btn => {
        btn.addEventListener('click', async () => {
          const nextDevice = btn.dataset.mwDevice;
          if (!nextDevice || nextDevice === this._device) {
            return;
          }

          await this.setDevice(nextDevice);
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
      elevationCard.innerHTML = `<span class="mw-trigger-icon">${SVG_ELEVATION}</span><span class="mw-trigger-label">Elevation</span>`;
      this._elevationCard = elevationCard;
      this._elevationIcon = elevationCard.querySelector('.mw-trigger-icon');
      this._elevationLabel = elevationCard.querySelector('.mw-trigger-label');
      pill.appendChild(elevationCard);
      this._applyTriggerVisual();

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

    async _setDeviceToDesktop() {
      if (this._device === 'desktop') {
        this._syncSeg();
        return;
      }

      this._device = 'desktop';
      this._syncSeg();
      await this._persistDeviceSelection(this._device);

      if (this._onDeviceChange) {
        this._onDeviceChange(this._device);
      }
    }

    async _ensureWatchConnection() {
      let connected = typeof window.isBangleConnected === 'function' ? window.isBangleConnected() : false;
      if (connected) {
        return true;
      }

      try {
        if (typeof window.tryAutoConnectBangle === 'function') {
          await window.tryAutoConnectBangle();
        }
      } catch (_) {
        /* Fall through to permission prompt below. */
      }

      connected = typeof window.isBangleConnected === 'function' ? window.isBangleConnected() : false;
      if (connected) {
        return true;
      }

      try {
        if (typeof window.requestBanglePermissionAndConnect === 'function') {
          await window.requestBanglePermissionAndConnect();
        }
      } catch (_) {
        return false;
      }

      return typeof window.isBangleConnected === 'function' ? window.isBangleConnected() : false;
    }

    _setWatchConnectionStatus(isConnected) {
      if (!this._watchStatusDot) return;
      const wasConnected = this._isWatchConnected;
      this._isWatchConnected = !!isConnected;
      this._setWatchConnectingStatus(false);
      this._watchStatusDot.classList.toggle('is-connected', !!isConnected);
      this._watchStatusDot.setAttribute('title', isConnected ? 'Bangle connected' : 'Bangle disconnected');
      this._watchStatusDot.setAttribute('aria-label', isConnected ? 'Bangle connected' : 'Bangle disconnected');

      if (wasConnected && !isConnected && this._device === 'smartwatch') {
        this._setDeviceToDesktop();
      }
    }

    _setWatchConnectingStatus(isConnecting) {
      if (!this._watchStatusDot) return;
      this._isWatchConnecting = !!isConnecting;
      this._watchStatusDot.classList.toggle('is-connecting', this._isWatchConnecting);
      if (this._isWatchConnecting) {
        this._watchStatusDot.classList.remove('is-connected');
        this._watchStatusDot.setAttribute('title', 'Connecting to Bangle');
        this._watchStatusDot.setAttribute('aria-label', 'Connecting to Bangle');
      }
    }

    _applyTriggerVisual() {
      if (!this._elevationCard) return;
      const theme = TRIGGER_THEME[this._nudgeTriggerKey] || TRIGGER_THEME.elevation;
      if (theme) {
        this._elevationCard.style.background = theme.bg;
        this._elevationCard.style.color = theme.fg;
        if (this._pill) {
          this._pill.style.setProperty('--mw-highlight-bg', theme.bg);
        }
        if (this._elevationIcon) {
          this._elevationIcon.innerHTML = theme.icon;
        }
      }
      if (this._elevationLabel) {
        this._elevationLabel.textContent = this._nudgeTriggerLabel;
      }
    }

    _notifyBangleElevation() {
      if (this._device !== 'smartwatch') {
        return;
      }

      if (typeof window.isBangleConnected === 'function' && !window.isBangleConnected()) {
        return;
      }

      if (typeof window.sendSimpleMessageToBangle !== 'function') {
        return;
      }

      const trigger = String(this._nudgeTriggerLabel || 'Elevation').trim() || 'Elevation';
      const nudgeType = String(this._nudgeTypeLabel || 'Vibrate').trim() || 'Vibrate';

      window.sendSimpleMessageToBangle({
        trigger_key: this._nudgeTriggerKey,
        type: trigger,
        message: `${trigger} (${nudgeType})`,
        speaker: '',
        force_vibrate: true
      }).catch((err) => {
        console.warn('Failed to send message to Bangle:', err);
      });
    }

    setNudgeContext(typeLabel, triggerLabel, triggerKey) {
      this._nudgeTypeLabel = String(typeLabel || this._nudgeTypeLabel || 'Vibrate').trim() || 'Vibrate';
      this._nudgeTriggerLabel = String(triggerLabel || this._nudgeTriggerLabel || 'Elevation').trim() || 'Elevation';
      this._nudgeTriggerKey = String(triggerKey || this._nudgeTriggerKey || 'elevation').trim() || 'elevation';
      this._applyTriggerVisual();
    }

    async setDevice(device) {
      const nextDevice = device === 'desktop' ? 'desktop' : 'smartwatch';
      if (nextDevice === 'smartwatch') {
        this._device = 'smartwatch';
        this._syncSeg();
        const isAlreadyConnected = typeof window.isBangleConnected === 'function' ? window.isBangleConnected() : false;
        if (!isAlreadyConnected) {
          this._setWatchConnectingStatus(true);
        }
        let connected = false;
        try {
          connected = await this._ensureWatchConnection();
        } finally {
          this._setWatchConnectingStatus(false);
        }
        if (!connected) {
          this._device = 'desktop';
          this._syncSeg();
        }
      } else {
        this._device = 'desktop';
        this._setWatchConnectingStatus(false);
        this._syncSeg();
      }
    }

    _setView(view) {
      this._view = view;
      this._transcriptTabBtn.classList.toggle('is-active', view === 'transcript');
      this._iconTabBtn.classList.toggle('is-active',       view === 'icon');
      this._transcriptPanel.classList.toggle('mw-hidden',  view !== 'transcript');
    }

    _signalArousalHighlight() {
      if (this._device !== 'smartwatch') return;

      const now = Date.now();
      if (now < this._arousalCooldownUntil) return;
      this._arousalCooldownUntil = now + 1800;

      this._arousalMarked = true;
      this._highlightPending = true;
      this._elevationCard.classList.remove('mw-hidden');
      this._notifyBangleElevation();
      this._renderTranscript(this._currentInterim || '');

      if (this._arousalReleaseTimer) {
        clearTimeout(this._arousalReleaseTimer);
      }
      this._arousalReleaseTimer = setTimeout(() => {
        this._highlightPending = false;
        this._renderTranscript(this._currentInterim || '');
      }, 1300);
    }

    _startAudioArousalMonitor(stream) {
      if (typeof window.createMeetingWidgetArousalMonitor !== 'function') {
        return;
      }

      if (!this._arousalMonitor) {
        this._arousalMonitor = window.createMeetingWidgetArousalMonitor(() => this._signalArousalHighlight());
      }
      this._arousalMonitor.start(stream);
    }

    _stopAudioArousalMonitor() {
      if (this._arousalMonitor && typeof this._arousalMonitor.stop === 'function') {
        this._arousalMonitor.stop();
      }
    }

    /* ── Start ─────────────────────────────────────────────────── */

    _startRecording() {
      this._seconds = 0;
      this._finalSegments = [];
      this._highlightPending = false;
      this._qMarked = false;
      this._arousalMarked = false;
      this._arousalCooldownUntil = 0;
      if (this._arousalReleaseTimer) {
        clearTimeout(this._arousalReleaseTimer);
        this._arousalReleaseTimer = null;
      }
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

      /* Desktop-only: hold Q to mark current phrase for highlight */
      this._onKeyDown = (e) => {
        if (e.key !== 'q' && e.key !== 'Q') return;
        this._qMarked = true;
        this._highlightPending = true;
        this._elevationCard.classList.remove('mw-hidden');
        this._notifyBangleElevation();
        this._renderTranscript(this._currentInterim || '');
      };
      this._onKeyUp = (e) => {
        if (e.key !== 'q' && e.key !== 'Q') return;
        this._highlightPending = false;
        this._renderTranscript(this._currentInterim || '');
      };
      document.addEventListener('keydown', this._onKeyDown);
      document.addEventListener('keyup',   this._onKeyUp);

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
            this._startAudioArousalMonitor(stream);
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
              this._finalSegments.push({ text: t + ' ', highlighted: this._qMarked || this._arousalMarked });
              this._qMarked = false;
              this._arousalMarked = false;
              this._highlightPending = false;
              if (this._arousalReleaseTimer) {
                clearTimeout(this._arousalReleaseTimer);
                this._arousalReleaseTimer = null;
              }
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

      this._stopAudioArousalMonitor();
      if (this._arousalReleaseTimer) {
        clearTimeout(this._arousalReleaseTimer);
        this._arousalReleaseTimer = null;
      }
      if (this._onKeyDown) {
        document.removeEventListener('keydown', this._onKeyDown);
        document.removeEventListener('keyup',   this._onKeyUp);
        this._onKeyDown = null;
        this._onKeyUp   = null;
      }
      this._highlightPending = false;
      this._qMarked = false;
      this._arousalMarked = false;
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
      overlay.className = 'mw-confirm-overlay';

      const box = document.createElement('div');
      box.className = 'mw-confirm-box';

      const title = document.createElement('p');
      title.className = 'mw-confirm-title';
      title.textContent = 'Save this meeting?';

      const sub = document.createElement('p');
      sub.className = 'mw-confirm-sub';
      sub.textContent = `"${meetingName}" will be transcribed and analysed.`;

      const btnRow = document.createElement('div');
      btnRow.className = 'mw-confirm-actions';

      const discardBtn = document.createElement('button');
      discardBtn.className = 'mw-confirm-discard';
      discardBtn.textContent = 'Discard';

      const saveBtn = document.createElement('button');
      saveBtn.className = 'mw-confirm-save';
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
        const cls = this._highlightPending || this._qMarked || this._arousalMarked
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

