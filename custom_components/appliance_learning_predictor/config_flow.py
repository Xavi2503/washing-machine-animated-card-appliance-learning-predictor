"""Config flow for Appliance Learning Predictor."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    APPLIANCE_TYPES,
    CONF_APPLIANCE_TYPE,
    CONF_DETECTION_MODE,
    CONF_ENERGY_ENTITY,
    CONF_MAX_LEARN_DURATION,
    CONF_POWER_ENTITY,
    CONF_RUNNING_STATES,
    CONF_START_DELAY,
    CONF_START_THRESHOLD,
    CONF_STATUS_ENTITY,
    CONF_STOP_DELAY,
    CONF_STOP_THRESHOLD,
    DEFAULT_MAX_LEARN_DURATION,
    DEFAULT_RUNNING_STATES,
    DEFAULT_START_DELAY,
    DEFAULT_START_THRESHOLD,
    DEFAULT_STOP_DELAY,
    DEFAULT_STOP_THRESHOLD,
    DETECTION_POWER,
    DETECTION_STATUS,
    DOMAIN,
)


def _base_schema(defaults: dict[str, Any] | None = None) -> probatio.Schema:
    defaults = defaults or {}
    return probatio.Schema(
        {
            probatio.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Washing machine")): TextSelector(
                TextSelectorConfig()
            ),
            probatio.Required(
                CONF_APPLIANCE_TYPE,
                default=defaults.get(CONF_APPLIANCE_TYPE, "washer"),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=APPLIANCE_TYPES,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="appliance_type",
                )
            ),
            (
                probatio.Required(CONF_POWER_ENTITY, default=defaults[CONF_POWER_ENTITY])
                if CONF_POWER_ENTITY in defaults
                else probatio.Required(CONF_POWER_ENTITY)
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            (
                probatio.Required(CONF_ENERGY_ENTITY, default=defaults[CONF_ENERGY_ENTITY])
                if CONF_ENERGY_ENTITY in defaults
                else probatio.Required(CONF_ENERGY_ENTITY)
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            probatio.Required(
                CONF_DETECTION_MODE,
                default=defaults.get(CONF_DETECTION_MODE, DETECTION_POWER),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[DETECTION_POWER, DETECTION_STATUS],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="detection_mode",
                )
            ),
        }
    )


def _power_schema(defaults: dict[str, Any] | None = None) -> probatio.Schema:
    defaults = defaults or {}
    return probatio.Schema(
        {
            probatio.Required(
                CONF_START_THRESHOLD,
                default=defaults.get(CONF_START_THRESHOLD, DEFAULT_START_THRESHOLD),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=10000,
                    step=1,
                    unit_of_measurement="W",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            probatio.Required(
                CONF_STOP_THRESHOLD,
                default=defaults.get(CONF_STOP_THRESHOLD, DEFAULT_STOP_THRESHOLD),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=1000,
                    step=0.1,
                    unit_of_measurement="W",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            probatio.Required(
                CONF_START_DELAY,
                default=defaults.get(CONF_START_DELAY, DEFAULT_START_DELAY),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=600,
                    step=1,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            probatio.Required(
                CONF_STOP_DELAY,
                default=defaults.get(CONF_STOP_DELAY, DEFAULT_STOP_DELAY),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=120,
                    step=1,
                    unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            probatio.Required(
                CONF_MAX_LEARN_DURATION,
                default=defaults.get(CONF_MAX_LEARN_DURATION, DEFAULT_MAX_LEARN_DURATION),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=30,
                    max=1440,
                    step=10,
                    unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _status_schema(defaults: dict[str, Any] | None = None) -> probatio.Schema:
    defaults = defaults or {}
    return probatio.Schema(
        {
            (
                probatio.Required(CONF_STATUS_ENTITY, default=defaults[CONF_STATUS_ENTITY])
                if CONF_STATUS_ENTITY in defaults
                else probatio.Required(CONF_STATUS_ENTITY)
            ): EntitySelector(
                EntitySelectorConfig(domain=["binary_sensor", "input_boolean", "sensor"])
            ),
            probatio.Required(
                CONF_RUNNING_STATES,
                default=defaults.get(CONF_RUNNING_STATES, DEFAULT_RUNNING_STATES),
            ): TextSelector(TextSelectorConfig()),
            probatio.Required(
                CONF_MAX_LEARN_DURATION,
                default=defaults.get(CONF_MAX_LEARN_DURATION, DEFAULT_MAX_LEARN_DURATION),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=30,
                    max=1440,
                    step=10,
                    unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


class ApplianceLearningPredictorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Start setup."""
        if user_input is not None:
            self._data.update(user_input)
            unique_id = f"{user_input[CONF_APPLIANCE_TYPE]}:{user_input[CONF_POWER_ENTITY]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            if user_input[CONF_DETECTION_MODE] == DETECTION_STATUS:
                return await self.async_step_status()
            return await self.async_step_power()

        return self.async_show_form(step_id="user", data_schema=_base_schema())

    async def async_step_power(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure automatic power-based cycle detection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if float(user_input[CONF_START_THRESHOLD]) <= float(user_input[CONF_STOP_THRESHOLD]):
                errors["base"] = "threshold_order"
            else:
                self._data.update(user_input)
                return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        return self.async_show_form(step_id="power", data_schema=_power_schema(), errors=errors)

    async def async_step_status(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure an existing status entity."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        return self.async_show_form(step_id="status", data_schema=_status_schema())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return ApplianceLearningPredictorOptionsFlow()


class ApplianceLearningPredictorOptionsFlow(OptionsFlow):
    """Handle editable settings."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit the common configuration."""
        if not self._data:
            self._data = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            self._data.update(user_input)
            if user_input[CONF_DETECTION_MODE] == DETECTION_STATUS:
                return await self.async_step_status()
            return await self.async_step_power()

        return self.async_show_form(step_id="init", data_schema=_base_schema(self._data))

    async def async_step_power(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if float(user_input[CONF_START_THRESHOLD]) <= float(user_input[CONF_STOP_THRESHOLD]):
                errors["base"] = "threshold_order"
            else:
                self._data.update(user_input)
                return self.async_create_entry(title="", data=self._data)
        return self.async_show_form(step_id="power", data_schema=_power_schema(self._data), errors=errors)

    async def async_step_status(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)
        return self.async_show_form(step_id="status", data_schema=_status_schema(self._data))
