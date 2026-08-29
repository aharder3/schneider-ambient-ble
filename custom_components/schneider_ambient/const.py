DOMAIN = "schneider_ambient"

SERVICE_UUID = "b35d95c0-6a68-437e-abe7-0ebffd8e0661"

# Proprietary Schneider/WSC characteristics discovered in PacketLogger captures.
CHAR_DEVICE_INFO = "b35d95c1-6a68-437e-abe7-0ebffd8e0661"
CHAR_CCT = "b35d95c2-6a68-437e-abe7-0ebffd8e0661"
CHAR_BRIGHTNESS = "b35d95c3-6a68-437e-abe7-0ebffd8e0661"
CHAR_DATE = "b35d95c4-6a68-437e-abe7-0ebffd8e0661"
CHAR_TIME = "b35d95c5-6a68-437e-abe7-0ebffd8e0661"
CHAR_CONTROL = "b35d95c6-6a68-437e-abe7-0ebffd8e0661"
CHAR_C8 = "b35d95c8-6a68-437e-abe7-0ebffd8e0661"
CHAR_C9 = "b35d95c9-6a68-437e-abe7-0ebffd8e0661"
CHAR_CA = "b35d95ca-6a68-437e-abe7-0ebffd8e0661"
CHAR_CB = "b35d95cb-6a68-437e-abe7-0ebffd8e0661"
CHAR_CC = "b35d95cc-6a68-437e-abe7-0ebffd8e0661"
CHAR_SESSION = "b35d95ce-6a68-437e-abe7-0ebffd8e0661"
CHAR_CF = "b35d95cf-6a68-437e-abe7-0ebffd8e0661"
CHAR_D0 = "b35d95d0-6a68-437e-abe7-0ebffd8e0661"
CHAR_D1 = "b35d95d1-6a68-437e-abe7-0ebffd8e0661"

# First physical authorization marker observed in C6 byte 1.
AUTHORIZATION_MARKER = 0x55
AUTHORIZATION_BYTE_INDEX = 1

# Repeated control/session command observed around interactive operations.
SESSION_INIT = bytes([0xAF, 0x01])

# Manual C6 mode: byte 2 is the two-light zone mask.
ZONE_1 = 0x01
ZONE_2 = 0x02
ZONE_ALL = ZONE_1 | ZONE_2

# Physical mapping confirmed on real hardware by the macOS protocol sweep:
# Zone 1 = lower light, Zone 2 = upper light.
ZONE_LOWER = ZONE_1
ZONE_UPPER = ZONE_2

CONTROL_OFF = bytes([0x00, 0x00, 0x00, 0x00])
CONTROL_NIGHTLIGHT = bytes([0x00, 0x00, 0x00, 0x02])

# Manual mode stores the active light mask in C6 byte 2.
CONTROL_MANUAL_ZONE_1 = bytes([0x01, 0x00, ZONE_1, 0x00])
CONTROL_MANUAL_ZONE_2 = bytes([0x01, 0x00, ZONE_2, 0x00])
CONTROL_MANUAL_ALL_ON = bytes([0x01, 0x00, ZONE_ALL, 0x00])

# Automatic/HCL mode stores the active light mask in C6 byte 3.
# Captured examples: 02 00 00 02 and 02 00 00 03.
CONTROL_AUTO_ZONE_1 = bytes([0x02, 0x00, 0x00, ZONE_1])
CONTROL_AUTO_ZONE_2 = bytes([0x02, 0x00, 0x00, ZONE_2])
CONTROL_AUTO_ALL_ON = bytes([0x02, 0x00, 0x00, ZONE_ALL])

# Backwards-compatible alias used by older code/docs.
CONTROL_ALL_ON = CONTROL_MANUAL_ALL_ON

PLATFORMS = ["light", "switch"]
