# Physical pairing / learn-button behavior

## Observed setup order

The important ordering for the Schneider/WSC setup is:

1. The WSC device is discovered over Bluetooth.
2. The controller establishes a Bluetooth LE / GATT connection to the cabinet.
3. **Only after the connection is established** is the user asked to press the physical pairing/learn button on the light or mirror cabinet.
4. The user presses the physical button and confirms in the UI.
5. The application-level Schneider initialization continues over the established connection.

Version 0.1.4 implements this ordering in Home Assistant.

## What the PacketLogger capture shows

For the captured WSC connection, the trace shows a normal LE connection, ATT/GATT setup, state reads, and application writes. In particular, the app writes:

- local date to characteristic `C4` as `YY MM DD`
- local time to characteristic `C5` as `HH MM SS`
- `AF 01` to characteristic `CE`

Brightness, color-temperature and power/zone commands follow later.

The captured session does **not** contain a Bluetooth Security Manager (SMP) pairing exchange on L2CAP CID `0x0006`, and it does **not** show an HCI link-encryption-change event for the WSC connection. Therefore the project does not claim that the observed button step is standard BLE bonding.

## Home Assistant 0.1.4 setup sequence

1. Make sure the ESPHome Bluetooth Proxy is online and near the cabinet.
2. Start **Settings → Devices & services → Add integration → Schneider Ambient BLE**.
3. Home Assistant performs a fresh Bluetooth discovery scan **without asking for the physical button yet**.
4. If one WSC device is found it is selected automatically; if several are found, choose the correct one.
5. Home Assistant establishes a real GATT connection to the selected WSC device.
6. **Only after that connection succeeds**, Home Assistant shows the pairing/learn-button confirmation screen.
7. Press the physical pairing/learn button on the light or mirror cabinet.
8. Press **Continue** in Home Assistant.
9. Home Assistant sends the observed application-level initialization (`C4` date, `C5` time, `CE = AF 01`).
10. The config entry is created only if the full sequence succeeds.

Home Assistant attempts to keep the setup GATT connection open while the button dialog is visible. A watchdog closes an abandoned connection after 90 seconds. If the link drops while the user is pressing the button, the integration reconnects automatically before sending the initialization, but the button prompt is still never shown until at least one real GATT connection has succeeded.

## Why `BleakClient.pair()` is not called

The physical button is currently treated as a **device-side learn/authorization step** because the recorded Schneider app session contains no standard SMP pairing transaction. Calling `BleakClient.pair()` would introduce a BLE security exchange that is not supported by the evidence in the capture.

A clean first-registration capture can still reveal whether Schneider performs an additional proprietary authorization write that was absent from the existing session.
