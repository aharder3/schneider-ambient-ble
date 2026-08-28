# Schneider Ambient Lighting BLE protocol — working notes

These notes contain only sanitized protocol observations. Raw PacketLogger traces are intentionally not part of the public repository because they may contain device identifiers and nearby Bluetooth metadata.

## Device discovery

Observed local name: `WSC`.

Primary proprietary service:

`B35D95C0-6A68-437E-ABE7-0EBFFD8E0661`

## Characteristics

| Characteristic | Observed use | Confidence |
|---|---|---|
| C1 | device/status information | high |
| C2 | color temperature | high |
| C3 | brightness | high |
| C4 | local date (`YY MM DD`) | high |
| C5 | local time (`HH MM SS`) | high |
| C6 | power / two-light zone mask / operating mode / physical auth marker | high for observed values |
| C8/C9/CA | HCL daily-curve data | medium-high |
| D0/D1 | Night-light schedule/settings | medium-high |
| CE | session / settings commit commands | high for payloads, semantic names inferred |

## First authorization

The first-authorization sequence is independently reproduced against real hardware:

1. connect to WSC;
2. read C1 and initial C6;
3. initial C6 is `01 00 03 00 00 00 00 00`;
4. press the physical cabinet button;
5. C6 changes to `01 55 03 00 00 00 00 00`;
6. read C1/C4/C5/CB/C2/C3/C6/C8/C6/C9/CA/D0/D1;
7. write current date to C4 and current time to C5.

No BLE SMP Pairing Request/Response was seen in the capture. `0x55` is therefore treated as an application-level physical authorization marker, not standard BLE bonding.

## Brightness

Brightness is encoded as a big-endian 16-bit value from 0 to 10000. The official HCL manual describes the user range as 10–100 %, so the Home Assistant light control clamps interactive brightness to 10–100 % and uses C6 power-off for off.

Examples observed in app writes:

- 100% → `27 10 27 10`
- 50% → `13 88 13 88`
- 20% → `07 D0 07 D0`

Formula: `raw = round(percent * 100)`.

The tested cabinet can return a longer C3 value than the four-byte writes shown by the app. The integration reads the current characteristic length and repeats the requested 16-bit value across all returned slots; this strategy is independently verified on the tested hardware for C2 and is also used for C3.

## Color temperature

Kelvin is encoded as big-endian uint16. Examples:

- 2000 K → `07 D0`
- 3000 K → `0B B8`
- 3500 K → `0D AC`
- 4000 K → `0F A0`
- 5100 K → `13 EC`
- 6500 K → `19 64`

Direct macOS tests successfully wrote 3000 K and 6500 K to all C2 slots and received exact read-back.

## Two main lights / manual mode

A second official-app capture confirms the manual C6 zone mask:

| C6 | Meaning |
|---|---|
| `00 00 00 00` | main lights off |
| `01 00 01 00` | manual mode, zone 1 |
| `01 00 02 00` | manual mode, zone 2 |
| `01 00 03 00` | manual mode, both zones |

Only on/off is separate per main light. Brightness and color temperature are global controls for the tested two-light cabinet.

The integration currently maps Zone 1 to **upper light** and Zone 2 to **lower light**. The zone-mask behavior is capture-confirmed; the physical upper/lower naming is inferred from the app/device behavior and can be swapped in `const.py` if a model is wired in the opposite order.

## Automatic / HCL mode

The second capture corrects the earlier `0x03` hypothesis. Automatic/HCL uses mode byte `0x02` and stores the active light mask in C6 byte 3:

| C6 | Meaning |
|---|---|
| `02 00 00 01` | automatic/HCL, zone 1 candidate |
| `02 00 00 02` | automatic/HCL, zone 2 |
| `02 00 00 03` | automatic/HCL, both zones |

Observed writes include `02 00 00 02` and `02 00 00 03`. When Home Assistant toggles a zone while HCL is active, it preserves the automatic format and changes only the zone mask.

The app also writes C8, C9 and CA followed by `CE = A0 01`; those characteristics contain schedule-like HCL curve points. Version 0.2.1 does not edit the HCL schedule itself.

## Night light

During the captured Night-light interaction the app writes:

- `C6 = 00 00 00 02`
- D0 schedule data
- C3 brightness data
- D1 schedule/settings data
- `CE = E1 00`

This strongly associates `00 00 00 02` with Night-light mode and D0/D1 with its configuration. Version 0.2.1 exposes the immediate C6 Night-light mode as an experimental Home Assistant switch, but it intentionally does **not** edit the Night-light schedule/settings yet.

The official Schneider HCL app documentation separately describes Night-light activation/deactivation and per-day Night-light schedules, which matches the capture structure.

## Session / commit characteristic CE

Observed CE values include:

- `AF 01` — repeated around interactive control/mode groups;
- `A0 01` — after writing HCL curve data (C8/C9/CA);
- `E1 00` — after writing Night-light settings (D0/D1).

Only `AF 01` is used by normal v0.2.1 interactive controls. The integration does not currently write HCL or Night-light schedules.
