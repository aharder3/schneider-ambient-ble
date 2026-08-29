#!/usr/bin/env python3
"""
WSC latency benchmark for macOS.

This script measures which part of Schneider/WSC BLE control is slow:
- scan
- connect
- direct zone write
- CCT/brightness with full Schneider preamble
- CCT/brightness with one shared session
- repeated writes while keeping one GATT connection open
- reconnect-per-command latency

It restores the original C2/C3/C6 values at the end when possible.

Run:
    python -u wsc_latency_test.py
"""

from __future__ import annotations

import asyncio
import statistics
import time
from pathlib import Path
from datetime import datetime

from bleak import BleakClient, BleakScanner

SERVICE = "b35d95c0-6a68-437e-abe7-0ebffd8e0661"

C2 = "b35d95c2-6a68-437e-abe7-0ebffd8e0661"
C3 = "b35d95c3-6a68-437e-abe7-0ebffd8e0661"
C6 = "b35d95c6-6a68-437e-abe7-0ebffd8e0661"
CE = "b35d95ce-6a68-437e-abe7-0ebffd8e0661"

SESSION_INIT = bytes([0xAF, 0x01])
MANUAL_BOTH = bytes([0x01, 0x00, 0x03, 0x00])

CCT_VALUES = [3000, 4000, 5000]
BRIGHTNESS_VALUES = [20, 50, 80]


def hx(data):
    return bytes(data).hex(" ")


def payload8(value: int) -> bytes:
    word = int(value).to_bytes(2, "big")
    return word * 4


class Log:
    def __init__(self):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = Path.cwd() / f"wsc-latency-{stamp}.log"
        self.fp = self.path.open("w", encoding="utf-8")

    def p(self, text=""):
        print(text, flush=True)
        self.fp.write(text + "\n")
        self.fp.flush()

    def close(self):
        self.fp.close()


async def timed(label, coro, log: Log):
    start = time.perf_counter()
    result = await coro
    elapsed = (time.perf_counter() - start) * 1000
    log.p(f"{label:<42} {elapsed:8.1f} ms")
    return result, elapsed


async def find_wsc(log):
    start = time.perf_counter()
    devices = await BleakScanner.discover(timeout=5, return_adv=True)
    elapsed = (time.perf_counter() - start) * 1000

    for _, result in devices.items():
        device, adv = result
        name = adv.local_name or device.name or ""
        services = {str(x).lower() for x in (adv.service_uuids or [])}
        if name.upper().startswith("WSC") or SERVICE in services:
            log.p(f"Scan/find WSC                              {elapsed:8.1f} ms")
            log.p(f"Found: {name or 'WSC'} [{device.address}]")
            return device

    raise RuntimeError("WSC not found")


async def write(client, uuid, payload):
    await client.write_gatt_char(uuid, payload, response=True)


async def full_cct(client, kelvin):
    await write(client, CE, SESSION_INIT)
    await write(client, C6, MANUAL_BOTH)
    await write(client, C2, payload8(kelvin))


async def full_brightness(client, pct):
    await write(client, CE, SESSION_INIT)
    await write(client, C6, MANUAL_BOTH)
    await write(client, C3, payload8(pct * 100))


async def direct_cct(client, kelvin):
    await write(client, C2, payload8(kelvin))


async def direct_brightness(client, pct):
    await write(client, C3, payload8(pct * 100))


def avg(values):
    return statistics.mean(values) if values else 0.0


