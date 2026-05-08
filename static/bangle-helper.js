(function () {
  'use strict';

  const UART_SERVICE = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
  const UART_RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';

  let device = null;
  let server = null;
  let service = null;
  let rxChar = null;
  let connectPromise = null;
  const MAX_BLE_CHUNK = 18;

  function emitConnectionStatus(connected) {
    window.dispatchEvent(new CustomEvent('bangle:connection', {
      detail: { connected: !!connected }
    }));
  }

  function clearConnectionState() {
    server = null;
    service = null;
    rxChar = null;
    emitConnectionStatus(false);
  }

  async function connectToDevice(targetDevice) {
    if (!targetDevice) {
      throw new Error('No Bluetooth device provided');
    }

    device = targetDevice;
    if (!device._mwDisconnectHandlerInstalled) {
      device.addEventListener('gattserverdisconnected', () => {
        clearConnectionState();
      });
      device._mwDisconnectHandlerInstalled = true;
    }

    server = await device.gatt.connect();
    service = await server.getPrimaryService(UART_SERVICE);
    rxChar = await service.getCharacteristic(UART_RX);
    emitConnectionStatus(true);
    return rxChar;
  }

  async function tryAutoConnectBangle() {
    if (!navigator.bluetooth || typeof navigator.bluetooth.getDevices !== 'function') {
      return null;
    }

    const devices = await navigator.bluetooth.getDevices();
    if (!devices || !devices.length) {
      return null;
    }

    for (let i = 0; i < devices.length; i++) {
      const candidate = devices[i];
      try {
        await connectToDevice(candidate);
        return candidate;
      } catch (_) {
        clearConnectionState();
      }
    }

    return null;
  }

  async function ensureConnected(allowPrompt) {
    if (rxChar) {
      return rxChar;
    }

    if (!navigator.bluetooth) {
      throw new Error('Web Bluetooth is not supported in this browser');
    }

    if (connectPromise) {
      return connectPromise;
    }

    connectPromise = (async function connectFlow() {
      if (device) {
        try {
          return await connectToDevice(device);
        } catch (_) {
          clearConnectionState();
        }
      }

      const autoConnected = await tryAutoConnectBangle();
      if (autoConnected && rxChar) {
        return rxChar;
      }

      if (!allowPrompt) {
        throw new Error('No authorized Bangle device available for auto-connect');
      }

      const selected = await navigator.bluetooth.requestDevice({
        filters: [{ services: [UART_SERVICE] }],
        optionalServices: [UART_SERVICE]
      });

      return connectToDevice(selected);
    })();

    try {
      return await connectPromise;
    } finally {
      connectPromise = null;
    }
  }

  async function writeLineToBangle(characteristic, line) {
    const text = String(line || '');
    for (let offset = 0; offset < text.length; offset += MAX_BLE_CHUNK) {
      const chunk = text.slice(offset, offset + MAX_BLE_CHUNK);
      const bytes = new TextEncoder().encode(chunk);
      await characteristic.writeValue(bytes);
    }
  }

  function normalizeOutgoingMessage(message) {
    if (message && typeof message === 'object') {
      return {
        trigger_key: message.trigger_key || '',
        type: message.type || 'Elevation',
        message: message.message || 'Elevation detected from meeting widget',
        speaker: message.speaker || '',
        force_vibrate: Boolean(message.force_vibrate)
      };
    }

    return {
      type: 'Elevation',
      message: String(message || 'Elevation detected from meeting widget'),
      speaker: '',
      force_vibrate: true
    };
  }

  function buildEspruinoCommand(payload) {
    const msg = String(payload.message || payload.type || 'Noonchi');
    const speaker = String(payload.speaker || '').trim();
    const fullMessage = speaker ? `${speaker}: ${msg}` : msg;

    function resolveTheme(input) {
      const raw = String(input || '').trim().toLowerCase();
      const key = raw
        .replace(/\s+/g, '_')
        .replace(/[^a-z_]/g, '');
      if (key === 'tone_difference') return 'tone_difference';
      if (key === 'unclear_intent') return 'unclear_intent';
      if (key === 'excellent_tone') return 'excellent_tone';
      if (key === 'need_for_clarification') return 'need_for_clarification';
      if (key === 'elevation') return 'elevation';
      return '';
    }

    const triggerKey = resolveTheme(payload.trigger_key) || resolveTheme(payload.type) || 'elevation';
    const typeLabel = String(payload.type || 'Elevation').trim() || 'Elevation';
    const messageLabel = fullMessage;

    const command = [
      '(function(){',
      'try{',
      `var k=${JSON.stringify(triggerKey)};`,
      `var title=${JSON.stringify(typeLabel)};`,
      `var message=${JSON.stringify(messageLabel)};`,
      'var W=g.getWidth(),H=g.getHeight;',
      'function wrap(t,m){var w=t.split(" "),l=[],c="";for(var i=0;i<w.length;i++){var n=(c+" "+w[i]).trim();if(n.length>m){if(c)l.push(c);c=w[i];}else c=n;}if(c)l.push(c);return l;}',
      'function buzz(kind){if(kind==="elevation")return Bangle.buzz(120).then(()=>Bangle.buzz(120));if(kind==="tone_difference")return Bangle.buzz(220);if(kind==="unclear_intent")return Bangle.buzz(80).then(()=>Bangle.buzz(80)).then(()=>Bangle.buzz(80));if(kind==="excellent_tone")return Bangle.buzz(60);if(kind==="need_for_clarification")return Bangle.buzz(100).then(()=>Bangle.buzz(100));return Bangle.buzz(150);}',
      'var T={',
      'elevation:{bg:"#F6E53A",fg:"#111111",accent:"#FF5A1F",title:"Elevation"},',
      'tone_difference:{bg:"#8FD0F2",fg:"#111111",accent:"#2E73CC",title:"Tone Difference"},',
      'unclear_intent:{bg:"#D95A9C",fg:"#111111",accent:"#7A0B3B",title:"Unclear Intent"},',
      'excellent_tone:{bg:"#86EFAC",fg:"#111111",accent:"#16A34A",title:"Excellent"},',
      'need_for_clarification:{bg:"#93C5FD",fg:"#111111",accent:"#2563EB",title:"Clarification"}',
      '};',
      'var s=T[k]||T.elevation;',
      'g.setBgColor(s.bg);g.clear();g.setColor(s.fg);',
      'var cx=(W/2)|0,cy=50;',
      'if(k==="elevation"){g.setColor(s.accent);g.fillCircle(cx,cy,16);g.setColor("#1B6B49");g.fillPoly([cx+1,cy-18,cx+10,cy-24,cx+13,cy-20,cx+5,cy-14]);}',
      'else if(k==="tone_difference"){g.setColor(s.accent);g.fillCircle(cx,cy,16);g.setColor("#111111");g.fillCircle(cx,cy,3);}',
      'else if(k==="unclear_intent"){g.setColor(s.accent);g.fillCircle(cx,cy-6,5);g.fillCircle(cx-6,cy+2,5);g.fillCircle(cx+6,cy+2,5);g.fillCircle(cx-10,cy+10,5);g.fillCircle(cx,cy+10,5);g.fillCircle(cx+10,cy+10,5);g.fillCircle(cx-5,cy+18,5);g.fillCircle(cx+5,cy+18,5);}',
      'else if(k==="excellent_tone"){g.setColor(s.accent);g.fillCircle(cx,cy,16);g.setColor("#DCFCE7");g.fillPoly([cx-8,cy,cx-2,cy+6,cx+9,cy-5,cx+6,cy-8,cx-2,cy+1,cx-5,cy-2]);}',
      'else if(k==="need_for_clarification"){g.setColor(s.accent);g.fillCircle(cx,cy,16);g.setColor("#111111");g.fillPoly([cx,cy-10,cx+3,cy-3,cx+10,cy,cx+3,cy+3,cx,cy+10,cx-3,cy+3,cx-10,cy,cx-3,cy-3]);g.setColor("#DBEAFE");g.fillCircle(cx,cy,3);}',
      'else {g.setColor(s.accent);g.fillCircle(cx,cy,16);g.setColor("#111111");g.setFontAlign(0,0);g.setFont("6x8",2);g.drawString("?",cx,cy+1);}',
      'g.setColor(s.fg);g.setFontAlign(0,0);g.setFont("6x8",2);',
      'g.drawString((k==="excellent_tone"||k==="need_for_clarification")?s.title:(title||s.title),cx,98);',
      'g.setFont("6x8",1);',
      'var lines=wrap(message||"",24);',
      'for(var i=0;i<Math.min(lines.length,3);i++)g.drawString(lines[i],cx,124+i*10);',
      'buzz(k);',
      'setTimeout(function(){if(Bangle.showClock)Bangle.showClock();else load();},3500);',
      '}catch(e){Bangle.buzz(120);E.showMessage("Noonchi nudge");}',
      '})();\n'
    ].join('');

    return command;
  }

  async function sendSimpleMessageToBangle(message) {
    const characteristic = await ensureConnected(true);
    const payload = normalizeOutgoingMessage(message);
    const command = buildEspruinoCommand(payload);
    await writeLineToBangle(characteristic, command);
  }

  async function requestBanglePermissionAndConnect() {
    await ensureConnected(true);
  }

  async function autoConnectBangle() {
    try {
      await ensureConnected(false);
    } catch (_) {
      /* Keep disconnected; caller may explicitly request permission. */
    }
  }

  window.tryAutoConnectBangle = autoConnectBangle;
  window.requestBanglePermissionAndConnect = requestBanglePermissionAndConnect;
  window.sendSimpleMessageToBangle = sendSimpleMessageToBangle;
  window.isBangleConnected = function isBangleConnected() {
    return !!rxChar;
  };

  emitConnectionStatus(false);
})();
