from __future__ import annotations

import asyncio

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothReachabilityIntent
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import CHAR_DATE, CHAR_SESSION, CHAR_TIME, SESSION_INIT


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
    async def initialize_connected_client(
        client: BleakClientWithServiceCache,
    ) -> None:
        """Replay the non-secret session initialization observed in PacketLogger.

        The physical pairing/learn prompt is intentionally handled by the config
        flow *after* a GATT connection has already been established. Once the user
        confirms the button press, this method sends the observed application-level
        initialization: current local date to C4, current local time to C5, then
        AF 01 to CE.

        The captured session contains no BLE SMP pairing exchange or link-encryption
        event, so this integration deliberately does not invent BleakClient.pair().
        """
        now = dt_util.now()
        await client.write_gatt_char(
            CHAR_DATE,
            bytes([now.year % 100, now.month, now.day]),
            response=True,
        )

        await asyncio.sleep(0.05)

        now = dt_util.now()
        await client.write_gatt_char(
            CHAR_TIME,
            bytes([now.hour, now.minute, now.second]),
            response=True,
        )

        await asyncio.sleep(0.25)
        await client.write_gatt_char(CHAR_SESSION, SESSION_INIT, response=True)

    async def initialize_session(self) -> None:
        """Connect, replay the observed initialization, then disconnect."""
        client = await self.open_connection()
        try:
            await self.initialize_connected_client(client)
        finally:
            await client.disconnect()

    async def write(self, characteristic: str, payload: bytes) -> None:
        """Connect, initialize, perform one ATT Write Request, then disconnect."""
        client = await self.open_connection()
        try:
            await self.initialize_connected_client(client)
            # PacketLogger shows ATT opcode 0x12 (Write Request), so response=True
            # matches the official app's observed behavior.
            await client.write_gatt_char(characteristic, payload, response=True)
        finally:
            await client.disconnect()
