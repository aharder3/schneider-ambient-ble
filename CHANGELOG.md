# Changelog

## 0.1.4

- Corrected the pairing/learn sequence: Home Assistant now discovers and **connects to WSC first**.
- The physical pairing/learn-button prompt is shown only after a real Bluetooth/GATT connection succeeds.
- Keeps the setup connection open while the confirmation dialog is shown, with a 90-second cleanup watchdog.
- After the user presses the cabinet button and confirms, Home Assistant sends the observed Schneider application initialization (`C4` date, `C5` time, `CE = AF 01`).
- If the setup link drops while the user is at the button prompt, the integration reconnects before initialization.
- Discovery and connection failures no longer instruct the user to press the cabinet button prematurely.
- Standard BLE `pair()` is still intentionally not called because the available capture contains no SMP pairing exchange or WSC link-encryption-change event.

## 0.1.3

- Reworked manual setup with a visible scan progress step and explicit connection verification.
- Added retry screens for discovery and connection failures.
- Added replay of the observed non-secret Schneider initialization.

## 0.1.2

- Added a physical pairing/learn-button prompt.
- Documented the PacketLogger evidence around pairing behavior.

## 0.1.1

- Added the manual Home Assistant config flow.
- Added Bluetooth discovery through Home Assistant's Bluetooth infrastructure and ESPHome proxies.

## 0.1.0

- Initial experimental release.
