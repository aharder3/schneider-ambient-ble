from homeassistant.const import Platform

DOMAIN = "schneider_ambient"
SERVICE_UUID = "b35d95c0-6a68-437e-abe7-0ebffd8e0661"
CHAR_CCT = "b35d95c2-6a68-437e-abe7-0ebffd8e0661"
CHAR_BRIGHTNESS = "b35d95c3-6a68-437e-abe7-0ebffd8e0661"
CHAR_POWER = "b35d95c6-6a68-437e-abe7-0ebffd8e0661"
PLATFORMS = [Platform.NUMBER, Platform.SWITCH]
