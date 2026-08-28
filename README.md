# Schneider Ambient BLE

Experimental local control for Schneider Ambient Lighting / WSC mirrors and mirror cabinets.

The repository intentionally contains **no personal identifiers, network addresses, Bluetooth MAC addresses, raw PacketLogger captures, or credentials**.

## Recommended setup: ESPHome Bluetooth Proxy + Home Assistant integration

Flash an ESP32 with [`esphome/bluetooth_proxy.yaml`](esphome/bluetooth_proxy.yaml). The ESP acts only as a connectable Bluetooth proxy; Schneider-specific logic stays in Home Assistant.

```yaml
esp32_ble_tracker:
  scan_parameters:
    active: true

bluetooth_proxy:
  active: true
```

The custom integration matches the proprietary Schneider service UUID and should appear as a Bluetooth-discovered device in Home Assistant when the cabinet is reachable through a connectable Bluetooth adapter/proxy.

### HACS installation

Until this repository is added to the HACS default store, add it as a **Custom repository** of type **Integration**. Then install **Schneider Ambient BLE** and restart Home Assistant.

Current entities:

- brightness number (decoded)
- color-temperature number (decoded)
- experimental power switch, disabled by default

Pairing/bonding behavior and power/zone semantics still need controlled captures before they can be considered stable.

## Alternative: direct ESPHome control

[`esphome/direct_control_experimental.yaml`](esphome/direct_control_experimental.yaml) lets an ESP32 connect directly to the cabinet and expose controls to Home Assistant while still acting as a Bluetooth proxy.

This requires setting the current BLE address in `schneider_mac`. Some devices may use a random/private address, so the address should not be published or assumed permanent.

## ESPHome secrets

Example local `secrets.yaml` (never commit it):

```yaml
wifi_ssid: "YOUR_WIFI"
wifi_password: "YOUR_PASSWORD"
api_key: "YOUR_ESPHOME_API_KEY"
ota_password: "YOUR_OTA_PASSWORD"
fallback_ap_password: "YOUR_FALLBACK_AP_PASSWORD"
```

## Protocol notes

See [`docs/protocol.md`](docs/protocol.md).

## Privacy / publishing

Do **not** commit raw `.pklg` files. They can contain device addresses and nearby Bluetooth metadata. The `.gitignore` blocks them by default.

## Publishing to GitHub

With the GitHub CLI installed and authenticated:

```bash
git clone /path/to/this/folder schneider-ambient-ble
cd schneider-ambient-ble

gh auth status
gh repo create schneider-ambient-ble --public --source=. --remote=origin --push
```

Or create an empty repository in the GitHub web UI and then:

```bash
git remote add origin git@github.com:YOUR_GITHUB_USER/schneider-ambient-ble.git
git push -u origin main
```

After creating the repository, replace `OWNER` in `custom_components/schneider_ambient/manifest.json` with the GitHub owner/user name.
