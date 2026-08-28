# Schneider Ambient BLE

Experimental local Home Assistant integration for Schneider Ambient Lighting / WSC mirrors and mirror cabinets over Bluetooth Low Energy.

[![Open your Home Assistant instance and open HACS repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aharder3&repository=schneider-ambient-ble&category=integration)

## Quick start

1. Flash an ESP32 with the included ESPHome Bluetooth Proxy example.
2. Add this repository to HACS as a custom **Integration**.
3. Install **Schneider Ambient BLE** and restart Home Assistant.
4. Open **Settings → Devices & services** and look for Bluetooth discovery.

Repository: https://github.com/aharder3/schneider-ambient-ble

## Project status

Brightness and color temperature have been decoded. Power/zone behavior and pairing/bonding are experimental.

## Privacy

Do not publish raw PacketLogger captures, credentials, network addresses or real Bluetooth MAC addresses.

## Disclaimer

Independent community project. Not affiliated with or endorsed by Schneider or W. Schneider+Co AG.
