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
BUTTON_WAIT_TIMEOUT_SECONDS = 60.0

# Exact post-button read order observed in the Schneider app capture. These reads
# populate the app with the cabinet's current state before date/time are synced.
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


class SchneiderAuthorizationRequired(RuntimeError):
    """Raised when the cabinet is connected but not physically authorized."""


class SchneiderAuthorizationTimeout(TimeoutError):
    """Raised when C6 never reports the physical-button marker."""

    def __init__(self, last_value: bytes | None) -> None:
        self.last_value = last_value
        last_text = last_value.hex(" ") if last_value is not None else "no C6 response"
        super().__init__(
            "Timed out waiting for physical authorization; last C6 value: "
            f"{last_text}"
        )


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
    def _is_authorized(control_value: bytes | bytearray) -> bool:
        """Return True when C6 contains the button-confirmation marker."""
        return (
            len(control_value) > AUTHORIZATION_BYTE_INDEX
            and control_value[AUTHORIZATION_BYTE_INDEX] == AUTHORIZATION_MARKER
        )

    @classmethod
    async def wait_for_physical_authorization(
        cls,
        client: BleakClientWithServiceCache,
        *,
        timeout: float = BUTTON_WAIT_TIMEOUT_SECONDS,
    ) -> bytes:
        """Mirror the official app's connect-then-poll physical-button flow.

        PacketLogger shows the app doing the following after GATT discovery:
        1. Read C1 once.
        2. Poll C6 approximately every 0.5 seconds.
        3. Before the physical button is pressed C6 is
           01 00 03 00 00 00 00 00.
        4. The first poll after the button press is
           01 55 03 00 00 00 00 00.
        5. Only then does the app continue with the rest of setup.

        This is application-level authorization. The captured session contains no
        BLE SMP Pairing Request/Response and no link-encryption transition.
        """
        # The official app reads C1 before starting the C6 polling loop.
        device_info = bytes(await client.read_gatt_char(CHAR_DEVICE_INFO))
        _LOGGER.debug("Schneider C1 before authorization: %s", device_info.hex(" "))

        # The capture shows ~0.5 s between the C1 response and the first C6 poll.
        await asyncio.sleep(BUTTON_POLL_INTERVAL_SECONDS)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        last_value: bytes | None = None

        while True:
            value = bytes(await client.read_gatt_char(CHAR_CONTROL))
            if value != last_value:
                _LOGGER.debug("Schneider C6 authorization state: %s", value.hex(" "))
                last_value = value

            if cls._is_authorized(value):
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

        # The app then writes current YY/MM/DD and HH/MM/SS. No AF 01 write is
        # observed during the authorization step itself; AF 01 appears later at
        # the start of interactive control groups.
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

    @classmethod
    async def verify_authorized(
        cls, client: BleakClientWithServiceCache
    ) -> bytes:
        """Verify that an already-configured cabinet still reports authorization."""
        value = bytes(await client.read_gatt_char(CHAR_CONTROL))
        if not cls._is_authorized(value):
            raise SchneiderAuthorizationRequired(
                "Schneider/WSC cabinet is connected but does not report the "
                "physical authorization marker on C6"
            )
        return value

    async def write(self, characteristic: str, payload: bytes) -> None:
        """Connect and perform one control write using the observed app preamble."""
        client = await self.open_connection()
        try:
            await self.verify_authorized(client)

            # In the capture, brightness and color-temperature interaction groups
            # begin with CE=AF 01 and C6=01 00 03 00 before the actual C2/C3 writes.
            if characteristic in (CHAR_BRIGHTNESS, CHAR_CCT):
                await client.write_gatt_char(CHAR_SESSION, SESSION_INIT, response=True)
                await client.write_gatt_char(
                    CHAR_CONTROL, CONTROL_ALL_ON, response=True
                )

            await client.write_gatt_char(characteristic, payload, response=True)
        finally:
            await client.disconnect()
