# Schneider Ambient BLE

Experimental local Home Assistant control for Schneider Ambient Lighting / WSC mirrors and mirror cabinets over Bluetooth Low Energy.

## Home Assistant alternative to the Schneider app

This project is intended as an independent, local Home Assistant replacement/alternative for the everyday Bluetooth lighting controls of the **Schneider Ambient Lighting App**: separate two-light switching, master power, brightness, tunable-white color temperature, Automatic/HCL and Night-light mode.

Official Schneider app information: <https://www.wschneider.com/ch/de/wussten-sie/licht-sich-wohlfuehlen-im-raum/schneider-app/>

The official app remains the reference implementation and may expose additional model-specific functions such as HCL schedules, night-light settings or saved ambience profiles. This project is not affiliated with or endorsed by W. Schneider+Co AG.

## Confirmed / implemented controls

Version 0.2.1 exposes the controls observed on a two-light Schneider/WSC cabinet:

- **Master light**: both main lights on/off together, global brightness and global tunable-white color temperature.
- **Upper light**: separate on/off only.
- **Lower light**: separate on/off only.
- **Brightness**: 10–100 % through the normal HA light brightness control; it applies to both main lights.
- **Light color / color temperature**: 2000–6500 K; it applies to both main lights. The C2 write path is independently verified on real hardware from macOS at 3000 K and 6500 K, including read-back.
- **Automatic / HCL**: separate switch using the newly captured C6 automatic format (`02 00 00 <zone-mask>`).
- **Night light**: separate switch using the captured C6 night-light command/state candidate `00 00 00 02`.

The second PacketLogger capture confirms that manual mode stores the two-light mask in C6 byte 2 (`01 00 01 00`, `01 00 02 00`, `01 00 03 00`) while Automatic/HCL stores it in byte 3 (`02 00 00 02`, `02 00 00 03`). Manual brightness or color-temperature changes deliberately leave Automatic/HCL and Night-light mode.

> **Status:** reverse-engineering project. Color temperature is independently real-hardware verified. Separate-zone C6 values and the Automatic/HCL `0x02` format are directly observed in the official-app capture. The immediate Night-light C6 state is implemented from the capture and should still be treated as experimental until independently replayed from macOS.
>
> **Current integration version: 0.2.3.** Home Assistant exposes one master light, two on/off-only zone lights, an Automatic/HCL switch and a Night-light switch.

