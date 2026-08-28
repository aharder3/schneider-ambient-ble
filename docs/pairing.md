# Pairing / first authorization

The current capture shows a proprietary **connect first, then physical-button authorization** flow. It does **not** show standard BLE SMP pairing/bonding.

## Captured sequence

The WSC connection is established first. The app completes GATT discovery and reads characteristic C1. It then repeatedly reads characteristic C6 approximately every 0.5 seconds while waiting for the user to press the physical button on the cabinet.

Observed C6 values:

```text
17:59:50.467  C6 -> 01 00 03 00 00 00 00 00
17:59:51.067  C6 -> 01 00 03 00 00 00 00 00
17:59:51.608  C6 -> 01 00 03 00 00 00 00 00
17:59:52.297  C6 -> 01 00 03 00 00 00 00 00
17:59:52.837  C6 -> 01 00 03 00 00 00 00 00
17:59:53.377  C6 -> 01 55 03 00 00 00 00 00  <-- physical button confirmed
```

The `0x55` byte is therefore used by this integration as the observed device-side authorization marker. Home Assistant does not ask the user to press Continue. It keeps the GATT connection open, polls C6, and advances automatically when the cabinet reports `0x55`.

## After the button is confirmed

The official app reads the current state in this order:

```text
C1, C4, C5, CB, C2, C3, C6, C8, C6, C9, CA, D0, D1
```

It then writes the current local date to C4 (`YY MM DD`) and the current local time to C5 (`HH MM SS`).

`CE = AF 01` occurs later, at the start of interactive control groups, not during the physical-button authorization itself.

## What the capture does not show

There is no observed BLE SMP Pairing Request/Response on L2CAP CID `0x0006`, and no encryption-change event for this WSC link. Therefore the integration deliberately does not call `BleakClient.pair()`.
