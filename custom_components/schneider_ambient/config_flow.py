from __future__ import annotations

import asyncio
import logging
from typing import Any, override

import voluptuous as vol
from bleak_retry_connector import BleakClientWithServiceCache

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import device_registry as dr

from .ble import SchneiderAuthorizationTimeout, SchneiderBleClient
from .const import DOMAIN, SERVICE_UUID
from .helpers import DEFAULT_DEVICE_NAME, normalize_device_name

_LOGGER = logging.getLogger(__name__)

DISCOVERY_SCAN_SECONDS = 10.0


def _device_name(discovery_info: BluetoothServiceInfoBleak) -> str:
    """Return a stable display name for a discovered cabinet."""
    return normalize_device_name(discovery_info.name)


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
        self._connect_task: asyncio.Task[BleakClientWithServiceCache] | None = None
        self._authorization_task: asyncio.Task[bytes] | None = None
        self._sync_task: asyncio.Task[None] | None = None
        self._setup_client: BleakClientWithServiceCache | None = None
        self._last_error = "No additional error information"

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle automatic Bluetooth discovery without connecting unsolicited."""
        if not _is_supported(discovery_info):
            return self.async_abort(reason="not_supported")

        self._discovery_info = discovery_info
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": _device_name(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether the automatically discovered cabinet should be configured."""
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

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start manual setup by discovering the already-advertising WSC device."""
        # A manual flow starts before a Bluetooth device name is known. Give the
        # flow a stable title immediately so Home Assistant's final create-entry
        # screen never renders "Created configuration for .".
        self.context["title_placeholders"] = {"name": DEFAULT_DEVICE_NAME}
        self._discovered_devices = {}
        self._scan_task = None
        return await self.async_step_scan()

    async def _async_scan_for_devices(self) -> None:
        """Run a fresh active scan, then collect matching connectable devices."""
        await bluetooth.async_request_active_scan(
            self.hass, duration=DISCOVERY_SCAN_SECONDS
        )

        found: dict[str, BluetoothServiceInfoBleak] = {}
        for discovery_info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            address = discovery_info.address
            if address in found:
                continue
            if _is_supported(discovery_info):
                found[address] = discovery_info

        self._discovered_devices = found

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover WSC before opening the pairing/authorization connection."""
        if self._scan_task is None:
            self._scan_task = self.hass.async_create_task(
                self._async_scan_for_devices(),
                "Schneider Ambient discovery scan",
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
        """Select one discovered WSC device."""
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
        """Select an address and then open the GATT connection."""
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

    async def _async_close_setup_client(self) -> None:
        """Close the setup connection without masking the flow result."""
        client = self._setup_client
        self._setup_client = None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Error while closing Schneider setup connection", exc_info=True)

    async def _async_open_setup_connection(self) -> BleakClientWithServiceCache:
        """Connect exactly before the physical-button polling stage."""
        assert self._discovery_info is not None
        helper = SchneiderBleClient(self.hass, self._discovery_info.address)
        return await helper.open_connection()

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Establish GATT before waiting for the physical cabinet button."""
        assert self._discovery_info is not None

        if self._connect_task is None:
            await self._async_close_setup_client()
            self._connect_task = self.hass.async_create_task(
                self._async_open_setup_connection(),
                "Schneider Ambient authorization connection",
            )

        if not self._connect_task.done():
            return self.async_show_progress(
                step_id="connect",
                progress_action="connecting",
                progress_task=self._connect_task,
            )

        try:
            self._setup_client = self._connect_task.result()
        except Exception as err:  # noqa: BLE001
            self._last_error = f"{type(err).__name__}: {err}"
            _LOGGER.exception("Could not establish Schneider/WSC GATT connection")
            self._setup_client = None
            return self.async_show_progress_done(next_step_id="connect_failed")

        self._authorization_task = None
        return self.async_show_progress_done(next_step_id="wait_for_button")

    async def _async_wait_for_button(self) -> bytes:
        """Poll C6 on the existing connection until the cabinet confirms the button."""
        client = self._setup_client
        if client is None or not client.is_connected:
            raise RuntimeError("Schneider setup connection was lost before authorization")
        return await SchneiderBleClient.wait_for_physical_authorization(client)

    async def async_step_wait_for_button(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the physical-button instruction while C6 is polled every 0.5 s."""
        if self._authorization_task is None:
            self._authorization_task = self.hass.async_create_task(
                self._async_wait_for_button(),
                "Schneider Ambient wait for physical authorization",
            )

        if not self._authorization_task.done():
            return self.async_show_progress(
                step_id="wait_for_button",
                progress_action="waiting_for_button",
                progress_task=self._authorization_task,
            )

        try:
            value = self._authorization_task.result()
            _LOGGER.debug(
                "Schneider physical authorization confirmed by C6: %s",
                value.hex(" "),
            )
        except SchneiderAuthorizationTimeout as err:
            self._last_error = str(err)
            _LOGGER.warning("Timed out waiting for Schneider physical button: %s", err)
            await self._async_close_setup_client()
            return self.async_show_progress_done(next_step_id="button_timeout")
        except Exception as err:  # noqa: BLE001
            self._last_error = f"{type(err).__name__}: {err}"
            _LOGGER.exception("Schneider authorization polling failed")
            await self._async_close_setup_client()
            return self.async_show_progress_done(next_step_id="connect_failed")

        self._sync_task = None
        return self.async_show_progress_done(next_step_id="sync")

    async def _async_sync_authorized_cabinet(self) -> None:
        """Read current state and sync date/time on the still-open authorized link."""
        client = self._setup_client
        if client is None or not client.is_connected:
            raise RuntimeError("Schneider setup connection was lost after authorization")
        await SchneiderBleClient.sync_after_authorization(client)

    async def async_step_sync(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Mirror the official app's post-button reads and clock sync."""
        if self._sync_task is None:
            self._sync_task = self.hass.async_create_task(
                self._async_sync_authorized_cabinet(),
                "Schneider Ambient post-authorization sync",
            )

        if not self._sync_task.done():
            return self.async_show_progress(
                step_id="sync",
                progress_action="syncing",
                progress_task=self._sync_task,
            )

        try:
            self._sync_task.result()
        except Exception as err:  # noqa: BLE001
            self._last_error = f"{type(err).__name__}: {err}"
            _LOGGER.exception("Schneider post-authorization state/clock sync failed")
            await self._async_close_setup_client()
            return self.async_show_progress_done(next_step_id="sync_failed")

        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry only after the captured authorization sequence succeeds."""
        assert self._discovery_info is not None
        title = _device_name(self._discovery_info)
        self.context["title_placeholders"] = {"name": title}
        await self._async_close_setup_client()

        _LOGGER.info(
            "Schneider Ambient BLE setup completed: title=%r address=%s",
            title,
            self._discovery_info.address,
        )

        # Give the create-entry screen an explicit localized success message.
        # Home Assistant's generic fallback uses the flow result title and can
        # otherwise render as "Created configuration for ." when the frontend
        # has not associated a device with the just-created entry yet.
        return self.async_create_entry(
            title=title,
            data={CONF_ADDRESS: self._discovery_info.address},
            description="success",
            description_placeholders={"name": title},
        )

    @override
    async def async_on_create_entry(
        self, result: ConfigFlowResult
    ) -> ConfigFlowResult:
        """Finalize the entry and device before the frontend renders success.

        This hook runs after Home Assistant has created the ConfigEntry but before
        the finished config-flow result is returned to the frontend. Registering
        the device here avoids a race where the create-entry screen sees zero
        devices and falls back to the generic "Created configuration for ..."
        message.
        """
        entry = result.get("result")
        if not isinstance(entry, ConfigEntry):
            return result

        title = normalize_device_name(entry.title)
        address = entry.data.get(CONF_ADDRESS)
        identifier = entry.unique_id or address or entry.entry_id

        if entry.title != title:
            self.hass.config_entries.async_update_entry(entry, title=title)

        # Make the final FlowResult itself explicit as well. The frontend uses
        # result.title in its generic completion fallback.
        result["title"] = title
        result["description"] = "success"
        result["description_placeholders"] = {"name": title}

        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, identifier)},
            connections={(dr.CONNECTION_BLUETOOTH, address)} if address else set(),
            name=title,
            manufacturer="Schneider",
            model="Ambient Lighting / WSC",
        )

        _LOGGER.info(
            "Schneider Ambient BLE final flow result: title=%r entry_id=%s address=%s",
            title,
            entry.entry_id,
            address,
        )
        return result

    async def async_step_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user retry discovery."""
        if user_input is not None:
            self._scan_task = None
            self._discovered_devices = {}
            return await self.async_step_scan()

        self._set_confirm_only()
        return self.async_show_form(step_id="no_devices")

    async def async_step_connect_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retry GATT connection without asking for the physical button first."""
        if user_input is not None:
            self._connect_task = None
            self._authorization_task = None
            await self._async_close_setup_client()
            return await self.async_step_connect()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="connect_failed",
            description_placeholders={"error": self._last_error},
        )

    async def async_step_button_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retry the exact connect -> C6-poll sequence after a button timeout."""
        if user_input is not None:
            self._connect_task = None
            self._authorization_task = None
            await self._async_close_setup_client()
            return await self.async_step_connect()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="button_timeout",
            description_placeholders={"error": self._last_error},
        )

    async def async_step_sync_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retry the whole authorization path if post-button sync fails."""
        if user_input is not None:
            self._connect_task = None
            self._authorization_task = None
            self._sync_task = None
            await self._async_close_setup_client()
            return await self.async_step_connect()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="sync_failed",
            description_placeholders={"error": self._last_error},
        )
