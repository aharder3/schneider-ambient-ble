from __future__ import annotations

import asyncio
import logging
from typing import Any, override

import voluptuous as vol
from bleak_retry_connector import BleakClientWithServiceCache

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .ble import SchneiderBleClient
from .const import DOMAIN, SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

# Manual setup first discovers the already-advertising WSC device, then opens a
# real GATT connection. Only after that connection succeeds does the flow ask the
# user to press the cabinet's physical pairing/learn button.
DISCOVERY_SCAN_SECONDS = 8.0
SETUP_CONNECTION_HOLD_SECONDS = 90.0


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
        self._connect_task: asyncio.Task[BleakClientWithServiceCache] | None = None
        self._initialize_task: asyncio.Task[None] | None = None
        self._setup_client: BleakClientWithServiceCache | None = None
        self._disconnect_watchdog: asyncio.Task[None] | None = None

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle automatic Bluetooth discovery and connect before prompting."""
        if not _is_supported(discovery_info):
            return self.async_abort(reason="not_supported")

        self._discovery_info = discovery_info
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": _device_name(discovery_info)}
        self._connect_task = None
        return await self.async_step_connect()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start manual setup by discovering the cabinet before any button press."""
        self._discovered_devices = {}
        self._scan_task = None
        return await self.async_step_scan()

    async def _async_scan_for_devices(self) -> None:
        """Run a fresh active scan, then collect matching connectable devices."""
        await bluetooth.async_request_active_scan(
            self.hass, duration=DISCOVERY_SCAN_SECONDS
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
        """Discover a WSC device before asking for the physical button press."""
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
        """Select a device from the pre-pairing discovery scan."""
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
        """Store one discovered device and connect to it before prompting the user."""
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

    async def _async_open_setup_connection(self) -> BleakClientWithServiceCache:
        """Open the GATT connection that precedes the physical-button prompt."""
        assert self._discovery_info is not None
        client = SchneiderBleClient(self.hass, self._discovery_info.address)
        return await client.open_connection()

    async def _async_close_setup_client(self) -> None:
        """Close any setup connection without masking the original flow result."""
        client = self._setup_client
        self._setup_client = None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Error while closing Schneider setup connection", exc_info=True)

    async def _async_disconnect_after_timeout(self) -> None:
        """Avoid leaking a GATT connection if the confirmation dialog is abandoned."""
        try:
            await asyncio.sleep(SETUP_CONNECTION_HOLD_SECONDS)
            await self._async_close_setup_client()
        except asyncio.CancelledError:
            raise

    def _start_disconnect_watchdog(self) -> None:
        """Start a bounded hold window for the setup connection."""
        if self._disconnect_watchdog is not None:
            self._disconnect_watchdog.cancel()
        self._disconnect_watchdog = self.hass.async_create_task(
            self._async_disconnect_after_timeout(),
            "Schneider Ambient setup connection timeout",
        )

    def _cancel_disconnect_watchdog(self) -> None:
        """Cancel the setup-connection hold timer."""
        if self._disconnect_watchdog is not None:
            self._disconnect_watchdog.cancel()
            self._disconnect_watchdog = None

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Establish GATT first; only then show the physical-button confirmation."""
        assert self._discovery_info is not None

        if self._connect_task is None:
            await self._async_close_setup_client()
            self._connect_task = self.hass.async_create_task(
                self._async_open_setup_connection(),
                "Schneider Ambient pre-pairing connection",
            )

        if not self._connect_task.done():
            return self.async_show_progress(
                step_id="connect",
                progress_action="connecting",
                progress_task=self._connect_task,
            )

        try:
            self._setup_client = self._connect_task.result()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not establish Schneider/WSC GATT connection")
            self._setup_client = None
            return self.async_show_progress_done(next_step_id="connect_failed")

        self._start_disconnect_watchdog()
        return self.async_show_progress_done(next_step_id="pairing_confirm")

    async def async_step_pairing_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt only after Home Assistant has successfully connected to WSC."""
        assert self._discovery_info is not None

        if user_input is not None:
            self._cancel_disconnect_watchdog()
            self._initialize_task = None
            return await self.async_step_initialize()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="pairing_confirm",
            description_placeholders={
                "name": self.context["title_placeholders"]["name"]
            },
        )

    async def _async_initialize_after_button(self) -> None:
        """After confirmation, initialize over the established/recovered connection."""
        assert self._discovery_info is not None

        client = self._setup_client
        if client is None or not client.is_connected:
            # If the cabinet or proxy dropped the link while the user was pressing
            # the button, reconnect automatically before replaying the observed app
            # initialization. The important setup order remains: a successful GATT
            # connection was established before the button prompt was shown.
            await self._async_close_setup_client()
            helper = SchneiderBleClient(self.hass, self._discovery_info.address)
            client = await helper.open_connection()
            self._setup_client = client

        helper = SchneiderBleClient(self.hass, self._discovery_info.address)
        try:
            await helper.initialize_connected_client(client)
        finally:
            await self._async_close_setup_client()

    async def async_step_initialize(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Apply the observed Schneider initialization after the button press."""
        if self._initialize_task is None:
            self._initialize_task = self.hass.async_create_task(
                self._async_initialize_after_button(),
                "Schneider Ambient post-button initialization",
            )

        if not self._initialize_task.done():
            return self.async_show_progress(
                step_id="initialize",
                progress_action="initializing",
                progress_task=self._initialize_task,
            )

        try:
            self._initialize_task.result()
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Schneider/WSC initialization failed after physical-button confirmation"
            )
            return self.async_show_progress_done(next_step_id="initialize_failed")

        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry only after connect -> button -> initialization succeeds."""
        assert self._discovery_info is not None
        self._cancel_disconnect_watchdog()
        await self._async_close_setup_client()
        return self.async_create_entry(
            title=_device_name(self._discovery_info),
            data={CONF_ADDRESS: self._discovery_info.address},
        )

    async def async_step_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user retry discovery before any pairing-button instruction."""
        if user_input is not None:
            self._scan_task = None
            self._discovered_devices = {}
            return await self.async_step_scan()

        self._set_confirm_only()
        return self.async_show_form(step_id="no_devices")

    async def async_step_connect_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retry the pre-pairing GATT connection without asking for the button yet."""
        if user_input is not None:
            self._connect_task = None
            return await self.async_step_connect()

        self._set_confirm_only()
        return self.async_show_form(step_id="connect_failed")

    async def async_step_initialize_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retry from a fresh connection and repeat the button step."""
        if user_input is not None:
            self._initialize_task = None
            self._connect_task = None
            await self._async_close_setup_client()
            return await self.async_step_connect()

        self._set_confirm_only()
        return self.async_show_form(step_id="initialize_failed")
