from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, SERVICE_UUID


def _device_name(discovery_info: BluetoothServiceInfoBleak) -> str:
    """Return a useful display name for a discovered cabinet."""
    return discovery_info.name or "Schneider Ambient"


def _is_supported(discovery_info: BluetoothServiceInfoBleak) -> bool:
    """Check whether a Bluetooth discovery looks like a supported cabinet."""
    service_uuids = {uuid.lower() for uuid in discovery_info.service_uuids}
    name = (discovery_info.name or "").strip().upper()
    return SERVICE_UUID in service_uuids or name.startswith("WSC")


class SchneiderAmbientConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Schneider Ambient BLE."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle automatic Bluetooth discovery."""
        if not _is_supported(discovery_info):
            return self.async_abort(reason="not_supported")

        self._discovery_info = discovery_info
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"name": _device_name(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user select a currently discovered Schneider/WSC device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices.get(address)

            if discovery_info is None:
                discovery_info = bluetooth.async_last_service_info(
                    self.hass, address, connectable=True
                )

            if discovery_info is None or not _is_supported(discovery_info):
                return self.async_abort(reason="device_not_found")

            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            self._discovery_info = discovery_info
            self.context["title_placeholders"] = {
                "name": _device_name(discovery_info)
            }
            return await self.async_step_bluetooth_confirm()

        # Ask all AUTO-mode scanners/proxies for a short active scan before reading
        # Home Assistant's discovery cache. This does not start a second Bleak scanner.
        await bluetooth.async_request_active_scan(self.hass)

        current_ids = self._async_current_ids(include_ignore=False)
        self._discovered_devices = {}

        for discovery_info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            address = discovery_info.address
            if address in current_ids or address in self._discovered_devices:
                continue
            if not _is_supported(discovery_info):
                continue
            self._discovered_devices[address] = discovery_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        choices = {
            address: f"{_device_name(info)} ({address})"
            for address, info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(choices)}),
        )

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered cabinet before creating the config entry."""
        assert self._discovery_info is not None

        if user_input is not None:
            return self.async_create_entry(
                title=_device_name(self._discovery_info),
                data={CONF_ADDRESS: self._discovery_info.address},
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self.context["title_placeholders"]["name"]
            },
        )
