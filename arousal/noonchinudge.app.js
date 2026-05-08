const Storage = require("Storage");
const EVENT_FILE = "noonchi.event.json";
const W = g.getWidth();
const H = g.getHeight();

const event = Storage.readJSON(EVENT_FILE, true) || {
  type: "Communication Difference",
  message: "Different communication styles.",
  speaker: ""
};

function styleFor(type) {
  if (type === "Elevation") {
    return { bg:"#F6E53A", fg:"#111111", accent:"#FF5A1F" };
  }
  if (type === "Tone Difference") {
    return { bg:"#8FD0F2", fg:"#111111", accent:"#2E73CC" };
  }
  if (type === "Unclear Intent") {
    return { bg:"#D95A9C", fg:"#111111", accent:"#7A0B3B" };
  }
  return { bg:"#A8DB43", fg:"#111111", accent:"#39A052" };
}

function drawLogo(x, y, s) {
  g.setColor("#FFE53B");
  g.fillPoly([
    x, y + 8 * s,
    x + 5 * s, y,
    x + 10 * s, y + 9 * s,
    x + 2 * s, y + 12 * s
  ]);
  g.setColor("#4B3CE8");
  g.fillPoly([
    x + 5 * s, y,
    x + 12 * s, y + 1 * s,
    x + 13 * s, y + 10 * s,
    x + 10 * s, y + 9 * s
  ]);
}

function wrap(text, maxChars) {
  const words = text.split(" ");
  let lines = [];
  let line = "";
  for (let i = 0; i < words.length; i++) {
    const next = (line + " " + words[i]).trim();
    if (next.length > maxChars) {
      if (line) lines.push(line);
      line = words[i];
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function drawIcon(type, cx, cy) {
  if (type === "Elevation") {
    g.setColor("#FF5A1F");
    g.fillCircle(cx, cy, 16);
    g.setColor("#1B6B49");
    g.fillPoly([cx+1, cy-18, cx+10, cy-24, cx+13, cy-20, cx+5, cy-14]);
    return;
  }

  if (type === "Tone Difference") {
    g.setColor("#2E73CC");
    g.fillCircle(cx, cy, 16);
    g.setColor("#111111");
    g.fillCircle(cx, cy, 3);
    return;
  }

  if (type === "Unclear Intent") {
    g.setColor("#7A0B3B");
    g.fillCircle(cx, cy-6, 5);
    g.fillCircle(cx-6, cy+2, 5);
    g.fillCircle(cx+6, cy+2, 5);
    g.fillCircle(cx-10, cy+10, 5);
    g.fillCircle(cx, cy+10, 5);
    g.fillCircle(cx+10, cy+10, 5);
    g.fillCircle(cx-5, cy+18, 5);
    g.fillCircle(cx+5, cy+18, 5);
    g.setColor("#1B6B49");
    g.fillPoly([cx-2, cy-16, cx-10, cy-24, cx-2, cy-24, cx+1, cy-18]);
    g.fillPoly([cx+2, cy-16, cx+10, cy-24, cx+2, cy-24, cx-1, cy-18]);
    return;
  }

  // Communication Difference
  g.setColor("#39A052");
  g.fillPoly([cx-18, cy+8, cx+18, cy-10, cx+7, cy+18]);
  g.setColor("#F25D6B");
  g.fillPoly([cx-13, cy+7, cx+13, cy-6, cx+5, cy+13]);
  g.setColor("#111111");
  g.fillCircle(cx+1, cy+3, 2);
  g.fillCircle(cx+8, cy-1, 2);
}

function buzz(type) {
  if (type === "Elevation") {
    Bangle.buzz(120).then(() => Bangle.buzz(120));
  } else if (type === "Tone Difference") {
    Bangle.buzz(220);
  } else if (type === "Unclear Intent") {
    Bangle.buzz(80).then(() => Bangle.buzz(80)).then(() => Bangle.buzz(80));
  } else {
    Bangle.buzz(150);
  }
}

function drawScreen() {
  const s = styleFor(event.type);

  g.setBgColor(s.bg);
  g.clear();
  g.setColor(s.fg);

  drawLogo(6, 6, 1);

  drawIcon(event.type, W / 2, 52);

  g.setColor(s.fg);
  g.setFontAlign(0, 0);
  g.setFont("6x8", 3);

  let titleLines = wrap(event.type, 14);
  if (titleLines.length === 1) {
    g.drawString(titleLines[0], W / 2, 100);
  } else {
    g.drawString(titleLines[0], W / 2, 90);
    g.drawString(titleLines[1], W / 2, 112);
  }

  g.setFont("6x8", 1);
  let messageLines = wrap(event.message || "", 26);
  for (let i = 0; i < Math.min(messageLines.length, 3); i++) {
    g.drawString(messageLines[i], W / 2, 132 + i * 10);
  }

  buzz(event.type);

  setTimeout(function() {
    load();
  }, 3500);
}

drawScreen();