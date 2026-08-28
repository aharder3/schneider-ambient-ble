from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device import SchneiderAmbientDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Schneider mode switches."""
    device: SchneiderAmbientDevice = entry.runtime_data
    async_add_entities(
        [
            SchneiderAutomaticModeSwitch(entry, device),
            SchneiderNightlightModeSwitch(entry, device),
        ]
    )


class _SchneiderModeSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, device: SchneiderAmbientDevice) -> None:
        self._device = device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.unique_id or entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Schneider",
            "model": "Ambient Lighting / WSC",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._device.add_listener(self.async_write_ha_state))

    async def async_update(self) -> None:
        await self._device.async_refresh()


class SchneiderAutomaticModeSwitch(_SchneiderModeSwitch):
    """Automatic/HCL mode from the capture-confirmed C6 0x02 format."""

    _attr_translation_key = "automatic_mode"
    _attr_icon = "mdi:theme-light-dark"

    def __init__(self, entry: ConfigEntry, device: SchneiderAmbientDevice) -> None:
        super().__init__(entry, device)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_automatic_mode"

    @property
    def is_on(self) -> bool | None:
        return self._device.state.automatic_mode

    async def async_turn_on(self, **kwargs) -> None:
        await self._device.async_set_automatic_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._device.async_set_automatic_mode(False)


class SchneiderNightlightModeSwitch(_SchneiderModeSwitch):
    """Night-light mode using the captured C6 00 00 00 02 command/state."""

    _attr_translation_key = "nightlight_mode"
    _attr_icon = "mdi:weather-night"

    def __init__(self, entry: ConfigEntry, device: SchneiderAmbientDevice) -> None:
        super().__init__(entry, device)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_nightlight_mode"

    @property
    def is_on(self) -> bool | None:
        return self._device.state.nightlight_mode

    async def async_turn_on(self, **kwargs) -> None:
        await self._device.async_set_nightlight_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._device.async_set_nightlight_mode(False)
