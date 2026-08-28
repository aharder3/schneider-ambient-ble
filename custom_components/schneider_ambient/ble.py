from __future__ import annotations

from bleak import BleakClient

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant


class SchneiderBleClient:
    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address

    async def write(self, characteristic: str, payload: bytes) -> None:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise RuntimeError("Schneider Ambient device is not reachable by a connectable Bluetooth adapter/proxy")

        async with BleakClient(ble_device) as client:
            await client.write_gatt_char(characteristic, payload, response=True)
