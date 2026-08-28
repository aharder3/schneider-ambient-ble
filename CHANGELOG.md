# Changelog

## 0.1.3

- Reworked the complete manual setup order so the physical pairing/learn button is pressed **before** Home Assistant scans.
- Added a visible scan progress step instead of immediately aborting when no cached device is present.
- Added retry screens for both discovery and connection failures.
- Added a real connection test before creating the Home Assistant config entry.
- Replays the non-secret Schneider app initialization observed in PacketLogger: local date (`C4`), local time (`C5`) and `AF 01` (`CE`).
- Deliberately does **not** call standard BLE `pair()` because the capture contains no SMP pairing exchange or link-encryption event for WSC.
- Runtime writes now initialize each newly opened BLE session before sending the requested command.

## 0.1.2

- Added a physical pairing/learn-button prompt.
- Documented the PacketLogger evidence around pairing behavior.

## 0.1.1

- Added the manual Home Assistant config flow.
- Added Bluetooth discovery through Home Assistant's Bluetooth infrastructure and ESPHome proxies.

## 0.1.0

- Initial experimental release.
