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
| `B35D95C6-6A68-437E-ABE7-0EBFFD8E0661` | power / zone / mode bitfield | medium |
| `B35D95CE-6A68-437E-ABE7-0EBFFD8E0661` | app/session/config trigger | low |

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

## Power / zone candidate

Observed writes include:

- `01 00 03 00`
- `01 00 01 00`
- `00 00 00 00`
- `01 00 02 00`
- `03 00 03 00`

`00 00 00 00` appears to be an all-off state. The remaining bitfield semantics still need a controlled capture before they should be treated as stable.
