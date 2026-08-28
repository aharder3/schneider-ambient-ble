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

    async def _connect(self) -> BleakClientWithServiceCache:
        """Connect via bleak-retry-connector using Home Assistant's BLEDevice."""
        ble_device = self._ble_device()
        return await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            ble_device.name or "Schneider Ambient",
            max_attempts=3,
        )

    @staticmethod
    async def _initialize_connected_client(
        client: BleakClientWithServiceCache,
    ) -> None:
        """Replay the non-secret session initialization observed in PacketLogger.

        The official iOS app writes the current local date to C4, the current local
        time to C5, then writes AF 01 to CE before the first lighting commands.
        The capture contains no BLE SMP pairing exchange or link-encryption event,
        so we deliberately do not call BleakClient.pair().
        """
        now = dt_util.now()
        await client.write_gatt_char(
            CHAR_DATE,
            bytes([now.year % 100, now.month, now.day]),
            response=True,
        )

        # The capture separates the date and time writes by only a few tens of ms.
        await asyncio.sleep(0.05)

        now = dt_util.now()
        await client.write_gatt_char(
            CHAR_TIME,
            bytes([now.hour, now.minute, now.second]),
            response=True,
        )

        # AF 01 follows after the initial state reads in the captured app session.
        # Its exact semantic name is still unknown, but replaying it mirrors the
        # observed app initialization without inventing an authentication secret.
        await asyncio.sleep(0.25)
        await client.write_gatt_char(CHAR_SESSION, SESSION_INIT, response=True)

    async def initialize_session(self) -> None:
        """Connect and verify the observed Schneider/WSC initialization sequence."""
        client = await self._connect()
        try:
            await self._initialize_connected_client(client)
        finally:
            await client.disconnect()

    async def write(self, characteristic: str, payload: bytes) -> None:
        """Connect, initialize the session, perform one ATT Write Request, disconnect."""
        client = await self._connect()
        try:
            await self._initialize_connected_client(client)
            # PacketLogger shows ATT opcode 0x12 (Write Request), so response=True
            # matches the official app's observed behavior.
            await client.write_gatt_char(characteristic, payload, response=True)
        finally:
            await client.disconnect()
