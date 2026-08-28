# Schneider Ambient BLE

Experimental local Home Assistant control for Schneider Ambient Lighting / WSC mirrors and mirror cabinets over Bluetooth Low Energy.

> **Status:** experimental reverse-engineering project. Brightness and color temperature are decoded. Power/zone semantics and pairing/bonding are still being validated.
>
> **Current integration version: 0.1.1.** This release adds the manual Home Assistant setup flow; older 0.1.0 builds can show `not_implemented` when the integration is added manually.

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

The ESP32 remains a generic connectable Bluetooth Proxy. Schneider-specific protocol handling stays in Home Assistant.

## Install with HACS

### One-click

Use the button above. It opens your Home Assistant instance and prepares this repository for HACS.

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
11. Go to **Settings → Devices & services**.
12. When the mirror cabinet is visible through a connectable Bluetooth adapter or ESPHome Bluetooth Proxy, Home Assistant should offer discovery automatically.

You can also add the integration manually via **Settings → Devices & services → Add integration → Schneider Ambient BLE**. Version 0.1.1 scans Home Assistant's existing Bluetooth cache/proxies and lets you select the discovered `WSC` device.

If Home Assistant shows `not_implemented`, an old 0.1.0 copy is still loaded. Update the HACS integration, restart Home Assistant completely, and verify that `manifest.json` reports version `0.1.1`.

If pairing mode is required by the cabinet, place the cabinet in pairing mode when Home Assistant asks for it. Pairing/bonding support is still experimental in this project.

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

This option requires a local BLE address and is intentionally not preconfigured with a real device address.

## Current protocol knowledge

The proprietary service observed during reverse engineering is:

```text
B35D95C0-6A68-437E-ABE7-0EBFFD8E0661
```

Current decoded functionality:

- Brightness: 0–100 % mapped to 0–10000
- Color temperature: Kelvin value transferred as a 16-bit value
- Power / zones: experimental
- Pairing / bonding: under investigation

See [`docs/protocol.md`](docs/protocol.md) for technical notes.

## Privacy

This public repository intentionally contains no:

- personal names or identifiers
- home network IP addresses
- Wi-Fi credentials
- Home Assistant API keys
- OTA passwords
- real Bluetooth MAC addresses
- raw PacketLogger `.pklg` captures

Raw Bluetooth captures may expose device addresses and nearby Bluetooth metadata. Do not publish them.

## GitHub Pages

An optional documentation landing page is included in [`docs/index.md`](docs/index.md).

To enable GitHub Pages:

1. Open the repository on GitHub.
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Branch: **main**.
5. Folder: **/docs**.
6. Click **Save**.

GitHub will then publish the documentation page after the Pages deployment completes.

## Issues / contributions

Bug reports and protocol findings are welcome via GitHub Issues:

https://github.com/aharder3/schneider-ambient-ble/issues

Before submitting a Bluetooth capture, remove or redact personal device addresses and nearby-device metadata.

## Disclaimer

This is an independent community project and is not affiliated with, endorsed by, or supported by Schneider or W. Schneider+Co AG. Product and company names may be trademarks of their respective owners.

Use at your own risk. The integration is based on reverse engineering of locally observed Bluetooth communication and may stop working after firmware or app updates.

## License

See [`LICENSE`](LICENSE).
