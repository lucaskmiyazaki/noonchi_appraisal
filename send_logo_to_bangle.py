#!/usr/bin/env python3
"""
Send the Noonchi logo to a Bangle.js 2 watch over BLE UART.

Requirements:
    pip install bleak

Usage:
    python3 send_logo_to_bangle.py [--address AA:BB:CC:DD:EE:FF]

If no address is given the script scans for the first device advertising
the Espruino/Bangle UART service and uses that.
"""

import asyncio
import argparse
import sys

from bleak import BleakClient, BleakScanner

# Nordic UART Service UUIDs
UART_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UART_RX_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # write (PC → watch)

# Max bytes per BLE write-without-response packet (safe for Espruino UART)
CHUNK_SIZE = 18
# Pause every N packets to let Espruino drain its input buffer
PACE_EVERY = 10
PACE_DELAY = 0.01  # seconds


# ---------------------------------------------------------------------------
# Noonchi logo — 48×45 px, RGB565 big-endian, composited on #fdf9f2 background
# Rasterised from static/images/logo.svg via @resvg/resvg-js
# ---------------------------------------------------------------------------
LOGO_B64 = (
    "/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3t4GSdn/3v/e/97/3v/e/97/3v/e/97/3v/e"
    "/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e"
    "/97/3v/e/97/3v/e/97/3t4GarVJuUm5SdqMFb23tXeD9Vp3SdpJ2km6SblJuUm5SblJuUm5"
    "SblJuUm5Yrb/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e"
    "/973nd4G3gZJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUn5"
    "/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97WB94G3gbNiUm5S"
    "blJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5Sbn/3v/e/97/3v/e"
    "/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97WB94G3gbeBkm5SblJuUm5SblJuUm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3v/e/97/3v/e"
    "/97/3v/e/97/3v/e/97/3v/e5vrWB94G3gbeBt4GSblJuUm5SblJuUm5SblJuf////9JuUm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuUm5/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e"
    "/97/3v/e1gfWB94G3gbeBt4Ge1JJuUm5SblJuUm5SblJuf////9JmUm5SblJuUm5SblJuUm5"
    "SblJuUm5SblJuUm5pRb/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e1gfWB94G"
    "3gbeBt4G3gZJuUm5SblJuUm5SblJuXM7rR1JuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5"
    "Sbn/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/97/3tYH1gfWB94G3gbeBt4G3gbeBkm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5Sbn/3v/e/97/3v/e"
    "/97/3v/e/97/3v/e/97/3v/e/97/3tYH1gfWB94G3gbeBt4G3gbeBknZSblJuUm5SblJuUm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5Sblitv/e/97/3v/e/97/3v/e/97/3v/e"
    "/97/3v/e/97eJtYH1gfWB94G3gbeBt4G3gbeBt4GSblJuUm5SblJuUm5SblJuUm5SblJuUm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJ2v/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e/77WB9YH"
    "1gfWB94G3gbeBt4G3gbeBt4GtMxJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5"
    "SblJuUm5SblJuf/e/97/3v/e/97/3v/e/97/3v/e/97/3v/e1gfWB9YH1gfWB94G3gbeBt4G"
    "3gbeBt4G3gZJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e"
    "/97/3v/e/97/3v/e/97/3v/e/97/3sX01gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBkm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3v/e"
    "/97/3v/e/97/3tYH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBmJ2SblJuUm5SblJuUm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3v/e/97/3v/e/97N6NYH"
    "1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4GSblJuUm5SblJuUm5SblJuUm5SblJuUm5"
    "SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3v/e/97/3v/e/97WB9YH1gfWB9YH1gfWB94G"
    "3gbeBt4G3gbeBt4G3gbeBt4GzahJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5"
    "SblJuf/e/97/3v/e/97/3v/e/97/3v/e3ibWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gZJukm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e"
    "/97/3v/e/97/3v/e1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBkm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3v/e/97/3tYH"
    "1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBouRSblJuUm5SblJuUm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3v/e/97OVtYH1gfWB9YH1gfWB9YH"
    "1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4GSblJuUm5SblJuUm5SblJuUm5SblJuUm5"
    "SblJuUm5SblJuf/e/97/3v/e/97/3v/e/97WB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G"
    "3gbeBt4G3gbeBt4G3gbeBt4G3gZJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e"
    "/97/3v/e/97/3v/excrWB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gZSGEm5SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3v/e"
    "1gfWB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBkm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3t4m1gfWB9YH1gfWB9YH"
    "1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBqysSblJuUm5SblJuUm5"
    "SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3tYH1gfWB9YH1gfWB9YH1gfWB9YH1gfWB94G"
    "3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4GSblJuUm5SblJuUm5SblJuUm5SblJuUm5"
    "SblJuf/e/97/3v/e/97e2dYH1gfWB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gbeBt4G3gbeBt4G3gZJuUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e"
    "/97N6NYH1gfWB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gZqtUm5SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97WJ9YH1gfWB9YH"
    "1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBkm5"
    "SblJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97WB9YH1gfWB9YH1gfWB9YH1gfWB9YH"
    "1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt3nSblJuUm5SblJuUm5"
    "SblJuUm5SblJuf/e/97/3v/e/97WB9YH1gfWB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G"
    "3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4GSdlJuUm5SblJuUm5SblJuUm5SblJuf/e"
    "/97/3v/e/97WB9YH1gfWB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gbeBt4G3gbeBt4G3gZJuUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97WJ9YH"
    "1gfWB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gakbUm5SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97N6dYH1gfWB9YH1gfWB9YH"
    "1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBkm5"
    "SblJuUm5SblJuUm5SblJuf/e/97/3v/e/97nG9YH1gfWB9YH1gfWB9YH1gfWB9YH1gfWB94G"
    "3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4GSblJuUm5SblJuUm5"
    "SblJuf/e/97/3v/e/97/3tYH1gfWB9YH1gfWB9YH1gfWB9YH1gfWB9YH3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4GYpZJuUm5SblJuUm5SblJuf/e/97/3v/e"
    "/97/3tYI1gfWB9YH1gfWB9YH1gfWB9YH1gfWB9YH3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gbeBt4G3gbeBt4G3gZJuUm5SblJuUm5SblJuf/e/97/3v/e/97/3v/e1gfWB9YH"
    "1gfWB9YH1gfWB9YH1gfWB9YH3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gbeBkm5SblJuUm5SblJuf/e/97/3v/e/97/3v/evbDWB9YH1gfWB9YH1gfWB9YH"
    "1gfWB9YH3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBqyNS"
    "blJuUm5SblJuf/e/97/3v/e/97/3v/e/97WB9YH1gfWB9YH1gfWB9YH1gfWB9YH1gfeBt4G3"
    "gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4GYnZJuUm5SblJub3X/97"
    "/3v/e/97/3v/e/97/3tYH1gfWB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gZR+Um5SblJuUm6/97/3v/e/97/3v/e/97/3v/e"
    "1ifWB9YH1gfWB9YH1gfWB9YH1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G"
    "3gbeBt4G3gbeBt4G3gbeBlo3SblJuUm5953/3v/e/97/3v/e/97/3v/e/97FytYH1gfWB9YH"
    "1gfWB9YH1gfWB9YH3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G"
    "3gbeBt4GrI1JuUm5Sbn/3v/e/97/3v/e/97/3v/e/97/3v/e3ibWB9YH1gfWB9YH1gfWB9YH"
    "1gfWB94G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBkm6S"
    "blJ2v/e/97/3v/e/97/3v/e/97/3v/e/97/3sX03ibWB9YH1gfWB9YH1gfWB9YH1ifeBt4G3"
    "gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gbeBt4G3gZJuXM1"
)
LOGO_W = 48
LOGO_H = 45


