from __future__ import annotations

DEFAULT_DEVICE_NAME = "Schneider Ambient"


def normalize_device_name(name: str | None) -> str:
    """Return a stable human-readable device name.

    Some Bluetooth backends/proxies can surface an empty/whitespace-only or
    punctuation-only name even when the advertisement is otherwise valid. Do
    not use such values as Home Assistant config-entry/device titles.
    """
    if name is None:
        return DEFAULT_DEVICE_NAME

    cleaned = name.strip()
    if not cleaned:
        return DEFAULT_DEVICE_NAME

    if not any(character.isalnum() for character in cleaned):
        return DEFAULT_DEVICE_NAME

    return cleaned
