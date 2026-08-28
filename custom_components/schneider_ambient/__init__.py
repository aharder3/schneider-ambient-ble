from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .helpers import normalize_device_name


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Schneider Ambient BLE and repair invalid legacy titles."""
    normalized_title = normalize_device_name(entry.title)
    if normalized_title != entry.title:
        hass.config_entries.async_update_entry(entry, title=normalized_title)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
