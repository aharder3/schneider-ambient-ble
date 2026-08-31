# Changelog

## 0.2.7

- Fixed the manual Bluetooth picker defaulting to **Scan again**, which could make setup look like an endless rescan loop.
- Real Bluetooth devices are now sorted first and the best Schneider/WSC match is explicitly preselected.
- **Scan again / Erneut suchen** is now the final picker item instead of the default.
- A failed active rescan keeps the previous Bluetooth cache instead of replacing the picker with an empty list.
- Clarified in the setup text that an active rescan takes about eight seconds.

## 0.2.6

- Fixed setup started from Home Assistant Bluetooth discovery: it now shows the same mandatory manual Bluetooth-device picker as user-started setup instead of bypassing directly to the discovered WSC.
- The picker is populated immediately from Home Assistant's connectable Bluetooth cache; **Erneut suchen / Scan again** performs an active scan when needed.
- A selected device is only assigned as the config-flow unique ID after the user explicitly chooses it.
- Treat an initial C6 authorization marker `0x55` as an already-authorized cabinet instead of a connection/setup error. A dedicated confirmation screen explains the persisted authorization before synchronization continues.

## 0.2.5

- Manual setup now always shows a Bluetooth-device picker instead of silently auto-selecting the only WSC candidate.
- The picker lists **all connectable Bluetooth devices** currently visible to Home Assistant; advertisements already matching Schneider/WSC are marked with `✓` and sorted first.
- Added an **Erneut suchen / Scan again** choice directly in the Bluetooth picker.
- A manually selected device is validated by the real proprietary WSC GATT reads (C1/C6), so setup can still work when a proxy provides incomplete advertisement metadata.
- Device naming still happens before the slower GATT authorization connection is opened.

## 0.2.4

- Added a dedicated setup step to choose the Home Assistant device name before the Bluetooth/GATT authorization starts.
- The chosen name becomes the config-entry title and device-registry name, so entities are naturally grouped below names such as `Bad Spiegelschrank`.
- The name field is pre-filled with `Schneider Ambient`, accepts up to 64 characters, and is validated before the BLE connection is opened.

## 0.2.3

- Added a reusable runtime GATT connection with a 120-second idle timeout. The direct macOS latency benchmark measured WSC reconnects at roughly 3.8-6.0 seconds, while writes on an already-open connection completed in roughly 30-240 ms.
- Use direct hardware-verified C6 writes for normal manual/Automatic zone switching, and reuse the initialized manual BLE session for repeated brightness/color-temperature slider writes. After one `CE=AF 01` + C6 manual-zone preamble, subsequent C2/C3 writes are sent directly while the same connection remains alive.
- Keep all runtime GATT work serialized and retain whole-operation retry/reconnect behavior when the proxy or peripheral actually drops the link.
- Release the cached connection cleanly when the Home Assistant config entry unloads.
- Added `tools/wsc_latency_test.py` for reproducible latency benchmarking.

## 0.2.2

- Confirmed physical zone mapping on real hardware: **Zone 1 = lower light**, **Zone 2 = upper light**.
- Expose brightness and tunable-white colour temperature directly on both `Licht oben` and `Licht unten`; those values are shared by the cabinet as required by the hardware.
- Remove the separate master light entity from the current layout.
- Confirmed C2 (colour temperature) across 2000–6500 K. C2 requires the full 8-byte/four-slot payload; a 4-byte write only updates half the returned slots.
- Confirmed C3 brightness across 1–100 %. The integration now permits brightness below the previous 10 % floor.
- Confirmed Automatic/HCL C6 masks for zone 1, zone 2 and both zones.
- Add serialized runtime GATT operations and whole-operation reconnect retries for transient ESPHome Bluetooth Proxy disconnects.
- Reduce proxy traffic by using the verified fixed 8-byte C2/C3 writes and avoiding redundant per-command read-backs.

## 0.2.1

- Added two separate on/off-only Home Assistant light entities for the cabinet's two physical light zones. Brightness and color temperature remain global on the master light.
- Corrected Automatic/HCL C6 decoding from the earlier `0x03` hypothesis to the newly captured `02 00 00 <zone-mask>` format.
- Added zone-aware C6 state handling: manual mode uses byte 2 (`01 00 01/02/03 00`), Automatic/HCL uses byte 3 (`02 00 00 01/02/03`).
- Added an experimental Night-light switch using the captured `C6 = 00 00 00 02` command/state.
- Zone switching preserves Automatic/HCL mode when possible; manual brightness/CCT changes exit HCL/Night-light mode and apply globally to both main lights.
- Updated protocol notes from the second sanitized PacketLogger capture.
- Expanded the README's Schneider Ambient Lighting App replacement section to include separate two-light switching, HCL and Night-light control.

## 0.2.0

- Replaced the separate brightness/color-temperature Number entities and disabled experimental power switch with one native Home Assistant `light` entity.
- The light entity now exposes on/off, brightness and tunable-white color temperature (2000–6500 K).
- Added an enabled-by-default `Automatic mode` switch using the observed C6 manual/automatic mode toggle (`01 00 03 00` ↔ `03 00 03 00`). Automatic/HCL mode remains protocol-inferred until independently verified from macOS.
- Manual brightness/CCT changes explicitly use the manual C6 preamble and update the shared Automatic-mode state to off.
- Added shared runtime state so the light and Automatic-mode switch stay synchronized in Home Assistant.
- Cleans up legacy development Number / experimental Power entities from the entity registry.
- README now positions the project as an independent local Home Assistant alternative for the core controls of the Schneider Ambient Lighting App and links to Schneider's official app page.

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