[![Open your Home Assistant instance and open HACS repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aharder3&repository=schneider-ambient-ble&category=integration)

## Recommended architecture

```text
Schneider / WSC mirror cabinet
          ⇅ BLE
ESP32 with ESPHome Bluetooth Proxy
          ⇅ LAN / Wi-Fi
Home Assistant
          ⇅
Schneider Ambient BLE custom integration
```

The ESP32 stays a generic connectable Bluetooth Proxy. Schneider-specific setup and protocol handling stay in Home Assistant.

## Install with HACS

### One-click

Use the HACS button above.

### Manual installation

1. Open **HACS → Integrations**.
2. Open the menu in the top-right corner.
3. Choose **Custom repositories**.
4. Repository: `https://github.com/aharder3/schneider-ambient-ble`
5. Category: **Integration**.
6. Add and install **Schneider Ambient BLE**.
7. Restart Home Assistant completely.

When updating an existing development install, use **Redownload** in HACS and verify:

```text
/config/custom_components/schneider_ambient/manifest.json
```

contains:

```json
"version": "0.2.3"
```

## Home Assistant controls

After setup the device page should contain five active controls:

1. **Schneider Ambient** (`light`) — master on/off, global brightness and 2000–6500 K color temperature.
2. **Upper light** (`light`) — on/off only.
3. **Lower light** (`light`) — on/off only.
4. **Automatic / HCL** (`switch`) — changes between manual and captured HCL mode while preserving the current zone mask.
5. **Night light** (`switch`) — activates/deactivates the captured night-light mode.

Brightness and color temperature are intentionally only present on the master light because the tested cabinet applies those values globally to both main lights. The old development entities `Brightness`, `Color temperature` and `Power (experimental)` are removed from the entity registry so they do not remain as duplicates.


## Real-hardware protocol sweep (v0.2.2)

A complete direct-macOS sweep confirmed the two-light model used by this integration:

- manual Zone 1 = **lower light** (`01 00 01 00`)
- manual Zone 2 = **upper light** (`01 00 02 00`)
- both = `01 00 03 00`; off = `00 00 00 00`
- Automatic/HCL uses `02 00 00 <zone mask>`
- C2 colour temperature works throughout 2000–6500 K and must update all four 16-bit slots (8 bytes)
- C3 brightness works from 1–100 %

Brightness and colour temperature are global hardware settings. Home Assistant exposes them on **both** zone light entities for a natural light-card experience; changing either entity updates the shared value on the cabinet while the two on/off states remain independent. Runtime operations are serialized and retried across transient GATT disconnects to improve ESPHome Bluetooth Proxy reliability.

## Runtime latency optimization

Direct macOS benchmarking on the tested WSC showed that the expensive part of an interactive Home Assistant command is establishing a new GATT connection: approximately 3.8-6.0 seconds per reconnect in the test, versus roughly 30-240 ms for writes on an already-open connection. Version 0.2.3 therefore keeps the runtime BLE connection alive for 120 seconds after the most recent command and reuses the initialized manual session for slider bursts. A dropped proxy/peripheral connection still triggers a fresh whole-operation retry.

The benchmark tool is available as `tools/wsc_latency_test.py`.

## ESPHome Bluetooth Proxy

Recommended example: [`esphome/bluetooth_proxy.yaml`](esphome/bluetooth_proxy.yaml)

Core configuration:

```yaml
esp32_ble_tracker:
  scan_parameters:
    active: true

bluetooth_proxy:
  active: true
```

Keep Wi-Fi credentials, API keys and OTA passwords in your local `secrets.yaml`; never commit them.


### Home Assistant setup behavior

Version 0.2.1 retains the physical authorization as a normal Home Assistant form instead of a background progress message. The form is only shown after the Bluetooth/GATT connection is established and C1 plus the initial non-authorized C6 value have been read successfully. The user then presses the physical cabinet button and clicks **Continue**; Home Assistant verifies C6=`0x55` before running the post-authorization reads and clock sync.

## First authorization / pairing flow

The real cabinet has now been verified directly from macOS with this exact order:

```text
Discover WSC
   ↓
Connect Bluetooth/GATT
   ↓
Read C1
   ↓
Read initial C6 = 01 00 03 00 00 00 00 00
   ↓
SHOW A VISIBLE HOME ASSISTANT FORM
"Bluetooth connected — press the cabinet button now"
   ↓
User presses the physical cabinet button
   ↓
User clicks Continue
   ↓
Home Assistant polls C6 for up to 8 s
   ↓
C6 = 01 55 03 00 00 00 00 00
   ↓
Read current cabinet state
   ↓
Write current date to C4
Write current time to C5
   ↓
Create Home Assistant entry
```

This is application-level physical authorization. The captured WSC session contains no standard BLE SMP Pairing Request/Response, so the integration does not call `BleakClient.pair()`.

## Confirmed color-temperature control

On the tested cabinet C2 is 8 bytes, containing four big-endian 16-bit Kelvin values. Home Assistant now reads the current C2 length first and writes the requested Kelvin value into every slot, matching the successful direct macOS tests.

Examples:

```text
3000 K → 0B B8 0B B8 0B B8 0B B8
6500 K → 19 64 19 64 19 64 19 64
```

The confirmed command sequence is:

```text
CE → AF 01
C6 → 01 00 03 00
C2 → repeated Kelvin payload
C2 → read-back verification
```


### Direct power / Automatic-mode verification helper

For protocol testing from macOS, [`tools/wsc_power_mode_mac.py`](tools/wsc_power_mode_mac.py) and [`tools/wsc_zone_mode_mac.py`](tools/wsc_zone_mode_mac.py) can replay the sanitized C6 states and print the read-back. The Night-light write remains marked experimental until it has also been independently replayed outside the Schneider app.

## Protocol knowledge

Primary proprietary service:

```text
B35D95C0-6A68-437E-ABE7-0EBFFD8E0661
```

Important characteristics:

| Characteristic | Observed role |
|---|---|
| C1 | device/status information |
| C2 | color temperature |
| C3 | brightness |
| C4 | local date, `YY MM DD` |
| C5 | local time, `HH MM SS` |
| C6 | power/zones plus physical authorization status |
| CE | `AF 01` control-session preamble; **not** treated as pairing |

Decoded controls:

- Brightness: 0–100 % maps to 0–10000, duplicated big-endian 16-bit value.
- Color temperature: Kelvin value, duplicated big-endian 16-bit value.
- Power/zones: separate manual zone masks are capture-confirmed; Automatic/HCL uses the captured `0x02` format; Night-light mode is still experimental for direct replay.

The capture shows `CE = AF 01` later, immediately before interactive brightness/color-temperature groups. For C2/C3 interaction, the app then writes C6=`01 00 03 00` before the actual value. Version 0.2.1 retains that captured preamble for manual brightness/CCT control.

See [`docs/protocol.md`](docs/protocol.md).

## Experimental direct ESPHome control

[`esphome/direct_control_experimental.yaml`](esphome/direct_control_experimental.yaml) is kept as an alternative. The Home Assistant integration is recommended because it can use Home Assistant's Bluetooth routing and ESPHome Bluetooth proxies.

## Privacy

This public repository intentionally contains no personal names, home-network IP addresses, Wi-Fi credentials, Home Assistant API keys, OTA passwords, real Bluetooth MAC addresses, or raw PacketLogger `.pklg` captures.

Raw Bluetooth captures may expose device addresses and nearby Bluetooth metadata. Redact them before publishing.

## GitHub Pages

An optional documentation landing page is included in [`docs/index.md`](docs/index.md). To enable it, use **Settings → Pages → Deploy from a branch → main → /docs**.

## Issues / contributions

Bug reports and protocol findings are welcome:

https://github.com/aharder3/schneider-ambient-ble/issues

## Disclaimer

This is an independent community project and is not affiliated with, endorsed by, or supported by Schneider or W. Schneider+Co AG. Product and company names may be trademarks of their respective owners.

Use at your own risk. The integration is based on reverse engineering of locally observed Bluetooth communication and may stop working after firmware or app updates.

## License

See [`LICENSE`](LICENSE).
