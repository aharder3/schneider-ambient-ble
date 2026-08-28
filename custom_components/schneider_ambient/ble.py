from __future__ import annotations

import asyncio
import logging

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothReachabilityIntent
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    AUTHORIZATION_BYTE_INDEX,
    AUTHORIZATION_MARKER,
    CHAR_BRIGHTNESS,
    CHAR_C8,
    CHAR_C9,
    CHAR_CA,
    CHAR_CB,
    CHAR_CCT,
    CHAR_CONTROL,
    CHAR_D0,
    CHAR_D1,
    CHAR_DATE,
    CHAR_DEVICE_INFO,
    CHAR_SESSION,
    CHAR_TIME,
    CONTROL_ALL_ON,
    SESSION_INIT,
)

_LOGGER = logging.getLogger(__name__)

BUTTON_POLL_INTERVAL_SECONDS = 0.5
BUTTON_VERIFY_TIMEOUT_SECONDS = 8.0

POST_AUTH_READ_ORDER = (
    CHAR_DEVICE_INFO,
    CHAR_DATE,
    CHAR_TIME,
    CHAR_CB,
    CHAR_CCT,
    CHAR_BRIGHTNESS,
    CHAR_CONTROL,
    CHAR_C8,
    CHAR_CONTROL,
    CHAR_C9,
    CHAR_CA,
    CHAR_D0,
    CHAR_D1,
)


class SchneiderAuthorizationTimeout(TimeoutError):
    """Raised when C6 never reports the physical-button marker."""

    def __init__(self, last_value: bytes | None) -> None:
        self.last_value = last_value
        last_text = last_value.hex(" ") if last_value is not None else "no C6 response"
        super().__init__(
            "Timed out waiting for physical authorization; last C6 value: "
            f"{last_text}"
        )


class SchneiderUnexpectedAuthorizationState(RuntimeError):
    """Raised when C6 is already authorized before the user is prompted."""


