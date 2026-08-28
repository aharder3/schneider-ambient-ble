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

    # v0.2.0 replaces the old separate Number + experimental Power entities with
    # one native Home Assistant light and an Automatic-mode switch. Remove stale
    # registry entries from development versions so the device page stays clean.
    entity_registry = er.async_get(hass)
    legacy_base = entry.unique_id or entry.entry_id
    for platform, unique_id in (
        ("number", f"{legacy_base}_brightness"),
        ("number", f"{legacy_base}_color_temperature"),
        ("switch", f"{legacy_base}_power_experimental"),
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
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
