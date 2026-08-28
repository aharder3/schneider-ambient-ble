from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ble import SchneiderBleClient
from .const import CHAR_CONTROL

POWER_ON_EXPERIMENTAL = bytes([0x01, 0x00, 0x03, 0x00])
POWER_OFF = bytes([0x00, 0x00, 0x00, 0x00])


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = SchneiderBleClient(hass, entry.data[CONF_ADDRESS])
    async_add_entities([SchneiderPowerSwitch(entry, client)])


class SchneiderPowerSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Power (experimental)"
    _attr_icon = "mdi:mirror-rectangle"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry: ConfigEntry, client: SchneiderBleClient) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.unique_id}_power_experimental"
        self._attr_device_info = {
            "identifiers": {("schneider_ambient", entry.unique_id or entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Schneider",
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self._client.write(CHAR_CONTROL, POWER_ON_EXPERIMENTAL)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.write(CHAR_CONTROL, POWER_OFF)
        self._attr_is_on = False
        self.async_write_ha_state()
