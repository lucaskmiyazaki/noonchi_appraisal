(function() {
  const Storage = require("Storage");
  const STATE_FILE = "noonchi.state.json";

  function isActive() {
    const s = Storage.readJSON(STATE_FILE, true);
    return !!(s && s.active);
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

  WIDGETS.noonchi = {
    area: "tl",
    sortorder: -10,
    width: isActive() ? 18 : 0,
    draw: function() {
      if (!isActive()) {
        this.width = 0;
        return;
      }
      this.width = 18;
      g.reset();
      g.clearRect(this.x, this.y, this.x + 17, this.y + 23);
      drawLogo(this.x + 2, this.y + 5, 1);
    }
  };
})();