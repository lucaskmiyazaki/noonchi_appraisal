import asyncio
import json
import threading
from flask import Flask, request, jsonify
from bleak import BleakScanner, BleakClient

UART_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

app = Flask(__name__)


class BangleManager:
    def __init__(self):
        self.client = None
        self.device = None
        self.lock = asyncio.Lock()
        self.helpers_installed = False

    async def find_bangle(self, timeout=6.0):
        print("Scanning...")
        devices = await BleakScanner.discover(timeout=timeout)

        for d in devices:
            print(f"Found: name={d.name!r}, address={d.address}")

        for d in devices:
            name = d.name or ""
            if "Bangle.js" in name:
                return d
        return None

    async def send_line(self, code, pause=0.1):
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Bangle is not connected")

        if not code.endswith("\n"):
            code += "\n"

        await self.client.write_gatt_char(
            UART_RX_UUID,
            code.encode("utf-8"),
            response=False
        )
        await asyncio.sleep(pause)

    async def _connect_no_lock(self):
        if self.client and self.client.is_connected:
            return

        self.device = await self.find_bangle()
        if not self.device:
            raise RuntimeError("No Bangle.js found")

        self.client = BleakClient(self.device, timeout=30.0)

        print(f"Connecting to {self.device.name} ({self.device.address})...")
        await self.client.connect()
        print("Connected.")

        self.helpers_installed = False

        await self.send_line("echo(0);")
        await self.install_watch_helpers()
        await self.send_line("Bangle.buzz(200);")

    async def connect(self):
        async with self.lock:
            await self._connect_no_lock()

    async def disconnect(self):
        async with self.lock:
            try:
                if self.client and self.client.is_connected:
                    print("Disconnecting...")
                    await self.client.disconnect()
                    await asyncio.sleep(2.0)
            except Exception as e:
                print("Disconnect error:", repr(e))
            finally:
                self.client = None
                self.device = None
                self.helpers_installed = False

    async def ensure_connected(self):
        async with self.lock:
            if not self.client or not self.client.is_connected:
                print("Watch is disconnected. Reconnecting...")
                await self._connect_no_lock()

    async def install_watch_helpers(self):
        if self.helpers_installed:
            return

        lines = [
            'global.drawTip = function(txt) {',
            '  Bangle.setLCDPower(1);',
            '  g.clear();',
            '  g.setFont("6x8", 2);',
            '  g.setFontAlign(-1, -1);',
            '  var x = 10;',
            '  var y = 10;',
            '  var maxWidth = g.getWidth() - 20;',
            '  var lines = g.wrapString(txt, maxWidth);',
            '  for (var i = 0; i < lines.length; i++) {',
            '    g.drawString(lines[i], x, y + i * 18);',
            '  }',
            '};',
            'global.showTip = function(txt) {',
            '  Bangle.buzz(200);',
            '  drawTip(txt);',
            '};',
        ]

        for line in lines:
            await self.send_line(line, pause=0.12)

        self.helpers_installed = True
        print("Watch helpers installed.")

    async def show_tip(self, text):
        await self.ensure_connected()

        async with self.lock:
            safe_text = json.dumps(text)
            await self.send_line(f"showTip({safe_text});", pause=0.15)


manager = BangleManager()


class AsyncRunner:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def run_background(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self.loop)


runner = AsyncRunner()


@app.route("/health", methods=["GET"])
def health():
    connected = bool(manager.client and manager.client.is_connected)
    return jsonify({
        "ok": True,
        "bangle_connected": connected
    })


@app.route("/tips", methods=["POST"])
def tips():
    try:
        data = request.get_json(force=True)
        text = data.get("tip", "").strip()

        if not text:
            return jsonify({"ok": False, "error": "Missing 'tip'"}), 400

        runner.run(manager.show_tip(text))
        return jsonify({
            "ok": True,
            "tip": text,
            "bangle_connected": True
        })

    except Exception as e:
        return jsonify({"ok": False, "error": repr(e)}), 500


if __name__ == "__main__":
    try:
        print("Starting server...")

        # connect once on startup
        try:
            runner.run(manager.connect())
            print("Initial Bangle connection successful.")
        except Exception as e:
            print("Initial connection failed:", repr(e))
            print("Server will still start and reconnect on first /tips request.")

        app.run(host="0.0.0.0", port=5007, debug=False)

    finally:
        try:
            runner.run(manager.disconnect())
        except Exception:
            pass