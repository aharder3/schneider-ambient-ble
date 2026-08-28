# Pairing / physical-button behavior

## What the PacketLogger capture proves

The captured Schneider/WSC session contains a normal BLE connection followed by GATT service/characteristic discovery and application writes. It does **not** contain a Bluetooth Security Manager (SMP) pairing exchange on L2CAP CID `0x0006`, nor an HCI encryption-change event for the WSC connection. Therefore the capture does not prove that the original app performs standard BLE bonding in this session.

Immediately before the first lighting commands the app writes:

- characteristic C4: three bytes matching the capture date (`YY MM DD`)
- characteristic C5: three bytes matching the capture time (`HH MM SS`)
- characteristic CE: `AF 01`, repeated before several command groups

C4/C5 are consequently interpreted as date/time synchronisation, **not pairing credentials**. `AF 01` looks like an application-level initialise/apply/request command, but its exact purpose is not yet proven.

## Physical pairing button

The Schneider user flow requires a physical button press on the luminaire/mirror cabinet when adding a controller. Since that button action itself is not visible as standard SMP traffic in the available capture, the Home Assistant setup flow explicitly asks the user to press the physical pairing button before continuing.

This is deliberately described as a **physical pairing-mode step**, not as confirmed BLE bonding. If a future capture includes the complete first-time registration from before the button press, it can be compared for SMP traffic or additional proprietary GATT writes.

## Recommended capture for completing the reverse engineering

1. Remove/forget the cabinet from the Schneider app if possible.
2. Start PacketLogger before opening the Schneider app.
3. Open the app and begin adding a new cabinet.
4. Press the physical pairing button only when prompted.
5. Complete registration.
6. Keep recording for another 10 seconds.

A useful future capture should be checked for L2CAP Security Manager traffic (CID `0x0006`), HCI encryption events, and any new writes to the proprietary `B35D95C0-6A68-437E-ABE7-0EBFFD8E0661` service.
