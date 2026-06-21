"""Config flow for Bermuda Tuner."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .analyzer import (
    audit,
    balance_scanners,
    calibrate_attenuation,
    calibrate_reference_power,
    explain_settings,
    walk_test,
)
from .const import BERMUDA_DOMAIN, CONF_AI_ENABLED, CONF_CONVERSATION_AGENT, DOMAIN
from .manager import TunerManager


class BermudaTunerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up one Bermuda Tuner instance."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Audit prerequisites and create the tuner."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if not self.hass.config_entries.async_entries(BERMUDA_DOMAIN):
            return self.async_abort(reason="bermuda_required")
        if user_input is not None:
            return self.async_create_entry(title="Bermuda Tuner", data={}, options=user_input)
        schema = vol.Schema(
            {
                vol.Optional(CONF_AI_ENABLED, default=False): bool,
                vol.Optional(CONF_CONVERSATION_AGENT): selector.ConversationAgentSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BermudaTunerOptionsFlow()


class BermudaTunerOptionsFlow(config_entries.OptionsFlow):
    """Provide a menu-driven tuning wizard."""

    _pending_patch: dict[str, Any] | None = None

    def _result(self, title: str, result: Any):
        self._result_title = title
        self._result_text = str(result)
        return self.async_show_form(
            step_id="result",
            data_schema=vol.Schema({}),
            description_placeholders={"title": title, "result": self._result_text},
        )

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "audit",
                "one_meter",
                "distance",
                "balance",
                "walk_test",
                "explain",
                "apply",
                "rollback",
                "ai",
            ],
        )

    async def async_step_result(self, user_input=None):
        """Return to the wizard menu after showing a result."""
        if user_input is not None:
            return await self.async_step_init()
        return self._result(self._result_title, self._result_text)

    async def async_step_audit(self, user_input=None):
        manager = TunerManager(self.hass)
        return self._result("Setup audit", audit(await manager.dump()))

    async def async_step_one_meter(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="one_meter",
                data_schema=vol.Schema(
                    {
                        vol.Optional("device_address", default=""): str,
                        vol.Optional("scanner", default=""): str,
                    }
                ),
            )
        manager = TunerManager(self.hass)
        dump = await manager.dump(user_input["device_address"])
        advert = manager.select_adverts(dump, user_input["scanner"])[0]
        return self._result("One-metre calibration", calibrate_reference_power(advert))

    async def async_step_distance(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="distance",
                data_schema=vol.Schema(
                    {
                        vol.Optional("device_address", default=""): str,
                        vol.Optional("scanner", default=""): str,
                        vol.Required("measured_distance", default=5.0): vol.All(
                            vol.Coerce(float), vol.Range(min=1.01)
                        ),
                        vol.Required("reference_power", default=-55.0): vol.All(
                            vol.Coerce(float), vol.Range(min=-120, max=-1)
                        ),
                    }
                ),
            )
        manager = TunerManager(self.hass)
        dump = await manager.dump(user_input["device_address"])
        advert = manager.select_adverts(dump, user_input["scanner"])[0]
        return self._result(
            "Distance calibration",
            calibrate_attenuation(
                advert, user_input["measured_distance"], user_input["reference_power"]
            ),
        )

    async def async_step_balance(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="balance",
                data_schema=vol.Schema({vol.Optional("device_address", default=""): str}),
            )
        manager = TunerManager(self.hass)
        dump = await manager.dump(user_input["device_address"])
        return self._result("Scanner balancing", balance_scanners(manager.select_adverts(dump)))

    async def async_step_walk_test(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="walk_test",
                data_schema=vol.Schema(
                    {
                        vol.Optional("device_address", default=""): str,
                        vol.Optional("ambiguity_db", default=4.0): vol.All(
                            vol.Coerce(float), vol.Range(min=0, max=30)
                        ),
                    }
                ),
            )
        manager = TunerManager(self.hass)
        dump = await manager.dump(user_input["device_address"])
        result = walk_test(manager.select_adverts(dump), user_input["ambiguity_db"])
        return self._result("Walk test", result)

    async def async_step_explain(self, user_input=None):
        manager = TunerManager(self.hass)
        return self._result("Plain-English settings", explain_settings(manager.current_settings()))

    async def async_step_apply(self, user_input=None):
        manager = TunerManager(self.hass)
        if user_input is None:
            return self.async_show_form(
                step_id="apply",
                data_schema=vol.Schema({vol.Required("settings"): selector.ObjectSelector()}),
            )
        self._pending_patch = dict(user_input["settings"])
        before = manager.current_settings()
        changes = {
            key: {"from": before.get(key), "to": value}
            for key, value in self._pending_patch.items()
        }
        return self.async_show_form(
            step_id="confirm_apply",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={"result": str(changes)},
        )

    async def async_step_confirm_apply(self, user_input=None):
        if user_input is None:
            return await self.async_step_apply()
        if not user_input["confirm"]:
            return await self.async_step_init()
        manager = TunerManager(self.hass)
        return self._result("Settings applied", await manager.apply(self._pending_patch or {}))

    async def async_step_rollback(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="rollback",
                data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            )
        if not user_input["confirm"]:
            return await self.async_step_init()
        return self._result("Rollback complete", await TunerManager(self.hass).rollback())

    async def async_step_ai(self, user_input=None):
        """Configure optional AI explanations."""
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            return self.async_create_entry(title="", data={**current, **user_input})
        return self.async_show_form(
            step_id="ai",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_AI_ENABLED,
                        default=current.get(CONF_AI_ENABLED, False),
                    ): bool,
                    vol.Optional(
                        CONF_CONVERSATION_AGENT,
                        default=current.get(CONF_CONVERSATION_AGENT),
                    ): selector.ConversationAgentSelector(),
                }
            ),
        )
