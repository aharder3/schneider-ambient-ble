from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .ble import SchneiderBleClient
from .const import DOMAIN, PLATFORMS
from .device import SchneiderAmbientDevice
from .helpers import normalize_device_name

_LOGGER = logging.getLogger(__name__)


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

    # Remove stale registry entries from earlier development layouts so the device
    # page only contains the current two zone lights and mode switches.
    entity_registry = er.async_get(hass)
    legacy_base = entry.unique_id or entry.entry_id
    for platform, unique_id in (
        ("number", f"{legacy_base}_brightness"),
        ("number", f"{legacy_base}_color_temperature"),
        ("switch", f"{legacy_base}_power_experimental"),
        ("light", f"{legacy_base}_light"),
    ):
        entity_id = entity_registry.async_get_entity_id(platform, DOMAIN, unique_id)
        if entity_id is not None:
            entity_registry.async_remove(entity_id)

    client = SchneiderBleClient(hass, address)
    runtime = SchneiderAmbientDevice(client)
    entry.runtime_data = runtime

    try:
        await runtime.async_refresh()
    except Exception:  # noqa: BLE001
        _LOGGER.debug(
            "Could not read initial Schneider/WSC state during setup", exc_info=True
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities and release the cached runtime BLE connection."""
    runtime = entry.runtime_data
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and isinstance(runtime, SchneiderAmbientDevice):
        await runtime.client.async_shutdown()
    return unload_ok
