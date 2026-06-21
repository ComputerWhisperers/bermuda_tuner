"""Bermuda Tuner integration."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .analyzer import (
    audit,
    balance_scanners,
    calibrate_attenuation,
    calibrate_reference_power,
    explain_settings,
    walk_test,
)
from .const import CONF_AI_ENABLED, CONF_CONVERSATION_AGENT, DOMAIN, TUNABLE_KEYS
from .manager import TunerManager


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bermuda Tuner and its response-returning actions."""
    manager = TunerManager(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    if hass.services.has_service(DOMAIN, "audit"):
        return True

    async def run(call: ServiceCall, operation: Callable[..., Any]) -> dict[str, Any]:
        try:
            dump = await manager.dump(str(call.data.get(CONF_DEVICE_ID, "")))
            adverts = manager.select_adverts(dump, str(call.data.get("scanner", "")))
            return manager.redact(operation(adverts, dump, call.data))
        except (ValueError, TypeError) as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_audit(call: ServiceCall):
        dump = await manager.dump()
        return manager.redact(audit(dump))

    async def handle_one_meter(call: ServiceCall):
        return await run(call, lambda adverts, _dump, _data: calibrate_reference_power(adverts[0]))

    async def handle_distance(call: ServiceCall):
        return await run(
            call,
            lambda adverts, _dump, data: calibrate_attenuation(
                adverts[0], data["measured_distance"], data["reference_power"]
            ),
        )

    async def handle_balance(call: ServiceCall):
        return await run(call, lambda adverts, _dump, _data: balance_scanners(adverts))

    async def handle_walk(call: ServiceCall):
        return await run(
            call, lambda adverts, _dump, data: walk_test(adverts, data["ambiguity_db"])
        )

    async def handle_explain(call: ServiceCall):
        return explain_settings(manager.current_settings())

    async def handle_preview(call: ServiceCall):
        patch = dict(call.data["settings"])
        unknown = set(patch) - TUNABLE_KEYS
        if unknown:
            raise HomeAssistantError(f"Unsupported setting(s): {', '.join(sorted(unknown))}")
        before = manager.current_settings()
        return {
            "before": before,
            "changes": {key: {"from": before[key], "to": value} for key, value in patch.items()},
        }

    async def handle_apply(call: ServiceCall):
        try:
            return await manager.apply(dict(call.data["settings"]))
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_rollback(call: ServiceCall):
        try:
            return await manager.rollback()
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_ai(call: ServiceCall):
        configured = {**entry.data, **entry.options}
        if not configured.get(CONF_AI_ENABLED):
            raise HomeAssistantError("AI explanations are disabled in Bermuda Tuner options")
        agent_id = call.data.get("agent_id") or configured.get(CONF_CONVERSATION_AGENT)
        if not agent_id:
            raise HomeAssistantError("Select a Home Assistant conversation agent first")
        dump = manager.redact(await manager.dump())
        report = audit(dump)
        prompt = (
            "Explain this redacted Bermuda Bluetooth coverage report to a beginner. "
            "Recommend placement or tuning checks, do not invent facts, and keep it concise. "
            f"Report: {json.dumps(report, separators=(',', ':'))}"
        )
        result = await conversation.async_converse(
            hass=hass,
            text=prompt,
            conversation_id=None,
            context=call.context,
            language=hass.config.language,
            agent_id=agent_id,
        )
        return {
            "agent_id": agent_id,
            "response": result.response.speech.get("plain", {}).get("speech", ""),
        }

    services = {
        "audit": (handle_audit, None),
        "calibrate_one_meter": (
            handle_one_meter,
            vol.Schema(
                {
                    vol.Optional(CONF_DEVICE_ID, default=""): cv.string,
                    vol.Optional("scanner", default=""): cv.string,
                }
            ),
        ),
        "calibrate_distance": (
            handle_distance,
            vol.Schema(
                {
                    vol.Optional(CONF_DEVICE_ID, default=""): cv.string,
                    vol.Optional("scanner", default=""): cv.string,
                    vol.Required("measured_distance"): vol.All(
                        vol.Coerce(float), vol.Range(min=1.01)
                    ),
                    vol.Required("reference_power"): vol.All(
                        vol.Coerce(float), vol.Range(min=-120, max=-1)
                    ),
                }
            ),
        ),
        "balance_scanners": (
            handle_balance,
            vol.Schema({vol.Optional(CONF_DEVICE_ID, default=""): cv.string}),
        ),
        "walk_test": (
            handle_walk,
            vol.Schema(
                {
                    vol.Optional(CONF_DEVICE_ID, default=""): cv.string,
                    vol.Optional("ambiguity_db", default=4): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=30)
                    ),
                }
            ),
        ),
        "explain_settings": (handle_explain, None),
        "preview": (handle_preview, vol.Schema({vol.Required("settings"): dict})),
        "apply": (handle_apply, vol.Schema({vol.Required("settings"): dict})),
        "rollback": (handle_rollback, None),
        "ask_ai": (handle_ai, vol.Schema({vol.Optional("agent_id"): cv.string})),
    }
    for name, (handler, schema) in services.items():
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=SupportsResponse.ONLY
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Bermuda Tuner."""
    hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data[DOMAIN]:
        for name in (
            "audit",
            "calibrate_one_meter",
            "calibrate_distance",
            "balance_scanners",
            "walk_test",
            "explain_settings",
            "preview",
            "apply",
            "rollback",
            "ask_ai",
        ):
            hass.services.async_remove(DOMAIN, name)
    return True
