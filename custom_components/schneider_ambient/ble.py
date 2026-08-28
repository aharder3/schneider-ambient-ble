from __future__ import annotations

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothReachabilityIntent
from homeassistant.core import HomeAssistant


class SchneiderBleClient:
    """Small write-only BLE client using Home Assistant's selected Bluetooth path."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address

    async def write(self, characteristic: str, payload: bytes) -> None:
        """Connect, perform one ATT Write Request, then disconnect."""
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            reason = bluetooth.async_address_reachability_diagnostics(
                self.hass,
                self.address,
                BluetoothReachabilityIntent.CONNECTION,
            )
            raise RuntimeError(
                "Schneider Ambient device is not reachable by a connectable "
                f"Bluetooth adapter/proxy. {reason}"
            )

        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            ble_device.name or "Schneider Ambient",
            max_attempts=3,
        )
        try:
            # PacketLogger shows ATT opcode 0x12 (Write Request), so response=True
            # matches the official app's observed behavior.
            await client.write_gatt_char(characteristic, payload, response=True)
        finally:
            await client.disconnect()
