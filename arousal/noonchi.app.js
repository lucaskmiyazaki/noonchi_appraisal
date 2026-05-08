const Storage = require("Storage");

const STATE_FILE = "noonchi.state.json";
const W = g.getWidth();
const H = g.getHeight();

function defaultState() {
  return {
    active: false,
    enabled: {
      "Communication Difference": true,
      "Elevation": true,
      "Tone Difference": true,
      "Unclear Intent": true
    }
  };
}

function loadState() {
  return Storage.readJSON(STATE_FILE, true) || defaultState();
}

function saveState(state) {
  Storage.writeJSON(STATE_FILE, state);
}

let state = loadState();

const COLORS = {
  lightBg: "#F2F2F2",
  darkBg: "#111111",
  white: "#FFFFFF",
  black: "#000000",
  gray: "#888888",
  border: "#222222",
  green: "#A6E542",
  orange: "#FFBE2E",
  blue: "#7DC8FF",
  pink: "#E85AA4",
  yellow: "#FFE53B",
  purple: "#4B3CE8"
};

function isDark() {
  return g.theme.dark;
}

function bg() {
  return isDark() ? "#17171C" : "#F3F3F3";
}

function fg() {
  return isDark() ? "#FFFFFF" : "#111111";
}

function muted() {
  return isDark() ? "#BEBEBE" : "#666666";
}

function clearScreen() {
  g.setBgColor(bg());
  g.clear();
  g.setColor(fg());
}

function drawLogo(x, y, s) {
  s = s || 1;
  g.setColor(COLORS.yellow);
  g.fillPoly([
    x, y + 10 * s,
    x + 6 * s, y,
    x + 12 * s, y + 12 * s,
    x + 3 * s, y + 15 * s
  ]);
  g.setColor(COLORS.purple);
  g.fillPoly([
    x + 6 * s, y,
    x + 14 * s, y + 1 * s,
    x + 16 * s, y + 13 * s,
    x + 12 * s, y + 12 * s
  ]);
}

function drawHeader() {
  drawLogo(8, 8, 1);
  g.setColor(fg());
  g.setFontAlign(-1, 0);
  g.setFont("Vector", 16);
  g.drawString("Noonchi", 30, 16);
}

function drawSwitch(on) {
  const x = 38, y = 34, w = 100, h = 40;
  const r = h / 2;

  g.setFont("6x8", 1);
  g.setColor(muted());
  g.setFontAlign(1, 0);
  g.drawString("OFF", x - 8, y + h / 2);
  g.setFontAlign(-1, 0);
  g.drawString("ON", x + w + 8, y + h / 2);

  g.setColor(on ? (isDark() ? "#FFFFFF" : "#111111") : (isDark() ? "#24242C" : "#E7E7E7"));
  g.fillCircle(x + r, y + r, r);
  g.fillCircle(x + w - r, y + r, r);
  g.fillRect(x + r, y, x + w - r, y + h);

  g.setColor(on ? (isDark() ? "#17171C" : "#FFFFFF") : (isDark() ? "#3A3A44" : "#FFFFFF"));
  const knobX = on ? (x + w - r) : (x + r);
  g.fillCircle(knobX, y + r, r - 4);

  return {x:x, y:y, w:w, h:h};
}

function drawNudgeCard(y, title, subtitle, color, enabled) {
  const x = 10;
  const w = W - 20;
  const h = 28;

  g.setColor(isDark() ? "#1D1D24" : "#FFFFFF");
  g.fillRect(x, y, x + w, y + h);
  g.setColor(enabled ? fg() : muted());
  g.drawRect(x, y, x + w, y + h);

  g.setColor(color);
  g.fillCircle(x + 11, y + 14, 8);

  g.setColor("#111111");
  g.fillCircle(x + 11, y + 14, 2);

  g.setColor(enabled ? fg() : muted());
  g.setFontAlign(-1, -1);
  g.setFont("6x8", 1);
  g.drawString(title, x + 24, y + 5);

  g.setColor(muted());
  g.drawString(subtitle, x + 24, y + 16);

  if (enabled) {
    g.setColor(color);
    g.fillCircle(x + w - 8, y + 14, 3);
  }

  return {x:x, y:y, w:w, h:h};
}

let switchBox;
let buttonBoxes = [];

function drawApp() {
  clearScreen();
  drawHeader();

  switchBox = drawSwitch(state.active);

  g.setColor(fg());
  g.setFontAlign(-1, 0);
  g.setFont("Vector", 12);
  g.drawString("Nudges Active", 10, 84);

  buttonBoxes = [];
  buttonBoxes.push({
    key: "Communication Difference",
    box: drawNudgeCard(94, "Communication Difference", "Different communication styles.", COLORS.green, state.enabled["Communication Difference"])
  });
  buttonBoxes.push({
    key: "Elevation",
    box: drawNudgeCard(126, "Elevation", "You might want to slow down.", COLORS.orange, state.enabled["Elevation"])
  });
  buttonBoxes.push({
    key: "Tone Difference",
    box: drawNudgeCard(158, "Tone Difference", "Your tone may need clarity.", COLORS.blue, state.enabled["Tone Difference"])
  });

  // Because the screen is small, this 4th card is scroll-like but still fits tightly
  // We draw it at the bottom edge.
  buttonBoxes.push({
    key: "Unclear Intent",
    box: drawNudgeCard(190, "Unclear Intent", "What you said may not be clear.", COLORS.pink, state.enabled["Unclear Intent"])
  });
}

function inside(p, r) {
  return p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h;
}

function showActivatedSplash() {
  g.setBgColor("#111111");
  g.clear();
  drawLogo(W / 2 - 14, H / 2 - 20, 2);
  g.setColor("#FFFFFF");
  g.setFontAlign(0, 0);
  g.setFont("Vector", 18);
  g.drawString("Noonchi", W / 2, H / 2 + 18);
  setTimeout(function() {
    load();
  }, 1400);
}

function onTouch(zone, e) {
  if (inside(e, switchBox)) {
    state.active = !state.active;
    saveState(state);

    if (WIDGETS && WIDGETS.noonchi) {
      Bangle.drawWidgets();
    }

    if (state.active) {
      showActivatedSplash();
    } else {
      drawApp();
    }
    return;
  }

  for (let i = 0; i < buttonBoxes.length; i++) {
    if (inside(e, buttonBoxes[i].box)) {
      const key = buttonBoxes[i].key;
      state.enabled[key] = !state.enabled[key];
      saveState(state);
      drawApp();
      return;
    }
  }
}

Bangle.loadWidgets();
Bangle.drawWidgets();

Bangle.setUI({
  mode: "custom",
  touch: onTouch,
  btn: function() { load(); }
});

drawApp();