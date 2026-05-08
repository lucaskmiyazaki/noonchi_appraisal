(function() {
  if (global.NOONCHI_BOOT_INSTALLED) return;
  global.NOONCHI_BOOT_INSTALLED = true;

  const Storage = require("Storage");
  const STATE_FILE = "noonchi.state.json";
  const EVENT_FILE = "noonchi.event.json";

  let buffer = "";

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

  function normalizeType(t) {
    if (!t) return "Communication Difference";
    if (t === "Communication Balance") return "Communication Difference";
    if (t === "Communication Variations") return "Communication Difference";
    return t;
  }

  function saveEvent(type, message, speaker) {
    Storage.writeJSON(EVENT_FILE, {
      type: type,
      message: message || "",
      speaker: speaker || "",
      ts: Date.now()
    });
  }

  function shouldShow(type, state) {
    if (!state.active) return false;
    if (!state.enabled) return false;
    return !!state.enabled[type];
  }

  function handleLine(line) {
    let obj;
    try {
      obj = JSON.parse(line);
    } catch (e) {
      obj = { type: "Communication Difference", message: line, speaker: "" };
    }

    const type = normalizeType(obj.type);
    const message = obj.message || "";
    const speaker = obj.speaker || "";
    const forceVibrate = !!obj.force_vibrate;

    if (forceVibrate) {
      try { Bangle.buzz(160); } catch (_) {}
      saveEvent(type, message, speaker);
      load("noonchinudge.app.js");
      return;
    }

    const state = loadState();

    if (!shouldShow(type, state)) {
      return;
    }

    saveEvent(type, message, speaker);
    load("noonchinudge.app.js");
  }

  Bluetooth.on("data", function(d) {
    buffer += d;
    let idx;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      let line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (line.length) handleLine(line);
    }
  });
})();