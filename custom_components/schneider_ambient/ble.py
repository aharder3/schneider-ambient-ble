from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
import logging
from typing import TypeVar

from bleak_retry_connector import (
    BLEAK_RETRY_EXCEPTIONS,
    BleakClientWithServiceCache,
    establish_connection,
)

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

T = TypeVar("T")

BUTTON_POLL_INTERVAL_SECONDS = 0.5
BUTTON_VERIFY_TIMEOUT_SECONDS = 8.0
RUNTIME_IDLE_DISCONNECT_SECONDS = 120.0

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
        self._gatt_lock = asyncio.Lock()
        self._runtime_client: BleakClientWithServiceCache | None = None
        self._idle_disconnect_task: asyncio.Task[None] | None = None
        # The macOS latency benchmark proved that direct C2/C3 writes are accepted
        # after one CE + C6 manual-session preamble. Remember that session while the
        # same GATT connection is alive so slider updates do not replay the preamble.
        self._manual_session_zone_mask: int | None = None

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
            max_attempts=4,
        )

    async def _disconnect_runtime_client(self) -> None:
        """Drop the cached runtime connection and its session state."""
        client = self._runtime_client
        self._runtime_client = None
        self._manual_session_zone_mask = None
        if client is not None:
            with suppress(Exception):
                await client.disconnect()

    async def _idle_disconnect(self, client: BleakClientWithServiceCache) -> None:
        """Release the BLE connection after a short idle period.

        Connecting to the tested WSC takes roughly 4-6 seconds, while a direct
        characteristic write only takes tens of milliseconds. Keeping the same
        GATT connection alive briefly therefore removes almost all perceived delay
        during normal light-card and slider interaction without permanently holding
        a Bluetooth-proxy connection slot.
        """
        try:
            await asyncio.sleep(RUNTIME_IDLE_DISCONNECT_SECONDS)
            async with self._gatt_lock:
                if self._runtime_client is client:
                    _LOGGER.debug(
                        "Schneider runtime BLE connection idle for %.0fs; disconnecting",
                        RUNTIME_IDLE_DISCONNECT_SECONDS,
                    )
                    await self._disconnect_runtime_client()
        except asyncio.CancelledError:
            return
        finally:
            if self._idle_disconnect_task is asyncio.current_task():
                self._idle_disconnect_task = None

    def _arm_idle_disconnect(self, client: BleakClientWithServiceCache) -> None:
        task = self._idle_disconnect_task
        if task is not None and not task.done():
            task.cancel()
        self._idle_disconnect_task = self.hass.async_create_task(
            self._idle_disconnect(client),
            "Schneider Ambient idle BLE disconnect",
        )

    async def _runtime_connection(self) -> BleakClientWithServiceCache:
        """Return the existing runtime GATT connection or establish it once."""
        client = self._runtime_client
        if client is not None and client.is_connected:
            return client

        if client is not None:
            await self._disconnect_runtime_client()

        client = await self.open_connection()
        self._runtime_client = client
        self._manual_session_zone_mask = None
        return client

    async def _run_gatt_operation(
        self,
        operation: Callable[[BleakClientWithServiceCache], Awaitable["T"]],
        *,
        attempts: int = 3,
    ) -> "T":
        """Run one serialized GATT transaction on a reusable connection.

        The hardware latency benchmark measured reconnect-per-command at about five
        seconds on average, versus ~30-240 ms for writes on an already-open link.
        Runtime operations therefore reuse one connection and only disconnect after
        an idle timeout. If the proxy/peripheral drops the link, the complete
        idempotent operation is retried on a fresh connection.
        """
        async with self._gatt_lock:
            task = self._idle_disconnect_task
            if task is not None and not task.done():
                task.cancel()
                self._idle_disconnect_task = None

            last_exc: BaseException | None = None
            for attempt in range(1, attempts + 1):
                client: BleakClientWithServiceCache | None = None
                try:
                    client = await self._runtime_connection()
                    result = await operation(client)
                    self._arm_idle_disconnect(client)
                    return result
                except BLEAK_RETRY_EXCEPTIONS as exc:
                    last_exc = exc
                    await self._disconnect_runtime_client()
                    if attempt >= attempts:
                        raise
                    _LOGGER.debug(
                        "Schneider GATT operation failed on attempt %d/%d; reconnecting",
                        attempt,
                        attempts,
                        exc_info=True,
                    )
                    await asyncio.sleep(0.20 * attempt)

            assert last_exc is not None
            raise last_exc

    async def async_shutdown(self) -> None:
        """Release a cached runtime GATT connection when the entry unloads."""
        task = self._idle_disconnect_task
        if task is not None and not task.done():
            task.cancel()
        self._idle_disconnect_task = None
        async with self._gatt_lock:
            await self._disconnect_runtime_client()

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

        async def _read(client: BleakClientWithServiceCache) -> SchneiderControlState:
            control = bytes(await client.read_gatt_char(CHAR_CONTROL))
            c3 = bytes(await client.read_gatt_char(CHAR_BRIGHTNESS))
            c2 = bytes(await client.read_gatt_char(CHAR_CCT))

            is_on, automatic, nightlight, zone_mask = self._decode_control(control)
            brightness = self._decode_uniform_u16(c3, divisor=100.0, label="C3")
            cct_value = self._decode_uniform_u16(c2, divisor=1.0, label="C2")
            cct = round(cct_value) if cct_value is not None else None

            return SchneiderControlState(
                is_on=is_on,
                brightness_percent=brightness,
                color_temp_kelvin=cct,
                automatic_mode=automatic,
                nightlight_mode=nightlight,
                zone_mask=zone_mask,
                raw_control=control,
            )

        return await self._run_gatt_operation(_read)

    @staticmethod
    def _decode_uniform_u16(
        payload: bytes, *, divisor: float, label: str
    ) -> float | None:
        """Decode all 16-bit slots and warn if the cabinet reports mixed values."""
        if len(payload) < 2 or len(payload) % 2:
            return None
        values = [
            int.from_bytes(payload[index : index + 2], "big")
            for index in range(0, len(payload), 2)
        ]
        if len(set(values)) != 1:
            _LOGGER.warning(
                "Schneider %s returned mixed 16-bit slots: %s", label, values
            )
        return values[0] / divisor

    async def _write_control(self, payload: bytes) -> bytes:
        """Write one captured C6 control payload on the reusable connection.

        The real-hardware zone and HCL sweeps accepted C6 directly without CE=AF01,
        and the latency benchmark measured a direct C6 write at ~59 ms. Keep the CE
        preamble only for the still-experimental night-light command. A standalone
        C6 write does not prove that C2/C3 are session-primed, so brightness/CCT will
        initialize their own manual session on the next write.
        """

        async def _write(client: BleakClientWithServiceCache) -> bytes:
            if payload == CONTROL_NIGHTLIGHT:
                await client.write_gatt_char(CHAR_SESSION, SESSION_INIT, response=True)
            await client.write_gatt_char(CHAR_CONTROL, payload, response=True)
            self._manual_session_zone_mask = None
            _LOGGER.debug("Schneider C6 write: %s", payload.hex(" "))
            return payload

        return await self._run_gatt_operation(_write)

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
        """Apply global brightness/CCT in one resilient GATT transaction.

        Real-hardware sweep results:
        - C2 must be written as all four 16-bit slots (8 bytes). A 4-byte C2 write
          changed only the first two slots and left the remaining two stale.
        - C3 accepts 4 bytes, but the verified 8-byte form also works for every
          tested value from 1 to 100 %. Using 8 bytes for both characteristics
          gives deterministic state across all slots and avoids preliminary reads.
        - C6 preserves the currently active zone mask instead of forcing both lights.
        """
        if brightness_percent is None and color_temp_kelvin is None:
            await self.set_zone_mask(zone_mask, automatic=False)
            return None, None

        zone_mask &= ZONE_ALL
        if zone_mask == 0:
            zone_mask = ZONE_ALL

        brightness_payload = None
        cct_payload = None

        if brightness_percent is not None:
            percent = max(1.0, min(100.0, float(brightness_percent)))
            encoded = round(percent * 100).to_bytes(2, "big")
            brightness_payload = encoded * 4

        if color_temp_kelvin is not None:
            kelvin = max(2000, min(6500, int(color_temp_kelvin)))
            encoded = kelvin.to_bytes(2, "big")
            cct_payload = encoded * 4

        async def _write(client: BleakClientWithServiceCache) -> tuple[bytes | None, bytes | None]:
            # The direct latency benchmark proved that once CE=AF01 + the manual C6
            # mask have initialized a live connection, subsequent C2/C3 writes can
            # be sent directly. This cuts slider writes to tens of milliseconds.
            if self._manual_session_zone_mask != zone_mask:
                await client.write_gatt_char(CHAR_SESSION, SESSION_INIT, response=True)
                await client.write_gatt_char(
                    CHAR_CONTROL, self._manual_control(zone_mask), response=True
                )
                self._manual_session_zone_mask = zone_mask

            if brightness_payload is not None:
                await client.write_gatt_char(
                    CHAR_BRIGHTNESS, brightness_payload, response=True
                )
            if cct_payload is not None:
                await client.write_gatt_char(CHAR_CCT, cct_payload, response=True)
            return brightness_payload, cct_payload

        return await self._run_gatt_operation(_write)

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
