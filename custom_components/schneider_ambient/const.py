DOMAIN = "schneider_ambient"

SERVICE_UUID = "b35d95c0-6a68-437e-abe7-0ebffd8e0661"

# Proprietary Schneider/WSC characteristics discovered in the capture.
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

# In the captured first-authorization flow C6 reads return
#   01 00 03 00 00 00 00 00
# until the physical cabinet button is pressed. The next poll returns
#   01 55 03 00 00 00 00 00
# and the official app immediately continues setup.
AUTHORIZATION_MARKER = 0x55
AUTHORIZATION_BYTE_INDEX = 1

SESSION_INIT = bytes([0xAF, 0x01])
CONTROL_ALL_ON = bytes([0x01, 0x00, 0x03, 0x00])

PLATFORMS = ["number", "switch"]
