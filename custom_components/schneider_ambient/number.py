from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ble import SchneiderBleClient


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up confirmed/decoded Schneider lighting controls."""
    client = SchneiderBleClient(hass, entry.data[CONF_ADDRESS])

    brightness: float | None = None
    cct: int | None = None
    try:
        brightness, cct = await client.read_control_state()
    except Exception:  # noqa: BLE001
        # Entity setup must not fail just because the cabinet was temporarily busy.
        pass

    async_add_entities(
        [
            SchneiderBrightnessNumber(entry, client, brightness),
            SchneiderColorTemperatureNumber(entry, client, cct),
        ]
    )


class SchneiderNumberBase(NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, client: SchneiderBleClient) -> None:
        self._entry = entry
        self._client = client
        self._attr_device_info = {
            "identifiers": {("schneider_ambient", entry.unique_id or entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Schneider",
            "model": "Ambient Lighting / WSC",
        }


class SchneiderBrightnessNumber(SchneiderNumberBase):
    _attr_name = "Brightness"
    _attr_icon = "mdi:brightness-6"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"

    def __init__(
        self,
        entry: ConfigEntry,
        client: SchneiderBleClient,
        initial_value: float | None,
    ) -> None:
        super().__init__(entry, client)
        self._attr_unique_id = f"{entry.unique_id}_brightness"
        self._attr_native_value = initial_value

    async def async_set_native_value(self, value: float) -> None:
        await self._client.set_brightness_percent(value)
        self._attr_native_value = value
        self.async_write_ha_state()


class SchneiderColorTemperatureNumber(SchneiderNumberBase):
    _attr_name = "Color temperature"
    _attr_icon = "mdi:temperature-kelvin"
    _attr_native_min_value = 2000
    _attr_native_max_value = 6500
    _attr_native_step = 100
    _attr_native_unit_of_measurement = UnitOfTemperature.KELVIN

    def __init__(
        self,
        entry: ConfigEntry,
        client: SchneiderBleClient,
        initial_value: int | None,
    ) -> None:
        super().__init__(entry, client)
        self._attr_unique_id = f"{entry.unique_id}_color_temperature"
        self._attr_native_value = initial_value

    async def async_set_native_value(self, value: float) -> None:
        kelvin = round(value)
        await self._client.set_color_temperature_kelvin(kelvin)
        self._attr_native_value = kelvin
        self.async_write_ha_state()