class SchneiderBleClient:
    """BLE client using Home Assistant's selected local/remote Bluetooth path."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address

    def _ble_device(self):
        """Return the currently best connectable BLE path for the device."""
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is not None:
            return ble_device

        reason = bluetooth.async_address_reachability_diagnostics(
            self.hass,
            self.address,
            BluetoothReachabilityIntent.CONNECTION,
        )
        raise RuntimeError(
            "Schneider Ambient device is not reachable by a connectable "
            f"Bluetooth adapter/proxy. {reason}"
        )

    async def open_connection(self) -> BleakClientWithServiceCache:
        """Open a real GATT connection via Home Assistant's selected BLE path."""
        ble_device = self._ble_device()
        return await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            ble_device.name or "Schneider Ambient",
            max_attempts=3,
        )

    @staticmethod
    def is_authorized(control_value: bytes | bytearray) -> bool:
        """Return True when C6 contains the physical authorization marker."""
        return (
            len(control_value) > AUTHORIZATION_BYTE_INDEX
            and control_value[AUTHORIZATION_BYTE_INDEX] == AUTHORIZATION_MARKER
        )

    @staticmethod
    async def read_pre_authorization_state(
        client: BleakClientWithServiceCache,
    ) -> tuple[bytes, bytes]:
        """Read C1 and initial C6 before showing the physical-button form.

        This exact order was independently confirmed against the real cabinet from
        macOS: the GATT connection is already established, C1 is readable and C6
        reports ``01 00 03 00 00 00 00 00`` before the physical button is pressed.
        """
        device_info = bytes(await client.read_gatt_char(CHAR_DEVICE_INFO))
        control = bytes(await client.read_gatt_char(CHAR_CONTROL))
        _LOGGER.debug("Schneider C1 before authorization: %s", device_info.hex(" "))
        _LOGGER.debug("Schneider initial C6: %s", control.hex(" "))
        return device_info, control

    @classmethod
    async def wait_for_authorization_marker(
        cls,
        client: BleakClientWithServiceCache,
        *,
        timeout: float = BUTTON_VERIFY_TIMEOUT_SECONDS,
    ) -> bytes:
        """Poll C6 after the user pressed the cabinet button and clicked Continue."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        last_value: bytes | None = None

        while True:
            value = bytes(await client.read_gatt_char(CHAR_CONTROL))
            if value != last_value:
                _LOGGER.debug("Schneider C6 after button press: %s", value.hex(" "))
                last_value = value

            if cls.is_authorized(value):
                return value

            remaining = deadline - loop.time()
            if remaining <= 0:
                raise SchneiderAuthorizationTimeout(last_value)

            await asyncio.sleep(min(BUTTON_POLL_INTERVAL_SECONDS, remaining))

    @staticmethod
    async def sync_after_authorization(
        client: BleakClientWithServiceCache,
    ) -> None:
        """Replay the post-button state-read and clock-sync sequence from the app."""
        for characteristic in POST_AUTH_READ_ORDER:
            value = bytes(await client.read_gatt_char(characteristic))
            _LOGGER.debug(
                "Schneider post-authorization read %s: %s",
                characteristic,
                value.hex(" "),
            )

        now = dt_util.now()
        await client.write_gatt_char(
            CHAR_DATE,
            bytes([now.year % 100, now.month, now.day]),
            response=True,
        )

        now = dt_util.now()
        await client.write_gatt_char(
            CHAR_TIME,
            bytes([now.hour, now.minute, now.second]),
            response=True,
        )

    @staticmethod
    def _uniform_u16_payload(current: bytes, value: int) -> bytes:
        """Build the cabinet's repeated big-endian 16-bit zone payload.

        C2 and C3 on the tested WSC are 8 bytes (four 16-bit slots). Reading the
        characteristic first makes this robust to a different number of slots while
        preserving the exact payload shape used by the device.
        """
        if len(current) < 2 or len(current) % 2:
            raise RuntimeError(
                f"Unexpected Schneider characteristic length: {len(current)} bytes"
            )
        encoded = max(0, min(65535, int(value))).to_bytes(2, "big")
        return encoded * (len(current) // 2)

    async def _write_uniform_u16(self, characteristic: str, value: int) -> bytes:
        """Read length, send the confirmed preamble, write all zones, then verify."""
        client = await self.open_connection()
        try:
            current = bytes(await client.read_gatt_char(characteristic))
            payload = self._uniform_u16_payload(current, value)

            # Confirmed from the Schneider capture and the successful macOS CCT test.
            await client.write_gatt_char(CHAR_SESSION, SESSION_INIT, response=True)
            await client.write_gatt_char(CHAR_CONTROL, CONTROL_ALL_ON, response=True)
            await client.write_gatt_char(characteristic, payload, response=True)

            readback = bytes(await client.read_gatt_char(characteristic))
            if readback != payload:
                raise RuntimeError(
                    "Schneider write completed but read-back differs: "
                    f"wanted {payload.hex(' ')}, got {readback.hex(' ')}"
                )
            return readback
        finally:
            await client.disconnect()

    async def set_color_temperature_kelvin(self, kelvin: int) -> bytes:
        """Set all C2 light zones to one color temperature in Kelvin."""
        if not 2000 <= kelvin <= 6500:
            raise ValueError("Color temperature must be between 2000 and 6500 K")
        return await self._write_uniform_u16(CHAR_CCT, kelvin)

    async def set_brightness_percent(self, percent: float) -> bytes:
        """Set all C3 light zones to one brightness percentage.

        The capture encodes brightness as percent * 100 in each 16-bit slot. This
        encoding is decoded from the trace but has not yet had the same independent
        macOS write verification as C2/color temperature.
        """
        percent = max(0.0, min(100.0, float(percent)))
        return await self._write_uniform_u16(CHAR_BRIGHTNESS, round(percent * 100))

    async def read_control_state(self) -> tuple[float | None, int | None]:
        """Read the first C3 brightness slot and first C2 CCT slot."""
        client = await self.open_connection()
        try:
            c3 = bytes(await client.read_gatt_char(CHAR_BRIGHTNESS))
            c2 = bytes(await client.read_gatt_char(CHAR_CCT))
        finally:
            await client.disconnect()

        brightness = None
        cct = None
        if len(c3) >= 2:
            brightness = int.from_bytes(c3[:2], "big") / 100.0
        if len(c2) >= 2:
            cct = int.from_bytes(c2[:2], "big")
        return brightness, cct

    async def write(self, characteristic: str, payload: bytes) -> None:
        """Perform a raw write for experimental controls."""
        client = await self.open_connection()
        try:
            await client.write_gatt_char(characteristic, payload, response=True)
        finally:
            await client.disconnect()