async def main():
    log = Log()
    try:
        log.p("Schneider/WSC macOS latency benchmark")
        log.p(f"Log: {log.path}")
        log.p()

        device = await find_wsc(log)

        log.p()
        log.p("=" * 72)
        log.p("1. ONE CONNECTION - BASELINE")
        log.p("=" * 72)

        t0 = time.perf_counter()
        client = BleakClient(device, timeout=20)
        await client.connect()
        connect_ms = (time.perf_counter() - t0) * 1000
        log.p(f"Initial GATT connect                         {connect_ms:8.1f} ms")

        original_c2 = bytes(await client.read_gatt_char(C2))
        original_c3 = bytes(await client.read_gatt_char(C3))
        original_c6 = bytes(await client.read_gatt_char(C6))

        log.p(f"Original C2: {hx(original_c2)}")
        log.p(f"Original C3: {hx(original_c3)}")
        log.p(f"Original C6: {hx(original_c6)}")

        _, c6_write_ms = await timed(
            "Direct C6 zone write",
            write(client, C6, MANUAL_BOTH),
            log
        )

        log.p()
        log.p("=" * 72)
        log.p("2. FULL PREAMBLE ON EVERY CCT CHANGE")
        log.p("=" * 72)
        full_cct_times = []
        for kelvin in CCT_VALUES:
            _, ms = await timed(
                f"CE + C6 + C2 -> {kelvin} K",
                full_cct(client, kelvin),
                log
            )
            full_cct_times.append(ms)

        log.p()
        log.p("=" * 72)
        log.p("3. ONE PREAMBLE, THEN DIRECT CCT WRITES")
        log.p("=" * 72)

        _, init_ms = await timed(
            "Shared session init: CE + C6",
            asyncio.gather(
                asyncio.sleep(0)
            ),
            log
        )
        # Do the writes sequentially; the gather above only creates a visually
        # separate timing line without overlapping BLE operations.
        start = time.perf_counter()
        await write(client, CE, SESSION_INIT)
        await write(client, C6, MANUAL_BOTH)
        shared_init_real = (time.perf_counter() - start) * 1000
        log.p(f"Actual shared CE + C6                       {shared_init_real:8.1f} ms")

        direct_cct_times = []
        for kelvin in CCT_VALUES:
            _, ms = await timed(
                f"Direct C2 only -> {kelvin} K",
                direct_cct(client, kelvin),
                log
            )
            direct_cct_times.append(ms)

        c2_verify = bytes(await client.read_gatt_char(C2))
        log.p(f"C2 final readback: {hx(c2_verify)}")

        log.p()
        log.p("=" * 72)
        log.p("4. FULL PREAMBLE ON EVERY BRIGHTNESS CHANGE")
        log.p("=" * 72)
        full_brightness_times = []
        for pct in BRIGHTNESS_VALUES:
            _, ms = await timed(
                f"CE + C6 + C3 -> {pct} %",
                full_brightness(client, pct),
                log
            )
            full_brightness_times.append(ms)

        log.p()
        log.p("=" * 72)
        log.p("5. ONE PREAMBLE, THEN DIRECT BRIGHTNESS WRITES")
        log.p("=" * 72)

        start = time.perf_counter()
        await write(client, CE, SESSION_INIT)
        await write(client, C6, MANUAL_BOTH)
        shared_bri_init = (time.perf_counter() - start) * 1000
        log.p(f"Actual shared CE + C6                       {shared_bri_init:8.1f} ms")

        direct_brightness_times = []
        for pct in BRIGHTNESS_VALUES:
            _, ms = await timed(
                f"Direct C3 only -> {pct} %",
                direct_brightness(client, pct),
                log
            )
            direct_brightness_times.append(ms)

        c3_verify = bytes(await client.read_gatt_char(C3))
        log.p(f"C3 final readback: {hx(c3_verify)}")

        log.p()
        log.p("=" * 72)
        log.p("6. RESTORE ORIGINAL STATE")
        log.p("=" * 72)

        await write(client, CE, SESSION_INIT)
        await write(client, C6, MANUAL_BOTH)
        await write(client, C2, original_c2)
        await write(client, C3, original_c3)
        await write(client, C6, original_c6)
        log.p("Original C2/C3/C6 restored.")

        await client.disconnect()

        log.p()
        log.p("=" * 72)
        log.p("7. RECONNECT-PER-COMMAND")
        log.p("=" * 72)

        reconnect_total = []
        reconnect_connect = []
        reconnect_write = []

        for index, kelvin in enumerate(CCT_VALUES, 1):
            start_total = time.perf_counter()
            c = BleakClient(device, timeout=20)

            start = time.perf_counter()
            await c.connect()
            connect_part = (time.perf_counter() - start) * 1000

            start = time.perf_counter()
            await full_cct(c, kelvin)
            write_part = (time.perf_counter() - start) * 1000

            await c.disconnect()
            total = (time.perf_counter() - start_total) * 1000

            reconnect_connect.append(connect_part)
            reconnect_write.append(write_part)
            reconnect_total.append(total)

            log.p(
                f"Round {index}: connect={connect_part:.1f} ms, "
                f"command={write_part:.1f} ms, total={total:.1f} ms"
            )

        # Restore one last time.
        c = BleakClient(device, timeout=20)
        await c.connect()
        await write(c, CE, SESSION_INIT)
        await write(c, C6, MANUAL_BOTH)
        await write(c, C2, original_c2)
        await write(c, C3, original_c3)
        await write(c, C6, original_c6)
        await c.disconnect()

        log.p()
        log.p("=" * 72)
        log.p("SUMMARY")
        log.p("=" * 72)
        log.p(f"Initial connect:                         {connect_ms:8.1f} ms")
        log.p(f"Direct C6 write:                         {c6_write_ms:8.1f} ms")
        log.p(f"Average full CCT (CE+C6+C2):            {avg(full_cct_times):8.1f} ms")
        log.p(f"Average direct C2 on open connection:    {avg(direct_cct_times):8.1f} ms")
        log.p(f"Average full brightness (CE+C6+C3):      {avg(full_brightness_times):8.1f} ms")
        log.p(f"Average direct C3 on open connection:    {avg(direct_brightness_times):8.1f} ms")
        log.p(f"Average reconnect connect part:          {avg(reconnect_connect):8.1f} ms")
        log.p(f"Average reconnect command part:          {avg(reconnect_write):8.1f} ms")
        log.p(f"Average reconnect total:                 {avg(reconnect_total):8.1f} ms")
        log.p()
        log.p("If direct C2/C3 writes are accepted and much faster, HA can keep")
        log.p("one short-lived shared connection/session for slider bursts instead")
        log.p("of reconnecting and replaying CE+C6 for every slider movement.")
        log.p()
        log.p(f"Please send back: {log.path}")

    finally:
        log.close()


if __name__ == "__main__":
    asyncio.run(main())
