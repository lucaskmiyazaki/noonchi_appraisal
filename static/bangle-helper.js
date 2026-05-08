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
    const buzzMs = payload.force_vibrate ? 220 : 140;
    return `Bangle.buzz(${buzzMs});E.showMessage(${JSON.stringify(fullMessage)});\n`;
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

  async function autoConnectBangleOnLoad() {
    try {
      await ensureConnected(false);
    } catch (_) {
      try {
        await ensureConnected(true);
      } catch (_) {
        /* User may dismiss chooser; keep status as disconnected. */
      }
    }
  }

  window.tryAutoConnectBangle = autoConnectBangleOnLoad;
  window.requestBanglePermissionAndConnect = requestBanglePermissionAndConnect;
  window.sendSimpleMessageToBangle = sendSimpleMessageToBangle;
  window.isBangleConnected = function isBangleConnected() {
    return !!rxChar;
  };

  emitConnectionStatus(false);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoConnectBangleOnLoad, { once: true });
  } else {
    autoConnectBangleOnLoad();
  }
})();
