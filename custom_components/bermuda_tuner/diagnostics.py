"""Diagnostics for Bermuda Tuner."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .manager import TunerManager


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry):
    """Return redacted settings and observations."""
    manager = TunerManager(hass)
    observations = await manager.dump()
    return manager.redact(
        {
            "tuner_options": dict(entry.options),
            "bermuda_settings": manager.current_settings(),
            "observations": observations,
            "privacy": "MAC addresses and IRKs are removed; AI is never called by diagnostics.",
        }
    )
