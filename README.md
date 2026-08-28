# Schneider Ambient BLE

Experimental local Home Assistant control for Schneider Ambient Lighting / WSC mirrors and mirror cabinets over Bluetooth Low Energy.

> **Status:** reverse-engineering project. Brightness and color temperature are decoded. Power/zone semantics are still experimental.
>
> **Current integration version: 0.1.8.** This release fixes the remaining Home Assistant setup-result issue, registers the WSC device immediately, fixes the experimental switch platform import, and requires a fresh C6 non-authorized → `0x55` transition for physical authorization.

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
"version": "0.1.8"
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


### Home Assistant setup-result behavior

Version 0.1.8 fixes the completion screen in the config-flow finalization hook (`async_on_create_entry`). The integration registers the WSC device before Home Assistant returns the finished flow to the frontend, explicitly normalizes the returned flow title, and supplies a localized success description. This avoids relying on timing between config-entry setup and the frontend's generic `Created configuration for ...` fallback.

## First authorization / pairing flow

The PacketLogger trace makes the setup order clear:

```text
Discover WSC
   ↓
Connect Bluetooth/GATT
   ↓
Complete GATT discovery
   ↓
Read C1
   ↓
Poll C6 every ~0.5 s
   ↓
01 00 03 00 00 00 00 00   waiting
   ↓ physical cabinet button
01 55 03 00 00 00 00 00   confirmed
   ↓
Read current cabinet state
   ↓
Write current date to C4
Write current time to C5
   ↓
Create Home Assistant entry
```

During setup, Home Assistant therefore behaves like the captured Schneider app:

1. It finds WSC.
2. It establishes the Bluetooth/GATT connection **before** asking for the physical button.
3. Once connected, the setup screen tells you to press the physical pairing/learn button.
4. Home Assistant keeps the connection open and reads C6 every 0.5 seconds.
5. There is **no Continue button to confirm the physical press**. The cabinet itself confirms it by changing C6 from the observed `0x00` state to `0x55`.
6. Home Assistant then reads the current state and synchronizes date/time.
7. The config entry is created only if the sequence succeeds.

The trace contains no BLE SMP Pairing Request/Response on L2CAP CID `0x0006` and no link-encryption transition for WSC. The integration therefore does not invent a standard `BleakClient.pair()` operation.

See [`docs/pairing.md`](docs/pairing.md) for packet-level evidence.

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
