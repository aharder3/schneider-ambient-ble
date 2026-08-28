from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
    CONTROL_NIGHTLIGHT,
    CONTROL_OFF,
    SESSION_INIT,
    ZONE_ALL,
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


@dataclass(frozen=True)
class SchneiderControlState:
    """Decoded top-level lighting state."""

    is_on: bool | None
    brightness_percent: float | None
    color_temp_kelvin: int | None
    automatic_mode: bool | None
    nightlight_mode: bool | None
    zone_mask: int | None
    raw_control: bytes


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
        """Read C1 and initial C6 before showing the physical-button form."""
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
        """Build a repeated big-endian 16-bit payload matching current C2/C3 length."""
        if len(current) < 2 or len(current) % 2:
            raise RuntimeError(
                f"Unexpected Schneider characteristic length: {len(current)} bytes"
            )
        encoded = max(0, min(65535, int(value))).to_bytes(2, "big")
        return encoded * (len(current) // 2)

    @staticmethod
    def _manual_control(zone_mask: int) -> bytes:
        zone_mask &= ZONE_ALL
        if zone_mask == 0:
            return CONTROL_OFF
        return bytes([0x01, 0x00, zone_mask, 0x00])

    @staticmethod
    def _automatic_control(zone_mask: int) -> bytes:
        zone_mask &= ZONE_ALL
        if zone_mask == 0:
            return CONTROL_OFF
        return bytes([0x02, 0x00, 0x00, zone_mask])

    @staticmethod
    def _decode_control(
        control: bytes,
    ) -> tuple[bool | None, bool | None, bool | None, int | None]:
        """Decode the observed C6 manual/auto/night-light state model.

        Capture evidence used here:
        - 00 00 00 00 -> main lights off
        - 01 00 01 00 -> manual, zone 1
        - 01 00 02 00 -> manual, zone 2
        - 01 00 03 00 -> manual, both zones
        - 02 00 00 02 -> automatic/HCL, zone mask 2
        - 02 00 00 03 -> automatic/HCL, both zones
        - 00 00 00 02 -> night-light command/state candidate

        The authorization marker may temporarily occupy byte 1 (0x55), so byte 1
        is deliberately ignored for normal mode decoding.
        """
        if len(control) < 4:
            return None, None, None, None

        mode = control[0]
        byte2 = control[2]
        byte3 = control[3]

        if mode == 0x01:
            zone_mask = byte2 & ZONE_ALL
            return zone_mask != 0, False, False, zone_mask

        if mode == 0x02:
            zone_mask = byte3 & ZONE_ALL
            return zone_mask != 0, True, False, zone_mask

        if control[:4] == CONTROL_NIGHTLIGHT:
            # Night light is separate from the two main light zones.
            return False, False, True, 0

        if control[:4] == CONTROL_OFF:
            return False, False, False, 0

        _LOGGER.debug("Unknown Schneider C6 state: %s", control.hex(" "))
        return None, None, None, None

    async def read_control_state(self) -> SchneiderControlState:
        """Read power/mode/zones, brightness and color temperature."""
        client = await self.open_connection()
        try:
            control = bytes(await client.read_gatt_char(CHAR_CONTROL))
            c3 = bytes(await client.read_gatt_char(CHAR_BRIGHTNESS))
            c2 = bytes(await client.read_gatt_char(CHAR_CCT))
        finally:
            await client.disconnect()

        is_on, automatic, nightlight, zone_mask = self._decode_control(control)
        brightness = None
        cct = None
        if len(c3) >= 2:
            brightness = int.from_bytes(c3[:2], "big") / 100.0
        if len(c2) >= 2:
            cct = int.from_bytes(c2[:2], "big")

        return SchneiderControlState(
            is_on=is_on,
            brightness_percent=brightness,
            color_temp_kelvin=cct,
            automatic_mode=automatic,
            nightlight_mode=nightlight,
            zone_mask=zone_mask,
            raw_control=control,
        )

    async def _write_control(self, payload: bytes) -> bytes:
        """Write one captured C6 control payload and return the resulting C6 state."""
        client = await self.open_connection()
        try:
            # AF 01 is observed repeatedly around mode/control groups and is known
            # to be accepted by the tested cabinet before C6 writes.
            await client.write_gatt_char(CHAR_SESSION, SESSION_INIT, response=True)
            await client.write_gatt_char(CHAR_CONTROL, payload, response=True)
            readback = bytes(await client.read_gatt_char(CHAR_CONTROL))
            _LOGGER.debug(
                "Schneider C6 write %s -> read-back %s",
                payload.hex(" "),
                readback.hex(" "),
            )
            return readback
        finally:
            await client.disconnect()

    async def set_main_power(self, on: bool, *, automatic: bool = False) -> bytes:
        """Turn both main light zones on or turn all main light zones off."""
        if not on:
            return await self._write_control(CONTROL_OFF)
        payload = (
            self._automatic_control(ZONE_ALL)
            if automatic
            else self._manual_control(ZONE_ALL)
        )
        return await self._write_control(payload)

    async def set_zone_mask(self, zone_mask: int, *, automatic: bool = False) -> bytes:
        """Set the active two-light zone mask while preserving manual/auto mode."""
        payload = (
            self._automatic_control(zone_mask)
            if automatic
            else self._manual_control(zone_mask)
        )
        return await self._write_control(payload)

    async def set_automatic_mode(self, enabled: bool, *, zone_mask: int) -> bytes:
        """Switch between captured Automatic/HCL and manual C6 formats."""
        zone_mask &= ZONE_ALL
        if zone_mask == 0:
            zone_mask = ZONE_ALL
        payload = (
            self._automatic_control(zone_mask)
            if enabled
            else self._manual_control(zone_mask)
        )
        return await self._write_control(payload)

    async def set_nightlight_mode(self, enabled: bool) -> bytes:
        """Activate/deactivate the captured C6 night-light mode candidate."""
        return await self._write_control(CONTROL_NIGHTLIGHT if enabled else CONTROL_OFF)

    async def apply_manual_light_state(
        self,
        *,
        brightness_percent: float | None = None,
        color_temp_kelvin: int | None = None,
        zone_mask: int = ZONE_ALL,
    ) -> tuple[bytes | None, bytes | None]:
        """Apply global brightness/CCT and verify read-back in one GATT session.

        Brightness and color temperature are global controls for the tested
        two-light cabinet. The C6 manual preamble preserves the currently active
        zone mask instead of forcing a disabled zone back on.
        """
        if brightness_percent is None and color_temp_kelvin is None:
            await self.set_zone_mask(zone_mask, automatic=False)
            return None, None

        zone_mask &= ZONE_ALL
        if zone_mask == 0:
            zone_mask = ZONE_ALL

        client = await self.open_connection()
        try:
            brightness_payload = None
            cct_payload = None

            if brightness_percent is not None:
                percent = max(10.0, min(100.0, float(brightness_percent)))
                current_c3 = bytes(await client.read_gatt_char(CHAR_BRIGHTNESS))
                brightness_payload = self._uniform_u16_payload(
                    current_c3, round(percent * 100)
                )

            if color_temp_kelvin is not None:
                kelvin = int(color_temp_kelvin)
                if not 2000 <= kelvin <= 6500:
                    raise ValueError(
                        "Color temperature must be between 2000 and 6500 K"
                    )
                current_c2 = bytes(await client.read_gatt_char(CHAR_CCT))
                cct_payload = self._uniform_u16_payload(current_c2, kelvin)

            await client.write_gatt_char(CHAR_SESSION, SESSION_INIT, response=True)
            await client.write_gatt_char(
                CHAR_CONTROL,
                self._manual_control(zone_mask),
                response=True,
            )

            if brightness_payload is not None:
                await client.write_gatt_char(
                    CHAR_BRIGHTNESS, brightness_payload, response=True
                )
                brightness_readback = bytes(
                    await client.read_gatt_char(CHAR_BRIGHTNESS)
                )
                if brightness_readback != brightness_payload:
                    raise RuntimeError(
                        "Schneider brightness write completed but read-back differs: "
                        f"wanted {brightness_payload.hex(' ')}, "
                        f"got {brightness_readback.hex(' ')}"
                    )

            if cct_payload is not None:
                await client.write_gatt_char(CHAR_CCT, cct_payload, response=True)
                cct_readback = bytes(await client.read_gatt_char(CHAR_CCT))
                if cct_readback != cct_payload:
                    raise RuntimeError(
                        "Schneider CCT write completed but read-back differs: "
                        f"wanted {cct_payload.hex(' ')}, got {cct_readback.hex(' ')}"
                    )

            return brightness_payload, cct_payload
        finally:
            await client.disconnect()

    async def set_color_temperature_kelvin(
        self, kelvin: int, *, zone_mask: int = ZONE_ALL
    ) -> bytes:
        """Set global color temperature in Kelvin."""
        _, payload = await self.apply_manual_light_state(
            color_temp_kelvin=kelvin, zone_mask=zone_mask
        )
        assert payload is not None
        return payload

    async def set_brightness_percent(
        self, percent: float, *, zone_mask: int = ZONE_ALL
    ) -> bytes:
        """Set global brightness percentage."""
        payload, _ = await self.apply_manual_light_state(
            brightness_percent=percent, zone_mask=zone_mask
        )
        assert payload is not None
        return payload

    async def write(self, characteristic: str, payload: bytes) -> None:
        """Perform a raw write for protocol experiments."""
        client = await self.open_connection()
        try:
            await client.write_gatt_char(characteristic, payload, response=True)
        finally:
            await client.disconnect()
