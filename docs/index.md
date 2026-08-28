# Schneider Ambient BLE

Experimental Home Assistant integration for Schneider Ambient Lighting / WSC mirror cabinets over BLE.

Current integration version: **0.1.5**.

## Recommended setup

Use an ESP32 running ESPHome as a connectable Bluetooth Proxy and install the Home Assistant custom integration through HACS.

## First authorization

The captured app flow is **connect first, physical button second**. After the GATT connection is established, the app polls C6 roughly every 0.5 seconds. Before the physical button press, C6 reports `01 00 03 00 00 00 00 00`; after the press it reports `01 55 03 00 00 00 00 00`. Home Assistant version 0.1.5 mirrors this behavior and advances automatically on the `0x55` marker.

See [Pairing / first authorization](pairing.md) and [Protocol notes](protocol.md).
