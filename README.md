# Schneider Ambient BLE

Experimental local Home Assistant control for Schneider Ambient Lighting / WSC mirrors and mirror cabinets over Bluetooth Low Energy.

## Confirmed on real hardware

The proprietary C2 color-temperature path has now been independently verified directly from macOS against a real WSC cabinet. The confirmed control sequence is `CE = AF 01` → `C6 = 01 00 03 00` → C2 write. C2 is 8 bytes on the tested device (four big-endian 16-bit Kelvin slots). Both 3000 K (`0B B8` repeated four times) and 6500 K (`19 64` repeated four times) were written and read back successfully.

Version 0.1.9 also changes first authorization to a visible Home Assistant form: HA connects first and confirms C6 is non-authorized, then the user is explicitly told to press the physical cabinet button and click Continue; HA only proceeds after C6 returns `0x55`.


> **Status:** reverse-engineering project. Brightness and color temperature are decoded. Power/zone semantics are still experimental.
>
> **Current integration version: 0.1.9.** This release uses the real-hardware-verified C2 payload shape, performs read-back verification, and changes first authorization to a persistent visible button form: connect first → confirm C6 is non-authorized → ask the user to press the cabinet button → Continue → verify C6=`0x55`.

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
"version": "0.1.9"
```

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

Version 0.1.9 deliberately separates the physical authorization into a normal Home Assistant form instead of a background progress message. The form is only shown after the Bluetooth/GATT connection is established and C1 plus the initial non-authorized C6 value have been read successfully. The user then presses the physical cabinet button and clicks **Continue**; Home Assistant verifies C6=`0x55` before running the post-authorization reads and clock sync.

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
- Power/zones: experimental.

The capture shows `CE = AF 01` later, immediately before interactive brightness/color-temperature groups. For C2/C3 interaction, the app then writes C6=`01 00 03 00` before the actual value. Version 0.1.6 retains that captured preamble for brightness/CCT control.

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
