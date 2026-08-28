# Schneider Ambient BLE

Experimental local Home Assistant control for Schneider Ambient Lighting / WSC mirrors and mirror cabinets over Bluetooth Low Energy.

> **Status:** experimental reverse-engineering project. Brightness and color temperature are decoded. Power/zone semantics are still being validated.
>
> **Current integration version: 0.1.3.** This release rebuilds the setup process so the physical pairing/learn button is pressed **before** the Bluetooth scan, then Home Assistant verifies the GATT connection and replays the observed Schneider session initialization before saving the device.

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

Use the button above to open this repository in HACS.

### Manual HACS installation

1. Open **HACS** in Home Assistant.
2. Open **Integrations**.
3. Open the menu in the top-right corner.
4. Choose **Custom repositories**.
5. Repository: `https://github.com/aharder3/schneider-ambient-ble`
6. Type/category: **Integration**.
7. Click **Add**.
8. Search for **Schneider Ambient BLE**.
9. Install it.
10. Restart Home Assistant.

If an older version was already installed, use **Redownload** in HACS and restart Home Assistant completely. Verify that `custom_components/schneider_ambient/manifest.json` reports version `0.1.3`.

## Setup process in Home Assistant

Version 0.1.3 intentionally changes the manual setup order.

1. Make sure the ESPHome Bluetooth Proxy is online and close to the mirror cabinet.
2. Go to **Settings → Devices & services → Add integration → Schneider Ambient BLE**.
3. Home Assistant first shows the physical-button instruction.
4. Press the physical **pairing/learn button on the light or mirror cabinet**.
5. Immediately press **Continue** in Home Assistant.
6. Home Assistant runs a fresh active Bluetooth scan for about 12 seconds.
7. If exactly one compatible `WSC` device is found, it is selected automatically. If more than one is found, choose the correct device.
8. Home Assistant connects to the device through the best available local adapter or ESPHome Bluetooth Proxy.
9. Before saving the entry, the integration replays the non-secret initialization observed in PacketLogger:
   - current local date → characteristic `C4` as `YY MM DD`
   - current local time → characteristic `C5` as `HH MM SS`
   - `AF 01` → characteristic `CE`
10. The config entry is created only if the connection and initialization succeed.
11. If discovery or connection fails, the flow stays open and offers a retry instead of aborting.

Automatic Bluetooth discovery is still supported. If Home Assistant discovers a compatible `WSC` advertisement itself, it asks for confirmation and tests the connection before saving the device.

## Why there is no standard BLE `pair()` call

The available PacketLogger capture shows a normal LE connection, GATT discovery, state reads and application writes. It does **not** contain a Bluetooth Security Manager pairing exchange on L2CAP CID `0x0006`, and it does not show a link-encryption-change event for the WSC connection.

Therefore the physical button is currently treated as a **device-side pairing/learn/authorization step**, not as proof of standard BLE bonding. The integration deliberately does not invent a `BleakClient.pair()` call that the captured Schneider app session did not perform.

See [`docs/pairing.md`](docs/pairing.md) for the detailed evidence and capture procedure.

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

Keep Wi-Fi credentials, API keys and OTA passwords in your local `secrets.yaml` and never commit that file.

## Experimental direct ESPHome control

[`esphome/direct_control_experimental.yaml`](esphome/direct_control_experimental.yaml) contains an alternative where the ESP32 connects to the cabinet itself while still acting as a Bluetooth Proxy.

This option requires a local BLE address and is intentionally not preconfigured with a real device address. The Home Assistant integration is the recommended path because it can use Home Assistant's Bluetooth routing and any suitable ESPHome proxy.

## Current protocol knowledge

The proprietary service observed during reverse engineering is:

```text
B35D95C0-6A68-437E-ABE7-0EBFFD8E0661
```

Observed characteristics currently used by the project:

```text
C2  color temperature
C3  brightness
C4  local date (YY MM DD)
C5  local time (HH MM SS)
C6  power / zones (experimental)
CE  AF 01 session/init command (exact semantic name still unknown)
```

Current decoded functionality:

- Brightness: 0–100 % mapped to 0–10000
- Color temperature: Kelvin value transferred as a 16-bit value
- Date/time synchronization: decoded from the capture
- `AF 01` session/init write: observed and replayed, exact meaning still under investigation
- Power / zones: experimental
- Standard BLE SMP bonding: not observed in the available capture

See [`docs/protocol.md`](docs/protocol.md) and [`docs/pairing.md`](docs/pairing.md).

## Privacy

This public repository intentionally contains no:

- personal names or identifiers
- home network IP addresses
- Wi-Fi credentials
- Home Assistant API keys
- OTA passwords
- real Bluetooth MAC addresses
- raw PacketLogger `.pklg` captures

Raw Bluetooth captures may expose device addresses and nearby Bluetooth metadata. Do not publish them without redaction.

## GitHub Pages

An optional documentation landing page is included in [`docs/index.md`](docs/index.md).

To enable GitHub Pages:

1. Open the repository on GitHub.
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Branch: **main**.
5. Folder: **/docs**.
6. Click **Save**.

## Issues / contributions

Bug reports and protocol findings are welcome:

https://github.com/aharder3/schneider-ambient-ble/issues

Before submitting a Bluetooth capture, remove or redact personal device addresses and nearby-device metadata.

## Disclaimer

This is an independent community project and is not affiliated with, endorsed by, or supported by Schneider or W. Schneider+Co AG. Product and company names may be trademarks of their respective owners.

Use at your own risk. The integration is based on reverse engineering of locally observed Bluetooth communication and may stop working after firmware or app updates.

## License

See [`LICENSE`](LICENSE).
