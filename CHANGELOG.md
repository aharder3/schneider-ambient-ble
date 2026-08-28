# Changelog

## 0.1.9

- Confirmed color-temperature control directly from macOS against a real WSC cabinet at both 3000 K and 6500 K, including exact C2 read-back.
- Fixed Home Assistant C2/C3 payload generation: the tested cabinet uses four 16-bit slots (8 bytes), not the previous 4-byte payload. The integration now reads the current characteristic length and writes the requested value to every slot.
- Rebuilt first authorization UI: Home Assistant connects first, reads C1 and a non-authorized C6 state, then displays a persistent **physical button** form. Only after the user presses the cabinet button and clicks Continue does HA verify C6=`0x55`.
- Added C2/C3 read-back verification after writes.
- Added initial brightness/color-temperature reads when the entities are created.
- Added a generic anonymized macOS CCT verification tool under `tools/`.


## 0.1.8

- Fixed the Home Assistant completion screen at the correct lifecycle point using `async_on_create_entry()`. The WSC device is now registered before the final config-flow result is returned to the frontend.
- The final `ConfigFlowResult` now explicitly carries the normalized entry title instead of relying on frontend timing.
- Added a localized `config.create_entry.success` message, so setup success no longer depends on Home Assistant's generic `Created configuration for ...` fallback.
- Added the required top-level `title` to custom-integration translation files.
- Added setup/finalization log lines containing the resolved title and Bluetooth address for troubleshooting.

## 0.1.7

- Fixed the blank Home Assistant completion message (`Created configuration for .`) by giving manual config flows a stable title from the first step.
- Register the Schneider/WSC device in the Home Assistant device registry immediately during config-entry setup, before entity platforms are forwarded.
- Fixed the experimental switch platform importing the removed `CHAR_POWER` constant; C6 is now consistently referenced as `CHAR_CONTROL`.
- Physical authorization now requires a fresh C6 transition: at least one non-`0x55` read must be observed before `0x55` is accepted. A stale `0x55` on initial connection no longer skips the button step.
- Normal brightness/color-temperature writes no longer require C6 to remain `0x55`; the capture indicates `0x55` is part of first authorization, not a permanent per-write authorization flag.

## 0.1.6

- Confirmed the captured connect → C6 polling → `0x55` physical-authorization → state/clock-sync flow works end-to-end in Home Assistant through an ESPHome Bluetooth Proxy.
- Fixed config entries being created with blank or punctuation-only Bluetooth names (for example `Created configuration for .`).
- Added automatic repair of already-created invalid config-entry titles on the next integration setup/restart.
- Kept the BLE authorization protocol unchanged; this release only hardens naming and documents the successful real-device test.

## 0.1.5

- Rebuilt the first-authorization flow from the PacketLogger capture.
- The integration now connects first, then polls characteristic C6 every 0.5 s while instructing the user to press the physical pairing/learn button.
- The setup continues automatically only when C6 changes from the observed pre-button state `01 00 03 00 00 00 00 00` to the observed confirmation state `01 55 03 00 00 00 00 00`.
- Removed the incorrect user-side Continue confirmation from the pairing step.
- Replays the official app's post-button state-read order and date/time synchronization.
- `AF 01` is no longer treated as a pairing command; the capture shows it later as part of interactive control groups.
- Manual discovery no longer hides an already-configured address as "not found"; Home Assistant can report `already_configured` correctly.

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