def build_espruino_command() -> str:
    """Return Espruino JS that draws the Noonchi logo centred on the watch screen."""
    return (
        "(function(){"
        "try{"
        "var W=g.getWidth(),H=g.getHeight();"
        "var bg=\"#fdf9f2\";"
        f"var img={{width:{LOGO_W},height:{LOGO_H},bpp:16,buffer:atob(\"{LOGO_B64}\")}};"
        "g.setBgColor(bg);g.clear();"
        "g.drawImage(img,(W/2|0)-(img.width/2|0),(H/2|0)-(img.height/2|0));"
        "g.setColor(\"#1c1b1f\");g.setFontAlign(0,0);g.setFont(\"6x8\",2);"
        "g.drawString(\"Noonchi\",(W/2|0),H/2+40|0);"
        "setTimeout(function(){if(Bangle.showClock)Bangle.showClock();else load();},5000);"
        "}catch(e){E.showMessage(\"Noonchi\");}"
        "})();\n"
    )


async def find_bangle() -> str:
    """Scan for a Bangle.js device by its UART service UUID."""
    print("Scanning for Bangle.js…")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: UART_SERVICE.lower() in [str(u).lower() for u in adv.service_uuids]
    )
    if device is None:
        raise RuntimeError(
            "No Bangle.js found nearby. "
            "Make sure it is awake and has BLE enabled, or pass --address manually."
        )
    print(f"Found: {device.name} [{device.address}]")
    return device.address


async def send(address: str) -> None:
    print(f"Connecting to {address}…")
    async with BleakClient(address) as client:
        print("Connected.")

        # Verify the UART RX characteristic is present
        chars = {str(c.uuid).lower(): c for s in client.services for c in s.characteristics}
        if UART_RX_CHAR not in chars:
            raise RuntimeError(
                f"UART RX characteristic ({UART_RX_CHAR}) not found on device."
            )
        rx = chars[UART_RX_CHAR]
        can_wr = "write-without-response" in rx.properties

        command = build_espruino_command()
        data = command.encode("utf-8")
        total = len(data)
        print(f"Sending {total} bytes ({(total // CHUNK_SIZE) + 1} packets)…")

        for i, offset in enumerate(range(0, total, CHUNK_SIZE)):
            chunk = data[offset: offset + CHUNK_SIZE]
            if can_wr:
                await client.write_gatt_char(rx, chunk, response=False)
            else:
                await client.write_gatt_char(rx, chunk, response=True)
            if i > 0 and i % PACE_EVERY == 0:
                await asyncio.sleep(PACE_DELAY)

        print("Done! Logo sent to watch.")


async def main(address: str | None) -> None:
    if address is None:
        address = await find_bangle()
    await send(address)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Noonchi logo to Bangle.js")
    parser.add_argument(
        "--address",
        metavar="AA:BB:CC:DD:EE:FF",
        help="BLE MAC address of the Bangle (skip scan)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.address))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
