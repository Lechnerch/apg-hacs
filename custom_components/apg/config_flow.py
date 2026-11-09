"""Config flow for the Austrian Power Grid (APG) integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApgApiClient, ApgApiError, ApgAuthError
from .const import (
    CONF_POWERMONITOR_SLUGS,
    CONF_POWERMONITOR_TOKEN,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MIN_SCAN_INTERVAL_MINUTES,
    POWERMONITOR_SLUGS,
)

_SLUG_OPTIONS = [
    selector.SelectOptionDict(value=slug, label=label)
    for slug, label in POWERMONITOR_SLUGS.items()
]


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the (shared) config/options schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_SCAN_INTERVAL_MINUTES,
                default=defaults.get(
                    CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL_MINUTES,
                    max=360,
                    step=5,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_POWERMONITOR_TOKEN,
                description={
                    "suggested_value": defaults.get(CONF_POWERMONITOR_TOKEN, "")
                },
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_POWERMONITOR_SLUGS,
                default=defaults.get(CONF_POWERMONITOR_SLUGS, []),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_SLUG_OPTIONS,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }
    )


async def _validate(hass, user_input: dict[str, Any]) -> dict[str, str]:
    """Validate user input; return a mapping of errors (empty if OK)."""
    errors: dict[str, str] = {}
    token = (user_input.get(CONF_POWERMONITOR_TOKEN) or "").strip()
    slugs = user_input.get(CONF_POWERMONITOR_SLUGS) or []

    if slugs and not token:
        errors[CONF_POWERMONITOR_TOKEN] = "token_required"
        return errors

    if token and slugs:
        client = ApgApiClient(async_get_clientsession(hass))
        try:
            await client.async_get_powermonitor(slugs[0], token)
        except ApgAuthError:
            errors[CONF_POWERMONITOR_TOKEN] = "invalid_auth"
        except ApgApiError:
            # Network/other issues should not block setup of the peak-hour part.
            errors["base"] = "powermonitor_unavailable"
    return errors


class ApgConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        # Only a single instance is useful: both APIs are nationwide.
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title="Austrian Power Grid",
                    data={},
                    options=_clean(user_input),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ApgOptionsFlow()


class ApgOptionsFlow(OptionsFlow):
    """Handle options (reconfiguration after setup)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(data=_clean(user_input))

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(user_input or dict(self.config_entry.options)),
            errors=errors,
        )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalise stored options (trim token, coerce interval to int)."""
    cleaned = dict(user_input)
    token = (cleaned.get(CONF_POWERMONITOR_TOKEN) or "").strip()
    if token:
        cleaned[CONF_POWERMONITOR_TOKEN] = token
    else:
        cleaned.pop(CONF_POWERMONITOR_TOKEN, None)
        cleaned[CONF_POWERMONITOR_SLUGS] = []
    if CONF_SCAN_INTERVAL_MINUTES in cleaned:
        cleaned[CONF_SCAN_INTERVAL_MINUTES] = int(cleaned[CONF_SCAN_INTERVAL_MINUTES])
    return cleaned
