from __future__ import annotations

import asyncio
import logging
from typing import Any, override

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .ble import SchneiderBleClient
from .const import DOMAIN, SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

# The physical button appears to open the device-side discovery/authorization
# window. Keep the active scan long enough to catch the WSC advertisement after
# the user presses the button, while keeping the config flow responsive.
PAIRING_SCAN_SECONDS = 12.0


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
        self._scan_task: asyncio.Task[None] | None = None
        self._connect_task: asyncio.Task[None] | None = None
        self._connect_error: str | None = None

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
        """Start manual setup with the physical-button instruction first."""
        return await self.async_step_prepare_pairing(user_input)

    async def async_step_prepare_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to press the physical button before scanning."""
        if user_input is not None:
            self._discovered_devices = {}
            self._scan_task = None
            return await self.async_step_scan()

        self._set_confirm_only()
        return self.async_show_form(step_id="prepare_pairing")

    async def _async_scan_for_devices(self) -> None:
        """Run a fresh active scan, then collect matching connectable devices."""
        await bluetooth.async_request_active_scan(
            self.hass, duration=PAIRING_SCAN_SECONDS
        )

        current_ids = self._async_current_ids(include_ignore=False)
        found: dict[str, BluetoothServiceInfoBleak] = {}

        for discovery_info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            address = discovery_info.address
            if address in current_ids or address in found:
                continue
            if _is_supported(discovery_info):
                found[address] = discovery_info

        self._discovered_devices = found

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show progress while Home Assistant/proxies scan after the button press."""
        if self._scan_task is None:
            self._scan_task = self.hass.async_create_task(
                self._async_scan_for_devices(),
                "Schneider Ambient pairing scan",
            )

        if not self._scan_task.done():
            return self.async_show_progress(
                step_id="scan",
                progress_action="scanning",
                progress_task=self._scan_task,
            )

        try:
            self._scan_task.result()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Bluetooth scan for Schneider/WSC devices failed")
            self._discovered_devices = {}

        return self.async_show_progress_done(next_step_id="select_device")

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a device from the fresh post-button scan."""
        if not self._discovered_devices:
            return await self.async_step_no_devices()

        if user_input is not None:
            return await self._async_use_selected_address(user_input[CONF_ADDRESS])

        if len(self._discovered_devices) == 1:
            address = next(iter(self._discovered_devices))
            return await self._async_use_selected_address(address)

        choices = {
            address: f"{_device_name(info)} ({address})"
            for address, info in self._discovered_devices.items()
        }
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(choices)}),
        )

    async def _async_use_selected_address(self, address: str) -> ConfigFlowResult:
        """Store one discovered device and continue to the connection check."""
        discovery_info = self._discovered_devices.get(address)
        if discovery_info is None:
            discovery_info = bluetooth.async_last_service_info(
                self.hass, address, connectable=True
            )

        if discovery_info is None or not _is_supported(discovery_info):
            return await self.async_step_no_devices()

        await self.async_set_unique_id(address, raise_on_progress=False)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": _device_name(discovery_info)}
        self._connect_task = None
        return await self.async_step_connect()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm an automatically discovered cabinet before connecting."""
        assert self._discovery_info is not None

        if user_input is not None:
            self._connect_task = None
            return await self.async_step_connect()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self.context["title_placeholders"]["name"]
            },
        )

    async def _async_initialize_selected_device(self) -> None:
        """Connect and replay the app's observed date/time/session initialization."""
        assert self._discovery_info is not None
        client = SchneiderBleClient(self.hass, self._discovery_info.address)
        await client.initialize_session()

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verify connectivity and initialize the device before saving the entry."""
        assert self._discovery_info is not None

        if self._connect_task is None:
            self._connect_error = None
            self._connect_task = self.hass.async_create_task(
                self._async_initialize_selected_device(),
                "Schneider Ambient connection check",
            )

        if not self._connect_task.done():
            return self.async_show_progress(
                step_id="connect",
                progress_action="connecting",
                progress_task=self._connect_task,
            )

        try:
            self._connect_task.result()
        except Exception as err:  # noqa: BLE001
            self._connect_error = str(err)
            _LOGGER.exception(
                "Could not connect to or initialize Schneider/WSC device"
            )
            return self.async_show_progress_done(next_step_id="connect_failed")

        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry only after the connection/initialization check succeeds."""
        assert self._discovery_info is not None
        return self.async_create_entry(
            title=_device_name(self._discovery_info),
            data={CONF_ADDRESS: self._discovery_info.address},
        )

    async def async_step_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Keep the flow open and let the user retry the physical-button scan."""
        if user_input is not None:
            self._scan_task = None
            return await self.async_step_prepare_pairing()

        self._set_confirm_only()
        return self.async_show_form(step_id="no_devices")

    async def async_step_connect_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain a failed connection and offer a clean retry."""
        if user_input is not None:
            self._connect_task = None
            self._scan_task = None
            return await self.async_step_prepare_pairing()

        self._set_confirm_only()
        return self.async_show_form(step_id="connect_failed")
