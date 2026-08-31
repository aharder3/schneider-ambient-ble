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

from .ble import (
    SchneiderAuthorizationTimeout,
    SchneiderBleClient,
    SchneiderUnexpectedAuthorizationState,
)
from .const import DOMAIN, SERVICE_UUID
from .helpers import DEFAULT_DEVICE_NAME, normalize_device_name

_LOGGER = logging.getLogger(__name__)

DISCOVERY_SCAN_SECONDS = 8.0
CONF_DISPLAY_NAME = "display_name"
RESCAN_OPTION = "__rescan__"


def _device_name(discovery_info: BluetoothServiceInfoBleak) -> str:
    return normalize_device_name(discovery_info.name)


def _is_supported(discovery_info: BluetoothServiceInfoBleak) -> bool:
    service_uuids = {uuid.lower() for uuid in discovery_info.service_uuids}
    name = (discovery_info.name or "").strip().upper()
    return SERVICE_UUID in service_uuids or name.startswith("WSC")


class SchneiderAmbientConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle Schneider/WSC first authorization using a visible button step."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._scan_task: asyncio.Task[None] | None = None
        self._connect_task: asyncio.Task[BleakClientWithServiceCache] | None = None
        self._verify_task: asyncio.Task[bytes] | None = None
        self._sync_task: asyncio.Task[None] | None = None
        self._setup_client: BleakClientWithServiceCache | None = None
        self._last_error = "No additional error information"
        self._configured_name: str | None = None

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
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
        assert self._discovery_info is not None
        if user_input is not None:
            return await self.async_step_name()

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
        self.context["title_placeholders"] = {"name": DEFAULT_DEVICE_NAME}
        self._discovered_devices = {}
        self._scan_task = None
        return await self.async_step_scan()

    async def _async_scan_for_devices(self) -> None:
        """Collect all connectable Bluetooth devices visible to Home Assistant.

        Manual setup deliberately does not pre-filter the list to WSC advertising.
        Some proxies/adapters can expose a device without the local name or service UUID
        being present in the latest advertisement. The selected device is validated by
        the real WSC GATT reads during the following connection step instead.
        """
        await bluetooth.async_request_active_scan(
            self.hass, duration=DISCOVERY_SCAN_SECONDS
        )
        found: dict[str, BluetoothServiceInfoBleak] = {}
        for discovery_info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            if discovery_info.address in found:
                continue
            found[discovery_info.address] = discovery_info
        self._discovered_devices = found

    @staticmethod
    def _device_choice_label(discovery_info: BluetoothServiceInfoBleak) -> str:
        """Return a useful label for the manual Bluetooth picker."""
        raw_name = (discovery_info.name or "").strip()
        name = raw_name if raw_name else "Unknown Bluetooth device"
        prefix = "✓ Schneider/WSC — " if _is_supported(discovery_info) else ""
        rssi = getattr(discovery_info, "rssi", None)
        suffix = f" — {rssi} dBm" if isinstance(rssi, (int, float)) else ""
        return f"{prefix}{name} ({discovery_info.address}){suffix}"

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
        """Always show a manual Bluetooth device picker."""
        if not self._discovered_devices:
            return await self.async_step_no_devices()

        if user_input is not None:
            selected = user_input[CONF_ADDRESS]
            if selected == RESCAN_OPTION:
                self._scan_task = None
                self._discovered_devices = {}
                return await self.async_step_scan()
            return await self._async_use_selected_address(selected)

        def sort_key(item: tuple[str, BluetoothServiceInfoBleak]) -> tuple[int, float, str]:
            _address, info = item
            supported_rank = 0 if _is_supported(info) else 1
            rssi = getattr(info, "rssi", None)
            signal_rank = -float(rssi) if isinstance(rssi, (int, float)) else 9999.0
            name = (info.name or "").casefold()
            return supported_rank, signal_rank, name

        choices: dict[str, str] = {RESCAN_OPTION: "↻ Scan again / Erneut suchen"}
        for address, info in sorted(self._discovered_devices.items(), key=sort_key):
            choices[address] = self._device_choice_label(info)

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(choices)}),
        )

    async def _async_use_selected_address(self, address: str) -> ConfigFlowResult:
        discovery_info = self._discovered_devices.get(address)
        if discovery_info is None:
            discovery_info = bluetooth.async_last_service_info(
                self.hass, address, connectable=True
            )
        if discovery_info is None:
            return await self.async_step_no_devices()

        # Do not reject a manually selected device solely because its latest
        # advertisement is missing WSC/local-name or service-UUID metadata. The
        # next step validates the device by connecting and reading the proprietary
        # C1/C6 characteristics. This makes manual selection useful with proxies
        # that expose incomplete advertisements.
        await self.async_set_unique_id(address, raise_on_progress=False)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        suggested = _device_name(discovery_info) if _is_supported(discovery_info) else DEFAULT_DEVICE_NAME
        self.context["title_placeholders"] = {"name": suggested}
        return await self.async_step_name()

    async def async_step_name(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose the Home Assistant device name before BLE setup."""
        assert self._discovery_info is not None

        suggested_name = self._configured_name or DEFAULT_DEVICE_NAME
        errors: dict[str, str] = {}

        if user_input is not None:
            entered_name = str(user_input.get(CONF_DISPLAY_NAME, "")).strip()
            if (
                not entered_name
                or len(entered_name) > 64
                or not any(character.isalnum() for character in entered_name)
            ):
                errors[CONF_DISPLAY_NAME] = "invalid_name"
            else:
                self._configured_name = entered_name
                self.context["title_placeholders"] = {"name": entered_name}
                self._connect_task = None
                return await self.async_step_connect()

        return self.async_show_form(
            step_id="name",
            data_schema=vol.Schema(
                {vol.Required(CONF_DISPLAY_NAME, default=suggested_name): str}
            ),
            errors=errors,
        )

    async def _async_close_setup_client(self) -> None:
        client = self._setup_client
        self._setup_client = None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Error closing Schneider setup connection", exc_info=True)

    async def _async_open_setup_connection(self) -> BleakClientWithServiceCache:
        assert self._discovery_info is not None
        helper = SchneiderBleClient(self.hass, self._discovery_info.address)
        return await helper.open_connection()

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect first, then prove C6 is non-authorized before showing the form."""
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
            _, initial_c6 = await SchneiderBleClient.read_pre_authorization_state(
                self._setup_client
            )
            if SchneiderBleClient.is_authorized(initial_c6):
                raise SchneiderUnexpectedAuthorizationState(
                    "C6 already contained 0x55 before the physical-button prompt: "
                    f"{initial_c6.hex(' ')}"
                )
        except Exception as err:  # noqa: BLE001
            self._last_error = f"{type(err).__name__}: {err}"
            if self._discovery_info is not None and not _is_supported(self._discovery_info):
                self._last_error += (
                    ". The device was selected manually and did not advertise as WSC; "
                    "verify that the selected Bluetooth device is the Schneider mirror cabinet"
                )
            _LOGGER.exception("Could not prepare Schneider/WSC authorization")
            await self._async_close_setup_client()
            return self.async_show_progress_done(next_step_id="connect_failed")

        # IMPORTANT: this is a real form, not a progress message. It remains visible
        # until the user physically presses the cabinet button and clicks Continue.
        return self.async_show_progress_done(next_step_id="press_button")

    async def async_step_press_button(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Keep a visible instruction on screen while the GATT link is open."""
        if user_input is None:
            self._set_confirm_only()
            return self.async_show_form(step_id="press_button", last_step=False)

        if self._setup_client is None or not self._setup_client.is_connected:
            self._last_error = (
                "Bluetooth/GATT connection was lost while waiting for the button press"
            )
            await self._async_close_setup_client()
            return await self.async_step_connection_lost()

        self._verify_task = None
        return await self.async_step_verify_button()

    async def _async_verify_button(self) -> bytes:
        client = self._setup_client
        if client is None or not client.is_connected:
            raise RuntimeError("Schneider setup connection was lost")
        return await SchneiderBleClient.wait_for_authorization_marker(client)

    async def async_step_verify_button(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """After Continue, verify that C6 changed to 0x55."""
        if self._verify_task is None:
            self._verify_task = self.hass.async_create_task(
                self._async_verify_button(),
                "Schneider Ambient verify physical button",
            )

        if not self._verify_task.done():
            return self.async_show_progress(
                step_id="verify_button",
                progress_action="verifying_button",
                progress_task=self._verify_task,
            )

        try:
            value = self._verify_task.result()
            _LOGGER.info("Schneider authorization confirmed by C6=%s", value.hex(" "))
        except SchneiderAuthorizationTimeout as err:
            self._last_error = str(err)
            return self.async_show_progress_done(next_step_id="button_not_confirmed")
        except Exception as err:  # noqa: BLE001
            self._last_error = f"{type(err).__name__}: {err}"
            _LOGGER.exception("Schneider button verification failed")
            await self._async_close_setup_client()
            return self.async_show_progress_done(next_step_id="connect_failed")

        self._sync_task = None
        return self.async_show_progress_done(next_step_id="sync")

    async def _async_sync_authorized_cabinet(self) -> None:
        client = self._setup_client
        if client is None or not client.is_connected:
            raise RuntimeError("Schneider setup connection was lost after authorization")
        await SchneiderBleClient.sync_after_authorization(client)

    async def async_step_sync(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
            _LOGGER.exception("Schneider post-authorization sync failed")
            await self._async_close_setup_client()
            return self.async_show_progress_done(next_step_id="sync_failed")
        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery_info is not None
        title = normalize_device_name(
            self._configured_name or _device_name(self._discovery_info)
        )
        self.context["title_placeholders"] = {"name": title}
        await self._async_close_setup_client()
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
        entry = result.get("result")
        if not isinstance(entry, ConfigEntry):
            return result
        title = normalize_device_name(entry.title)
        address = entry.data.get(CONF_ADDRESS)
        identifier = entry.unique_id or address or entry.entry_id
        if entry.title != title:
            self.hass.config_entries.async_update_entry(entry, title=title)
        result["title"] = title
        result["description"] = "success"
        result["description_placeholders"] = {"name": title}
        dr.async_get(self.hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, identifier)},
            connections={(dr.CONNECTION_BLUETOOTH, address)} if address else set(),
            name=title,
            manufacturer="Schneider",
            model="Ambient Lighting / WSC",
        )
        return result

    async def async_step_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._scan_task = None
            self._discovered_devices = {}
            return await self.async_step_scan()
        self._set_confirm_only()
        return self.async_show_form(step_id="no_devices")

    async def async_step_connect_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._connect_task = None
            self._verify_task = None
            await self._async_close_setup_client()
            return await self.async_step_connect()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="connect_failed",
            description_placeholders={"error": self._last_error},
        )

    async def async_step_connection_lost(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._connect_task = None
            await self._async_close_setup_client()
            return await self.async_step_connect()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="connection_lost",
            description_placeholders={"error": self._last_error},
        )

    async def async_step_button_not_confirmed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Keep the same open connection and let the user press/retry again."""
        if user_input is not None:
            if self._setup_client is None or not self._setup_client.is_connected:
                self._last_error = "Bluetooth/GATT connection was lost"
                return await self.async_step_connection_lost()
            self._verify_task = None
            return await self.async_step_press_button()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="button_not_confirmed",
            description_placeholders={"error": self._last_error},
        )

    async def async_step_sync_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._connect_task = None
            self._verify_task = None
            self._sync_task = None
            await self._async_close_setup_client()
            return await self.async_step_connect()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="sync_failed",
            description_placeholders={"error": self._last_error},
        )
