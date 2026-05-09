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

  // Send data to Bangle over BLE UART.  Uses Write-Without-Response when available
  // (much faster than Write-With-Response).  A small periodic pause yields to the
  // BLE stack so the Espruino UART buffer is never overwhelmed.
  async function writeLineToBangle(characteristic, line) {
    const text = String(line || '');
    const useNoRsp = (typeof characteristic.writeValueWithoutResponse === 'function');
    const enc = new TextEncoder();
    for (let offset = 0; offset < text.length; offset += MAX_BLE_CHUNK) {
      const chunk = text.slice(offset, offset + MAX_BLE_CHUNK);
      const bytes = enc.encode(chunk);
      if (useNoRsp) {
        await characteristic.writeValueWithoutResponse(bytes);
      } else {
        await characteristic.writeValue(bytes);
      }
      // Pace every ~180 bytes to give Espruino time to drain its buffer
      if (offset > 0 && (offset / MAX_BLE_CHUNK) % 10 === 0) {
        await new Promise(r => setTimeout(r, 8));
      }
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

  // Pixel-faithful 2bpp (4-colour indexed) icon images, rasterised directly from the
  // SVG source via resvg-js.  Each entry: { w, h, b64 (base64 pixel bytes), pal (RGB565
  // palette as comma-separated ints), dy (half-height for vertical centring at cy=50) }.
  const BANGLE_ICONS = {
    elevation: {
      w: 32, h: 43,
      b64: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAqqoAAAAAAAKqqgAAAAAACqqoAAAAAAAqqqgAAAAAACqqoAAAAAAAqqqgAAAAAACqqoAAAAAAAqqqAAAAAABVWoAAAAAAFVVVQAAAAAFVVVVUAAAAFVVVVVVAAABVVVVVVVAAAVVVVVVVVAAFVVVVVVVVABVVVVVVVVUAFVVVVVVVVUBVVVVVVVVVUFVVVVVVVVVQVVVVVVVVVVFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVBVVVVVVVVVUFVVVVVVVVVQFVVVVVVVVUAVVVVVVVVVQAVVVVVVVVUAAVVVVVVVVAAAVVVVVVVQAAAVVVVVVUAAAAVVVVVVAAAAAFVVVVAAAAAAAVVUAAAA=',
      pal: '65535,64195,6791,65535', dy: 21
    },
    tone_difference: {
      w: 32, h: 32,
      b64: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAoAAAAAAAAAKoAAAAAAAACaoAAAAAAAAlagAAAAAAAJVqgAAAAAACVVqAAAAAAAlVWqAAAAAAJVVaoAAAAACVVVagAAAAAlVVVqAAAAAJVVVWoAAAACVVVVagAAAAlVVVVqAAAAJVVVVWoAAACVVVVVqgAAAlVVVVWqAAAJVVVVVagAACVVVVVWqAAAlVVVVVagAAJVVVVVWqAACVVVVVVqgAAqVVVVVaoAACqlVVVaqgAACqpVVaqgAAACqqqqqoAAAAAqqqqoAAAAAAKqqoAAAA==',
      pal: '65535,57898,28109,65535', dy: 16
    },
    unclear_intent: {
      w: 32, h: 40,
      b64: 'ABVQAAAVUAAAFVVAAVVQAAAFVVAFVVAAAAVVUBVVUAAABVVUFVVQAAAFVVRVVVAAAAFVVVVVQAAAAVVVVVUAAAAAVVVVVAAAAAAFVVVAAAAAEAAVVAAEAAaqABqkAKqQGqqAqqoCqqQqqqGqqkqqqKqqpqqqmqqqqqqqqqqqqqqqqqqqqqqqqmqqpqqqmqqpKqqhqqpKqqgaqoCqqgKqpAaqqmqpqqqAAAKqpBqqgAAACqqoKqqgAAAKqqlqqqAAABqqqqqqpAAAGqqqqqqkAAAaqqqqqqQAAAqqqWqqoAAABqqoKqqQAAABqqVaqkAAAAAVaqlUAAAAAACqqgAAAAAAAqqqgAAAAAACqqqAAAAAAAKqqoAAAAAAAqqqgAAAAAACqqqAAAAAAAGqqkAAAAAAAGqpAAAAAAAACpAAAAA=',
      pal: '65535,18674,26971,65535', dy: 20
    },
    excellent_tone: {
      w: 32, h: 32,
      b64: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACVpWAAAAAAAVWlVAAAAAAFVaVVAAAAABVVpVVAAAAAlVWlVWAAAABVVaVVUAAAAFVVpVVQAAAAVVWlVVAAAABVVaVVUAAAAFVVpVVQAAAAVVWlVVAAAACVVaVVYAAAABVVpVVAAAAAFVWlVUAAAAAFVaVVAAAAAAlVpVYAAAAAAVWlVAAAAAAAVaVQAAAAAACVpWAAAAAAACWlgAAAAAAAAaQAAAAAAAAAoAAAAAAAAACgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==',
      pal: '65535,5385,49082,65535', dy: 16
    },
    need_for_clarification: {
      w: 32, h: 32,
      b64: 'AAABVVVAAAAAABVVVVQAAAABVVVVVUAAAAVVVVVVUAAAFVVVVVVUAABVVVVVVVUAAVVVVVVVVUAFVVVVVVVVUAVVVVVVVVVQFVVVVVVVVVQVVVVVVVVVVFVVVVaVVVVVVVVVVpVVVVVVVVWqqlVVVVVVVaqqVVVVVVVVqqpVVVVVVVaqqpVVVVVVVaqqVVVVVVVVaqlVVVVVVVVqqVVVVVVVVVVVVVVVFVVVVVVVVVQVVVVVVVVVVAVVVVVVVVVQBVVVVVVVVVABVVVVVVVVQABVVVVVVVUAABVVVVVVVAAABVVVVVVQAAABVVVVVUAAAAAVVVVUAAAAAAFVVUAAAA==',
      pal: '65535,11095,6339,65535', dy: 16
    }
  };

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

    // Select the pre-rasterised icon data for this trigger
    const img = BANGLE_ICONS[triggerKey] || BANGLE_ICONS.elevation;

    const command = [
      '(function(){',
      'try{',
      `var k=${JSON.stringify(triggerKey)};`,
      `var title=${JSON.stringify(typeLabel)};`,
      `var message=${JSON.stringify(messageLabel)};`,
      'var W=g.getWidth(),H=g.getHeight();',
      'function wrap(t,m){var w=t.split(" "),l=[],c="";for(var i=0;i<w.length;i++){var n=(c+" "+w[i]).trim();if(n.length>m){if(c)l.push(c);c=w[i];}else c=n;}if(c)l.push(c);return l;}',
      'function buzz(kind){if(kind==="elevation")return Bangle.buzz(120).then(function(){return Bangle.buzz(120);});if(kind==="tone_difference")return Bangle.buzz(220);if(kind==="unclear_intent")return Bangle.buzz(80).then(function(){return Bangle.buzz(80);}).then(function(){return Bangle.buzz(80);});if(kind==="excellent_tone")return Bangle.buzz(60);if(kind==="need_for_clarification")return Bangle.buzz(100).then(function(){return Bangle.buzz(100);});return Bangle.buzz(150);}',
      'var T={',
      'elevation:{bg:"#FFFFFF",fg:"#111111",title:"Elevation"},',
      'tone_difference:{bg:"#FFFFFF",fg:"#111111",title:"Tone Difference"},',
      'unclear_intent:{bg:"#FFFFFF",fg:"#111111",title:"Unclear Intent"},',
      'excellent_tone:{bg:"#FFFFFF",fg:"#111111",title:"Excellent"},',
      'need_for_clarification:{bg:"#FFFFFF",fg:"#111111",title:"Clarification"}',
      '};',
      'var s=T[k]||T.elevation;',
      'g.setBgColor(s.bg);g.clear();',
      'var cx=(W/2)|0,cy=50;',
      // Embed the 2bpp pixel-faithful icon for this trigger
      `var I={width:${img.w},height:${img.h},bpp:2,buffer:atob("${img.b64}"),palette:new Uint16Array([${img.pal}])};`,
      `g.drawImage(I,cx-16,cy-${img.dy});`,
      'g.setColor(s.fg);g.setFontAlign(0,0);g.setFont("6x8",2);',
      // tone_difference: two-line label ("Tone" / "Difference")
      // need_for_clarification: always show "Clarification"
      ...(triggerKey === 'tone_difference'
        ? ['g.drawString("Tone",cx,91);', 'g.drawString("Difference",cx,107);']
        : [`g.drawString(${JSON.stringify(triggerKey === 'need_for_clarification' ? 'Clarification' : typeLabel)}||s.title,cx,98);`]),
      'g.setFont("6x8",1);',
      'var lines=wrap(message||"",24);',
      'for(var i=0;i<Math.min(lines.length,3);i++)g.drawString(lines[i],cx,124+i*10);',
      'buzz(k);',
      'setTimeout(function(){if(Bangle.showClock)Bangle.showClock();else load();},5000);',
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
