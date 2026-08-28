from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ble import SchneiderBleClient
from .const import CHAR_BRIGHTNESS, CHAR_CCT


def _dup_be16(value: int) -> bytes:
    value = max(0, min(65535, int(value)))
    encoded = value.to_bytes(2, "big")
    return encoded + encoded


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    address = entry.data[CONF_ADDRESS]
    client = SchneiderBleClient(hass, address)
    async_add_entities(
        [
            SchneiderBrightnessNumber(entry, client),
            SchneiderColorTemperatureNumber(entry, client),
        ]
    )


class SchneiderNumberBase(NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: ConfigEntry, client: SchneiderBleClient) -> None:
        self._entry = entry
        self._client = client
        self._attr_device_info = {
            "identifiers": {("schneider_ambient", entry.unique_id or entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Schneider",
        }


class SchneiderBrightnessNumber(SchneiderNumberBase):
    _attr_name = "Brightness"
    _attr_icon = "mdi:brightness-6"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"

    def __init__(self, entry: ConfigEntry, client: SchneiderBleClient) -> None:
        super().__init__(entry, client)
        self._attr_unique_id = f"{entry.unique_id}_brightness"

    async def async_set_native_value(self, value: float) -> None:
        await self._client.write(CHAR_BRIGHTNESS, _dup_be16(round(value * 100)))
        self._attr_native_value = value
        self.async_write_ha_state()


class SchneiderColorTemperatureNumber(SchneiderNumberBase):
    _attr_name = "Color temperature"
    _attr_icon = "mdi:temperature-kelvin"
    _attr_native_min_value = 2000
    _attr_native_max_value = 6500
    _attr_native_step = 100
    _attr_native_unit_of_measurement = UnitOfTemperature.KELVIN

    def __init__(self, entry: ConfigEntry, client: SchneiderBleClient) -> None:
        super().__init__(entry, client)
        self._attr_unique_id = f"{entry.unique_id}_color_temperature"

    async def async_set_native_value(self, value: float) -> None:
        await self._client.write(CHAR_CCT, _dup_be16(round(value)))
        self._attr_native_value = value
        self.async_write_ha_state()
