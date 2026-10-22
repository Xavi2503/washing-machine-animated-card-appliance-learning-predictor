"""Sensor platform for Appliance Learning Predictor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ALGORITHM_VERSION, DOMAIN
from .predictor import AppliancePredictor


@dataclass(frozen=True, kw_only=True)
class PredictorSensorDescription(SensorEntityDescription):
    """Describe a predictor sensor."""


SENSORS: tuple[PredictorSensorDescription, ...] = (
    PredictorSensorDescription(
        key="remaining_time",
        translation_key="remaining_time",
        icon="mdi:timer-sand",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PredictorSensorDescription(
        key="expected_end",
        translation_key="expected_end",
        icon="mdi:clock-end",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    PredictorSensorDescription(
        key="expected_duration",
        translation_key="expected_duration",
        icon="mdi:timeline-clock-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PredictorSensorDescription(
        key="confidence",
        translation_key="confidence",
        icon="mdi:percent-circle-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PredictorSensorDescription(
        key="cycle_profile",
        translation_key="cycle_profile",
        icon="mdi:shape-outline",
    ),
    PredictorSensorDescription(
        key="learned_cycles",
        translation_key="learned_cycles",
        icon="mdi:brain",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up predictor sensors."""
    runtime: AppliancePredictor = entry.runtime_data
    async_add_entities(PredictorSensor(runtime, entry, description) for description in SENSORS)


class PredictorSensor(SensorEntity):
    """Representation of a predictor output."""

    _attr_has_entity_name = True

    def __init__(
        self,
        runtime: AppliancePredictor,
        entry: ConfigEntry,
        description: PredictorSensorDescription,
    ) -> None:
        self.runtime = runtime
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": runtime.name,
            "manufacturer": "Community",
            "model": f"Learning predictor ({runtime.appliance_type})",
        }
        self._remove_listener = None

    async def async_added_to_hass(self) -> None:
        """Register updates."""
        await super().async_added_to_hass()
        self._remove_listener = self.runtime.add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister updates."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        return self.runtime.values.get(self.entity_description.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "detection_mode": self.runtime.mode,
            "active_cycle": self.runtime.active,
            "source_power_entity": self.runtime.power_entity,
            "source_energy_entity": self.runtime.energy_entity,
        }
