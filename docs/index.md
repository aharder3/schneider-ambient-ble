# Schneider Ambient BLE

Independent Home Assistant alternative for the core Bluetooth lighting controls of the [Schneider Ambient Lighting App](https://www.wschneider.com/ch/de/wussten-sie/licht-sich-wohlfuehlen-im-raum/schneider-app/).

Current integration version: **0.2.1**.

## Home Assistant controls

- Native `light` entity: **on/off**, **brightness**, and **tunable-white color temperature from 2000–6500 K**.
- Separate **Automatic mode** switch for the captured Automatic/HCL mode.
- Manual brightness or color-temperature changes switch the cabinet back to manual mode.

The Schneider app remains the official reference implementation. This community integration aims to replace its core day-to-day lighting controls inside Home Assistant; model-specific schedule editing, night-light configuration and saved ambience profiles are not fully implemented yet.

## Recommended setup

Use an ESP32 running ESPHome as a connectable Bluetooth Proxy and install the Home Assistant custom integration through HACS.

## First authorization

The real cabinet was independently verified from macOS with this order: connect first, read C1 and C6, then press the physical cabinet button. C6 changes from `01 00 03 00 00 00 00 00` to `01 55 03 00 00 00 00 00`. Home Assistant reproduces that application-level authorization flow.

See [Pairing / first authorization](pairing.md) and [Protocol notes](protocol.md).


## v0.2.1 controls

- Master light: both main lights, global brightness and color temperature.
- Upper light: separate on/off.
- Lower light: separate on/off.
- Automatic / HCL: captured C6 `0x02` mode.
- Night light: experimental captured C6 `00 00 00 02` mode.

Official Schneider app reference: <https://www.wschneider.com/ch/de/wussten-sie/licht-sich-wohlfuehlen-im-raum/schneider-app/>
