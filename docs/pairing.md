# Physical pairing / learn-button behavior

## What the PacketLogger capture actually shows

The available iPhone PacketLogger capture contains the complete BLE connection used by the Schneider/WSC app session that was recorded.

For the WSC connection, the trace shows:

1. A normal LE connection is established.
2. ATT MTU exchange and GATT service/characteristic discovery follow.
3. The app reads the cabinet state.
4. About eight seconds after connection, the app writes the local date to characteristic `C4` as three bytes: `YY MM DD`.
5. The app writes the local time to characteristic `C5` as three bytes: `HH MM SS`.
6. The app later writes `AF 01` to characteristic `CE` before the lighting command groups.
7. Brightness, color-temperature and power/zone writes then follow.

The capture does **not** contain a Bluetooth Security Manager (SMP) pairing exchange on L2CAP CID `0x0006`, and it does **not** show an HCI encryption-change event for the WSC link. Therefore this project does not claim that the Schneider app performs standard BLE bonding in the captured session.

## What this implies for Home Assistant

The physical button is treated as a **device-side pairing/learn/authorization step**. The integration deliberately does not call `BleakClient.pair()` because that would invent a standard BLE security exchange that is not present in the capture.

Version 0.1.3 changes the manual setup order to match the real-world requirement:

1. Home Assistant first tells the user to press the physical pairing/learn button.
2. Only after the user confirms the button press does Home Assistant run a fresh active Bluetooth scan.
3. If a WSC device is found, Home Assistant connects to it before creating a config entry.
4. The integration replays the non-secret initialization observed in PacketLogger: current local date to `C4`, current local time to `C5`, then `AF 01` to `CE`.
5. The config entry is created only if that connection/initialization succeeds.
6. If nothing is found, or the GATT connection fails, the flow stays open and offers a clean retry instead of aborting.

## Why the old flow could fail

Versions 0.1.1/0.1.2 started the manual Bluetooth scan **before** showing the physical-button instruction. If the cabinet only advertises its setup state after the button is pressed, Home Assistant could finish its scan first and show `No compatible Schneider/WSC device was found`. The user was then told to press the button only after the scan had already ended.

Version 0.1.3 reverses that order.

## Recommended setup sequence

1. Make sure the ESPHome Bluetooth Proxy is online and close to the mirror cabinet.
2. Start **Settings → Devices & services → Add integration → Schneider Ambient BLE**.
3. Home Assistant displays the physical-button instruction first.
4. Press the pairing/learn button on the cabinet.
5. Immediately press **Continue** in Home Assistant.
6. Wait while Home Assistant actively scans.
7. If one compatible WSC device is found, it is selected automatically; if multiple are found, choose the correct one.
8. Home Assistant tests the GATT connection and replays the observed session initialization.
9. Only after success is the device saved.

## Future capture that would improve confidence

For the strongest possible proof of the first-time registration behavior:

1. Remove/forget the cabinet from the Schneider app if possible.
2. Start PacketLogger before opening the Schneider app.
3. Begin adding a new cabinet.
4. Press the physical button only when the Schneider app asks for it.
5. Complete registration.
6. Keep recording for another 10 seconds.

That capture can be checked for any setup-only proprietary GATT write that is missing from the current session.
