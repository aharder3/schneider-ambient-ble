from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ZONE_LOWER, ZONE_UPPER
from .device import SchneiderAmbientDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the two separately switchable cabinet lights.

    The WSC protocol has separate on/off bits for the upper and lower light, while
    brightness and tunable-white colour temperature are global. Home Assistant
    therefore exposes the global brightness/CCT controls on *both* light entities.
    Changing either entity updates the shared values for both physical lights.
    """
    device: SchneiderAmbientDevice = entry.runtime_data
    async_add_entities(
        [
            SchneiderZoneLight(entry, device, ZONE_UPPER, "upper_light"),
            SchneiderZoneLight(entry, device, ZONE_LOWER, "lower_light"),
        ]
    )


class SchneiderZoneLight(LightEntity):
    """One separately switchable WSC light with shared brightness/CCT controls."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_min_color_temp_kelvin = 2000
    _attr_max_color_temp_kelvin = 6500

    def __init__(
        self,
        entry: ConfigEntry,
        device: SchneiderAmbientDevice,
        zone_bit: int,
        translation_key: str,
    ) -> None:
        self._device = device
        self._zone_bit = zone_bit
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{translation_key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.unique_id or entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Schneider",
            "model": "Ambient Lighting / WSC",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._device.add_listener(self.async_write_ha_state))

    @property
    def is_on(self) -> bool | None:
        zone_mask = self._device.state.zone_mask
        if zone_mask is None:
            return None
        return bool(zone_mask & self._zone_bit)

    @property
    def brightness(self) -> int | None:
        """Return the cabinet-global brightness on both zone entities."""
        percent = self._device.state.brightness_percent
        if percent is None:
            return None
        return round(max(0.0, min(100.0, percent)) * 255 / 100)

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the cabinet-global CCT on both zone entities."""
        return self._device.state.color_temp_kelvin

    async def async_update(self) -> None:
        await self._device.async_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness_percent = None
        color_temp_kelvin = None

        if ATTR_BRIGHTNESS in kwargs:
            # Direct hardware sweep confirmed 1..100 %. Zero is represented by
            # the separate C6 off command instead of a C3 brightness of zero.
            brightness_percent = max(1.0, kwargs[ATTR_BRIGHTNESS] * 100 / 255)

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            color_temp_kelvin = round(kwargs[ATTR_COLOR_TEMP_KELVIN])

        await self._device.async_turn_on_zone(
            self._zone_bit,
            brightness_percent=brightness_percent,
            color_temp_kelvin=color_temp_kelvin,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._device.async_set_zone(self._zone_bit, False)
