# Changelog

## 0.1.1

- Fix Home Assistant manual setup returning `not_implemented` by implementing `async_step_user`.
- Scan Home Assistant's existing Bluetooth adapters and ESPHome Bluetooth Proxies for compatible devices.
- Add exact `WSC` local-name discovery fallback in addition to the proprietary service UUID.
- Use Home Assistant's selected connectable BLE path plus `bleak-retry-connector` for GATT writes.
- Add English and German config-flow strings.
- Add Bluetooth adapter dependency recommended for remote adapter/proxy availability.

## 0.1.0

- Initial experimental integration.
