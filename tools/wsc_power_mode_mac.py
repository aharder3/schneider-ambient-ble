"""Direct macOS verification helper for Schneider/WSC C6 mode writes.

Usage inside a venv with bleak installed:
  python -u tools/wsc_power_mode_mac.py manual
  python -u tools/wsc_power_mode_mac.py auto
  python -u tools/wsc_power_mode_mac.py nightlight
  python -u tools/wsc_power_mode_mac.py off

No real device identifier is embedded in this script.
"""

from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient, BleakScanner

SERVICE = "b35d95c0-6a68-437e-abe7-0ebffd8e0661"
C6 = "b35d95c6-6a68-437e-abe7-0ebffd8e0661"
CE = "b35d95ce-6a68-437e-abe7-0ebffd8e0661"

SESSION_INIT = bytes([0xAF, 0x01])
PAYLOADS = {
    "off": bytes([0x00, 0x00, 0x00, 0x00]),
    "nightlight": bytes([0x00, 0x00, 0x00, 0x02]),
    "manual": bytes([0x01, 0x00, 0x03, 0x00]),
    "auto": bytes([0x02, 0x00, 0x00, 0x03]),
}


def hx(data: bytes) -> str:
    return data.hex(" ")


async def find_wsc():
    found = await BleakScanner.discover(timeout=10, return_adv=True)
    for _, result in found.items():
        device, adv = result
        name = adv.local_name or device.name or ""
        services = {str(uuid).lower() for uuid in (adv.service_uuids or [])}
        if name.upper().startswith("WSC") or SERVICE in services:
            return device, name or "WSC"
    return None, None


async def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1].lower() not in PAYLOADS:
        print("Usage: python -u wsc_power_mode_mac.py off|manual|auto|nightlight")
        raise SystemExit(2)

    mode = sys.argv[1].lower()
    device, name = await find_wsc()
    if device is None:
        print("ERROR: WSC not found")
        return

    print(f"Found {name} [{device.address}]", flush=True)
    async with BleakClient(device, timeout=20) as client:
        before = bytes(await client.read_gatt_char(C6))
        print(f"C6 before: {hx(before)}", flush=True)
        print(f"Writing {mode}: {hx(PAYLOADS[mode])}", flush=True)
        await client.write_gatt_char(CE, SESSION_INIT, response=True)
        await client.write_gatt_char(C6, PAYLOADS[mode], response=True)
        after = bytes(await client.read_gatt_char(C6))
        print(f"C6 after:  {hx(after)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
