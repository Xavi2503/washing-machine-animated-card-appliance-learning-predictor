"""Button platform for Appliance Learning Predictor."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .predictor import AppliancePredictor


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up predictor buttons."""
    runtime: AppliancePredictor = entry.runtime_data
    async_add_entities([ResetLearningButton(runtime, entry)])


class ResetLearningButton(ButtonEntity):
    """Clear learned cycle history for one configured appliance."""

    _attr_has_entity_name = True
    _attr_translation_key = "reset_learning"
    _attr_icon = "mdi:brain"

    def __init__(self, runtime: AppliancePredictor, entry: ConfigEntry) -> None:
        self.runtime = runtime
        self._attr_unique_id = f"{entry.entry_id}_reset_learning"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": runtime.name,
            "manufacturer": "Community",
            "model": f"Learning predictor ({runtime.appliance_type})",
        }

    async def async_press(self) -> None:
        """Reset learned history."""
        await self.runtime.async_reset_history()
