# Changelog

## 0.1.2

- Add explicit physical pairing-button instruction to the Home Assistant config flow.
- Document PacketLogger evidence: no standard BLE SMP/bonding exchange is present in the captured WSC session.
- Identify the pre-command C4/C5 writes as date/time synchronisation rather than pairing credentials.
- Add `docs/pairing.md` with a reproducible capture procedure for true first-time registration.


## 0.1.1

- Fix Home Assistant manual setup returning `not_implemented` by implementing `async_step_user`.
- Scan Home Assistant's existing Bluetooth adapters and ESPHome Bluetooth Proxies for compatible devices.
- Add exact `WSC` local-name discovery fallback in addition to the proprietary service UUID.
- Use Home Assistant's selected connectable BLE path plus `bleak-retry-connector` for GATT writes.
- Add English and German config-flow strings.
- Add Bluetooth adapter dependency recommended for remote adapter/proxy availability.

## 0.1.0

- Initial experimental integration.
