from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS
from .helpers import normalize_device_name


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Schneider Ambient BLE and register the cabinet immediately."""
    normalized_title = normalize_device_name(entry.title)
    if normalized_title != entry.title:
        hass.config_entries.async_update_entry(entry, title=normalized_title)

    address = entry.data.get(CONF_ADDRESS)
    identifier = entry.unique_id or address or entry.entry_id

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, identifier)},
        connections={(dr.CONNECTION_BLUETOOTH, address)} if address else set(),
        name=normalized_title,
        manufacturer="Schneider",
        model="Ambient Lighting / WSC",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
