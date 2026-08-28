# Schneider Ambient Lighting BLE protocol — working notes

These notes contain only sanitized protocol observations. Raw PacketLogger traces are intentionally not part of the public repository because they may contain nearby device names and Bluetooth addresses.

## Device discovery

Observed local name: `WSC`.

The device exposes the proprietary service:

`B35D95C0-6A68-437E-ABE7-0EBFFD8E0661`

## Characteristics

| Characteristic | Observed use | Confidence |
|---|---|---|
| `B35D95C2-6A68-437E-ABE7-0EBFFD8E0661` | color temperature | high |
| `B35D95C3-6A68-437E-ABE7-0EBFFD8E0661` | brightness | high |
| `B35D95C4-6A68-437E-ABE7-0EBFFD8E0661` | local date (`YY MM DD`) | high |
| `B35D95C5-6A68-437E-ABE7-0EBFFD8E0661` | local time (`HH MM SS`) | high |
| `B35D95C6-6A68-437E-ABE7-0EBFFD8E0661` | power / zone / mode bitfield | medium |
| `B35D95CE-6A68-437E-ABE7-0EBFFD8E0661` | `AF 01` session/init command | medium for payload, low for semantic name |

## Observed connection/session sequence

The recorded WSC connection follows this order:

1. LE connection
2. ATT MTU exchange
3. GATT service and characteristic discovery
4. reads of current device state
5. write current local date to `C4`
6. write current local time to `C5`
7. write `AF 01` to `CE`
8. lighting commands on `C2`, `C3` and `C6`

No Bluetooth SMP pairing exchange and no WSC link-encryption-change event are present in the available capture. See [`pairing.md`](pairing.md).

## Brightness

Brightness is encoded as a big-endian 16-bit value from `0` to `10000`, duplicated in the four-byte payload.

Examples:

- 100% → `27 10 27 10`
- 50% → `13 88 13 88`
- 20% → `07 D0 07 D0`

Formula: `raw = round(percent * 100)`.

## Color temperature

Kelvin is encoded as a big-endian 16-bit value, duplicated in the four-byte payload.

Examples:

- 2000 K → `07 D0 07 D0`
- 3500 K → `0D AC 0D AC`
- 4400 K → `11 30 11 30`
- 5100 K → `13 EC 13 EC`
- 6500 K → `19 64 19 64`

## Date and time

The capture contains:

- `C4`: `1A 08 1C` → 2026-08-28 (`YY MM DD`)
- `C5`: `10 3B 37` → 16:59:55 (`HH MM SS`)

These values match the capture date/time and therefore are treated as clock synchronization, not pairing credentials.

## Session/init command

The app writes `AF 01` to `CE` after the initial state reads and repeats it before several later command groups. The payload is therefore reproduced by the integration when opening a new session, but the exact semantic meaning of `AF 01` is still not proven.

## Power / zone candidate

Observed writes include:

- `01 00 03 00`
- `01 00 01 00`
- `00 00 00 00`
- `01 00 02 00`
- `03 00 03 00`

`00 00 00 00` appears to be an all-off state. The remaining bitfield semantics still need a controlled capture before they should be treated as stable.
