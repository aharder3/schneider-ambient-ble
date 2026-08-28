from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .ble import SchneiderBleClient, SchneiderControlState
from .const import ZONE_ALL


@dataclass
class SchneiderState:
    """Cached state shared by all Schneider entities."""

    is_on: bool | None = None
    brightness_percent: float | None = None
    color_temp_kelvin: int | None = None
    automatic_mode: bool | None = None
    nightlight_mode: bool | None = None
    zone_mask: int | None = None


class SchneiderAmbientDevice:
    """Coordinate one WSC cabinet across Home Assistant entities."""

    def __init__(self, client: SchneiderBleClient) -> None:
        self.client = client
        self.state = SchneiderState()
        self._listeners: set[Callable[[], None]] = set()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)

        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def _apply_control_state(self, state: SchneiderControlState) -> None:
        self.state.is_on = state.is_on
        self.state.brightness_percent = state.brightness_percent
        self.state.color_temp_kelvin = state.color_temp_kelvin
        self.state.automatic_mode = state.automatic_mode
        self.state.nightlight_mode = state.nightlight_mode
        self.state.zone_mask = state.zone_mask

    async def async_refresh(self) -> None:
        self._apply_control_state(await self.client.read_control_state())
        self._notify()

    async def async_turn_off(self) -> None:
        await self.client.set_main_power(False)
        self.state.is_on = False
        self.state.zone_mask = 0
        self.state.automatic_mode = False
        self.state.nightlight_mode = False
        self._notify()

    async def async_turn_on(
        self,
        *,
        brightness_percent: float | None = None,
        color_temp_kelvin: int | None = None,
    ) -> None:
        if brightness_percent is None and color_temp_kelvin is None:
            await self.client.set_main_power(
                True, automatic=self.state.automatic_mode is True
            )
        else:
            # Brightness and CCT are global for both main lights. Their captured
            # interactive path is manual, so changing either leaves HCL/nightlight.
            active_mask = self.state.zone_mask or ZONE_ALL
            await self.client.apply_manual_light_state(
                brightness_percent=brightness_percent,
                color_temp_kelvin=color_temp_kelvin,
                zone_mask=active_mask,
            )
            self.state.automatic_mode = False
            self.state.nightlight_mode = False
            self.state.zone_mask = active_mask

        self.state.is_on = True
        if brightness_percent is None and color_temp_kelvin is None:
            self.state.zone_mask = ZONE_ALL
        if brightness_percent is not None:
            self.state.brightness_percent = max(10.0, brightness_percent)
        if color_temp_kelvin is not None:
            self.state.color_temp_kelvin = color_temp_kelvin
        self._notify()

    async def async_set_zone(self, zone_bit: int, enabled: bool) -> None:
        if self.state.zone_mask is None:
            await self.async_refresh()
        current_mask = self.state.zone_mask or 0
        target_mask = (
            current_mask | zone_bit if enabled else current_mask & ~zone_bit
        ) & ZONE_ALL

        automatic = self.state.automatic_mode is True and target_mask != 0
        await self.client.set_zone_mask(target_mask, automatic=automatic)

        self.state.zone_mask = target_mask
        self.state.is_on = target_mask != 0
        self.state.nightlight_mode = False
        if target_mask == 0:
            self.state.automatic_mode = False
        self._notify()

    async def async_set_automatic_mode(self, enabled: bool) -> None:
        zone_mask = self.state.zone_mask or ZONE_ALL
        await self.client.set_automatic_mode(enabled, zone_mask=zone_mask)
        self.state.zone_mask = zone_mask
        self.state.is_on = True
        self.state.automatic_mode = enabled
        self.state.nightlight_mode = False
        self._notify()

    async def async_set_nightlight_mode(self, enabled: bool) -> None:
        await self.client.set_nightlight_mode(enabled)
        self.state.nightlight_mode = enabled
        self.state.automatic_mode = False
        self.state.is_on = False
        self.state.zone_mask = 0
        self._notify()
