from __future__ import annotations

import asyncio
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
        # Home Assistant can issue multiple service calls very quickly (for example
        # brightness + CCT + zone changes from one light card). Keep those operations
        # ordered so an ESPHome Bluetooth proxy never receives overlapping GATT work.
        self._operation_lock = asyncio.Lock()

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
        async with self._operation_lock:
            state = await self.client.read_control_state()
        self._apply_control_state(state)
        self._notify()

    async def async_turn_off(self) -> None:
        async with self._operation_lock:
            await self.client.set_main_power(False)
        self.state.is_on = False
        self.state.zone_mask = 0
        self.state.automatic_mode = False
        self.state.nightlight_mode = False
        self._notify()

    async def async_turn_on_zone(
        self,
        zone_bit: int,
        *,
        brightness_percent: float | None = None,
        color_temp_kelvin: int | None = None,
    ) -> None:
        """Turn on one zone and optionally set the shared brightness/CCT.

        Power is per-zone, but C2/C3 are cabinet-global. Exposing C2/C3 on both
        Home Assistant light entities provides the natural UI while keeping the
        real hardware model intact.
        """
        if self.state.zone_mask is None:
            await self.async_refresh()

        current_mask = self.state.zone_mask or 0
        target_mask = (current_mask | zone_bit) & ZONE_ALL

        async with self._operation_lock:
            if brightness_percent is None and color_temp_kelvin is None:
                await self.client.set_zone_mask(
                    target_mask,
                    automatic=self.state.automatic_mode is True,
                )
            else:
                # The captured interactive brightness/CCT path is manual. Preserve
                # which zones are currently on instead of forcing both zones on.
                await self.client.apply_manual_light_state(
                    brightness_percent=brightness_percent,
                    color_temp_kelvin=color_temp_kelvin,
                    zone_mask=target_mask,
                )

        self.state.zone_mask = target_mask
        self.state.is_on = target_mask != 0
        self.state.nightlight_mode = False
        if brightness_percent is not None or color_temp_kelvin is not None:
            self.state.automatic_mode = False
        if brightness_percent is not None:
            self.state.brightness_percent = max(1.0, min(100.0, brightness_percent))
        if color_temp_kelvin is not None:
            self.state.color_temp_kelvin = max(2000, min(6500, color_temp_kelvin))
        self._notify()

    async def async_set_zone(self, zone_bit: int, enabled: bool) -> None:
        if self.state.zone_mask is None:
            await self.async_refresh()

        current_mask = self.state.zone_mask or 0
        target_mask = (
            current_mask | zone_bit if enabled else current_mask & ~zone_bit
        ) & ZONE_ALL

        automatic = self.state.automatic_mode is True and target_mask != 0
        async with self._operation_lock:
            await self.client.set_zone_mask(target_mask, automatic=automatic)

        self.state.zone_mask = target_mask
        self.state.is_on = target_mask != 0
        self.state.nightlight_mode = False
        if target_mask == 0:
            self.state.automatic_mode = False
        self._notify()

    async def async_set_automatic_mode(self, enabled: bool) -> None:
        zone_mask = self.state.zone_mask or ZONE_ALL
        async with self._operation_lock:
            await self.client.set_automatic_mode(enabled, zone_mask=zone_mask)
        self.state.zone_mask = zone_mask
        self.state.is_on = True
        self.state.automatic_mode = enabled
        self.state.nightlight_mode = False
        self._notify()

    async def async_set_nightlight_mode(self, enabled: bool) -> None:
        async with self._operation_lock:
            await self.client.set_nightlight_mode(enabled)
        self.state.nightlight_mode = enabled
        self.state.automatic_mode = False
        self.state.is_on = False
        self.state.zone_mask = 0
        self._notify()
