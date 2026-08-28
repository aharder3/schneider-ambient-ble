"""Direct macOS verification tool for Schneider/WSC color temperature.

Requires: python3 -m pip install bleak
Usage: python -u tools/wsc_cct_mac.py 3000
"""
from __future__ import annotations

import asyncio
import sys
from bleak import BleakClient, BleakScanner

SERVICE = "b35d95c0-6a68-437e-abe7-0ebffd8e0661"
C2 = "b35d95c2-6a68-437e-abe7-0ebffd8e0661"
C6 = "b35d95c6-6a68-437e-abe7-0ebffd8e0661"
CE = "b35d95ce-6a68-437e-abe7-0ebffd8e0661"


def hx(data: bytes | bytearray) -> str:
    return bytes(data).hex(" ")


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -u tools/wsc_cct_mac.py <2000..6500>")
    kelvin = int(sys.argv[1])
    if not 2000 <= kelvin <= 6500:
        raise SystemExit("Kelvin must be between 2000 and 6500")

    found = await BleakScanner.discover(timeout=10, return_adv=True)
    target = None
    for _, result in found.items():
        device, adv = result
        name = adv.local_name or device.name or ""
        uuids = {str(x).lower() for x in (adv.service_uuids or [])}
        if name.upper().startswith("WSC") or SERVICE in uuids:
            target = device
            break
    if target is None:
        raise SystemExit("WSC not found")

    async with BleakClient(target, timeout=20) as client:
        current = bytes(await client.read_gatt_char(C2))
        if len(current) < 2 or len(current) % 2:
            raise RuntimeError(f"Unexpected C2 length: {len(current)}")
        encoded = kelvin.to_bytes(2, "big")
        payload = encoded * (len(current) // 2)
        print(f"Current C2: {hx(current)}", flush=True)
        print(f"Target C2:  {hx(payload)}", flush=True)
        await client.write_gatt_char(CE, bytes([0xAF, 0x01]), response=True)
        await client.write_gatt_char(C6, bytes([0x01, 0x00, 0x03, 0x00]), response=True)
        await client.write_gatt_char(C2, payload, response=True)
        readback = bytes(await client.read_gatt_char(C2))
        print(f"Read-back:  {hx(readback)}", flush=True)
        if readback != payload:
            raise RuntimeError("Read-back differs from requested payload")
        print(f"SUCCESS: {kelvin} K", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
