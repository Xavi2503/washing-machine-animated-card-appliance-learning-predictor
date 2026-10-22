"""Learning and cycle-detection engine for Appliance Learning Predictor."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ALGORITHM_VERSION,
    BIAS_MAX_MINUTES,
    CHECKPOINT_MINUTES,
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
    MAX_ACTIVE_MINUTES,
    MAX_CYCLES,
    MIN_LEARN_DURATION,
    MIN_LEARN_ENERGY,
    PHASE_SHIFT_LIMIT,
    POLL_SECONDS,
    PROFILE_DURATION_TOLERANCE,
    PROFILE_ENERGY_TOLERANCE,
    STORAGE_VERSION,
    UNKNOWN_SCORE_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class AppliancePredictor:
    """Run cycle detection and remaining-time learning for one appliance."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config = {**entry.data, **entry.options}
        self.name = self.config.get(CONF_NAME, entry.title)
        self.appliance_type = self.config[CONF_APPLIANCE_TYPE]
        self.power_entity = self.config[CONF_POWER_ENTITY]
        self.energy_entity = self.config[CONF_ENERGY_ENTITY]
        self.mode = self.config[CONF_DETECTION_MODE]
        self.max_learn_duration = int(
            self.config.get(CONF_MAX_LEARN_DURATION, DEFAULT_MAX_LEARN_DURATION)
        )

        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._unsub_interval: Callable[[], None] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._started = False

        self.history: list[dict[str, Any]] = []
        self.active = False
        self.start_time: datetime | None = None
        self.energy_start = 0.0
        self.points: list[dict[str, float]] = []
        self.prediction_samples: list[dict[str, float]] = []
        self._last_checkpoint = 0
        self._power_sum = 0.0
        self._power_count = 0
        self._last_remaining: float | None = None
        self._last_prediction_elapsed = 0.0

        self._start_candidate: datetime | None = None
        self._start_candidate_energy: float | None = None
        self._stop_candidate: datetime | None = None
        self._stop_candidate_energy: float | None = None
        self._last_status_running = False

        self.values: dict[str, Any] = {
            "remaining_time": None,
            "expected_end": None,
            "expected_duration": None,
            "confidence": 0,
            "cycle_profile": "Waiting for cycle",
            "learned_cycles": 0,
        }

    async def async_start(self) -> None:
        """Load history and start polling."""
        stored = await self._store.async_load() or {}
        raw_history = stored.get("cycles", [])
        if isinstance(raw_history, list):
            self.history = self._sanitize_history(raw_history)
        self.values["learned_cycles"] = len(self.history)

        active = stored.get("active")
        if isinstance(active, dict):
            self._restore_active(active)

        self._last_status_running = self._status_entity_running() or False
        await self.async_evaluate(dt_util.now())
        self._unsub_interval = async_track_time_interval(
            self.hass, self.async_evaluate, timedelta(seconds=POLL_SECONDS)
        )
        self._started = True
        self._notify()

    async def async_stop(self) -> None:
        """Stop polling and persist data."""
        if self._unsub_interval is not None:
            self._unsub_interval()
            self._unsub_interval = None
        await self._store.async_save(self._serialize())
        self._started = False

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an entity update listener."""
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    async def async_evaluate(self, now: datetime | None = None) -> None:
        """Evaluate detection, sample an active cycle and refresh predictions."""
        now = now or dt_util.now()
        power = self._read_power_w()
        energy = self._read_energy_kwh()

        # Never treat unavailable/unknown source sensors as zero. Doing so could
        # falsely stop an active cycle and contaminate the learning history.
        if power is None or energy is None:
            self._notify()
            return

        if self.mode == DETECTION_STATUS:
            running = self._status_entity_running()
            if running is None:
                # A missing/unavailable status source is not the same as "not running".
                self._notify()
                return
            if running and not self.active:
                self._start_cycle(now, energy)
            elif not running and self.active:
                self._finish_cycle(now, energy)
            self._last_status_running = running
        else:
            self._evaluate_power_detection(now, power, energy)

        if self.active:
            self._sample_active(now, power, energy)

        self.values["learned_cycles"] = len(self.history)
        self._notify()

    def _evaluate_power_detection(self, now: datetime, power: float, energy: float) -> None:
        start_threshold = float(
            self.config.get(CONF_START_THRESHOLD, DEFAULT_START_THRESHOLD)
        )
        stop_threshold = float(self.config.get(CONF_STOP_THRESHOLD, DEFAULT_STOP_THRESHOLD))
        start_delay = float(self.config.get(CONF_START_DELAY, DEFAULT_START_DELAY))
        stop_delay = float(self.config.get(CONF_STOP_DELAY, DEFAULT_STOP_DELAY))

        if not self.active:
            self._stop_candidate = None
            self._stop_candidate_energy = None
            if power >= start_threshold:
                if self._start_candidate is None:
                    self._start_candidate = now
                    self._start_candidate_energy = energy
                if (now - self._start_candidate).total_seconds() >= start_delay:
                    start_time = self._start_candidate
                    start_energy = (
                        self._start_candidate_energy
                        if self._start_candidate_energy is not None
                        else energy
                    )
                    self._start_candidate = None
                    self._start_candidate_energy = None
                    self._start_cycle(start_time, start_energy)
            else:
                self._start_candidate = None
                self._start_candidate_energy = None
            return

        self._start_candidate = None
        self._start_candidate_energy = None
        if power <= stop_threshold:
            if self._stop_candidate is None:
                self._stop_candidate = now
                self._stop_candidate_energy = energy
            if (now - self._stop_candidate).total_seconds() >= stop_delay * 60:
                effective_end = self._stop_candidate
                effective_energy = (
                    self._stop_candidate_energy
                    if self._stop_candidate_energy is not None
                    else energy
                )
                self._stop_candidate = None
                self._stop_candidate_energy = None
                self._finish_cycle(effective_end, effective_energy)
        else:
            self._stop_candidate = None
            self._stop_candidate_energy = None

    def _start_cycle(self, when: datetime, energy: float) -> None:
        self.active = True
        self.start_time = when
        self.energy_start = energy
        self.points = []
        self.prediction_samples = []
        self._last_checkpoint = 0
        self._power_sum = 0.0
        self._power_count = 0
        self._last_remaining = None
        self._last_prediction_elapsed = 0.0
        self._stop_candidate = None
        self._stop_candidate_energy = None
        self.values.update(
            {
                "remaining_time": None,
                "expected_end": None,
                "expected_duration": None,
                "confidence": 0,
                "cycle_profile": "Learning" if not self.history else "Analyzing",
            }
        )
        self._schedule_save()
        _LOGGER.info("%s: cycle started", self.name)

    def _finish_cycle(self, when: datetime, energy: float) -> None:
        if not self.active or self.start_time is None:
            return

        duration = max(0.0, (when - self.start_time).total_seconds() / 60.0)
        used_energy = max(0.0, energy - self.energy_start)
        valid = (
            MIN_LEARN_DURATION <= duration <= self.max_learn_duration
            and used_energy >= MIN_LEARN_ENERGY
        )

        if valid:
            profile = self._assign_profile(duration, used_energy)
            errors: list[dict[str, float]] = []
            for sample in self.prediction_samples:
                elapsed = float(sample.get("m", 0))
                if elapsed > duration + 1:
                    continue
                predicted_remaining = float(sample.get("remaining", 0))
                actual_remaining = max(0.0, duration - elapsed)
                errors.append(
                    {"m": round(elapsed, 1), "error": round(actual_remaining - predicted_remaining, 2)}
                )

            cycle = {
                "duration": int(round(duration)),
                "energy": round(used_energy, 4),
                "profile": profile,
                "points": [p for p in self.points if p["m"] <= duration + 1],
                "errors": errors,
                "algorithm_version": ALGORITHM_VERSION,
            }
            self.history.append(cycle)
            self.history = self._sanitize_history(self.history)[-MAX_CYCLES:]
            self.values.update(
                {
                    "remaining_time": 0,
                    "expected_end": when,
                    "expected_duration": int(round(duration)),
                    "confidence": 100,
                    "cycle_profile": f"Profile {profile}",
                }
            )
            _LOGGER.info(
                "%s: learned cycle (%d min, %.3f kWh, profile %d)",
                self.name,
                round(duration),
                used_energy,
                profile,
            )
        else:
            if duration > self.max_learn_duration:
                reason = "Invalid long cycle"
            else:
                reason = "Cycle not learned"
            self.values.update(
                {
                    "remaining_time": 0,
                    "expected_end": when,
                    "expected_duration": int(round(duration)) if duration else None,
                    "confidence": 0,
                    "cycle_profile": reason,
                }
            )
            _LOGGER.warning(
                "%s: cycle not learned (%.1f min, %.3f kWh)",
                self.name,
                duration,
                used_energy,
            )

        self.active = False
        self.start_time = None
        self._stop_candidate = None
        self._stop_candidate_energy = None
        self.points = []
        self.prediction_samples = []
        self._last_remaining = None
        self._last_checkpoint = 0
        self.values["learned_cycles"] = len(self.history)
        self._schedule_save()

    def _sample_active(self, now: datetime, power: float, energy: float) -> None:
        if self.start_time is None:
            return
        elapsed = max(0.0, (now - self.start_time).total_seconds() / 60.0)
        if elapsed > MAX_ACTIVE_MINUTES:
            self.values.update(
                {
                    "remaining_time": None,
                    "expected_end": None,
                    "expected_duration": None,
                    "confidence": 0,
                    "cycle_profile": "Invalid runtime",
                }
            )
            return

        self._power_sum += max(0.0, power)
        self._power_count += 1
        cycle_energy = max(0.0, energy - self.energy_start)

        if elapsed >= CHECKPOINT_MINUTES and elapsed - self._last_checkpoint >= CHECKPOINT_MINUTES:
            avg_power = self._power_sum / max(1, self._power_count)
            self.points.append(
                {
                    "m": int(round(elapsed)),
                    "e": round(cycle_energy, 4),
                    "p": round(avg_power, 1),
                }
            )
            self._last_checkpoint = int(round(elapsed))
            self._power_sum = 0.0
            self._power_count = 0
            self._schedule_save()

        self._predict(now, elapsed, power, cycle_energy)

    def _predict(self, now: datetime, elapsed: float, power: float, energy: float) -> None:
        candidates: list[tuple[float, float, int]] = []
        for cycle in self.history:
            duration = float(cycle.get("duration", 0))
            if duration <= elapsed + 1:
                continue
            best: tuple[float, int] | None = None
            for shift in range(-PHASE_SHIFT_LIMIT, PHASE_SHIFT_LIMIT + 1, 5):
                score = self._match_score(cycle, shift, power, energy)
                if score is None:
                    continue
                if best is None or score < best[0]:
                    best = (score, shift)
            if best is None:
                continue
            score, shift = best
            remaining = max(0.0, duration - max(0.0, elapsed + shift))
            candidates.append((score, remaining, int(cycle.get("profile", 1))))

        if not candidates:
            if self.history:
                durations = sorted(float(c.get("duration", 0)) for c in self.history)
                median = durations[len(durations) // 2]
                remaining = max(0.0, median - elapsed)
                confidence = min(25, 8 + len(self.history) * 3)
                self._set_prediction(now, elapsed, remaining, confidence, "Analyzing")
            else:
                self.values.update(
                    {
                        "remaining_time": None,
                        "expected_end": None,
                        "expected_duration": None,
                        "confidence": 0,
                        "cycle_profile": "Learning",
                    }
                )
            return

        candidates.sort(key=lambda item: item[0])
        top = candidates[: min(6, len(candidates))]
        weighted = 0.0
        total_weight = 0.0
        profile_weights: dict[int, float] = {}
        for score, remaining, profile in top:
            weight = 1.0 / ((0.08 + score) ** 2)
            weighted += remaining * weight
            total_weight += weight
            profile_weights[profile] = profile_weights.get(profile, 0.0) + weight

        raw_remaining = weighted / max(total_weight, 0.001)
        raw_remaining += self._bias_for_elapsed(elapsed)
        raw_remaining = max(0.0, raw_remaining)
        raw_remaining = self._stabilize(elapsed, raw_remaining)

        best_score = top[0][0]
        winner = max(profile_weights, key=profile_weights.get)
        predicted_total = max(elapsed + raw_remaining, 1.0)
        progress = _clamp(elapsed / predicted_total, 0.0, 1.0)
        score_quality = _clamp(1.0 - best_score / 1.5, 0.0, 1.0)
        confidence = int(
            round(
                _clamp(
                    10 + score_quality * 55 + min(len(self.history), 8) * 3 + progress * 11,
                    10,
                    99,
                )
            )
        )
        if best_score > UNKNOWN_SCORE_THRESHOLD:
            profile_text = "New / unknown profile"
            confidence = min(confidence, 30)
        else:
            profile_text = f"Profile {winner}"

        self._set_prediction(now, elapsed, raw_remaining, confidence, profile_text)

    def _match_score(
        self, cycle: dict[str, Any], shift: int, current_power: float, current_energy: float
    ) -> float | None:
        hist_points = cycle.get("points", [])
        if not hist_points:
            return None

        current_points = self.points[-3:] if self.points else []
        comparisons: list[float] = []
        for point in current_points:
            target = float(point["m"]) + shift
            hist = self._nearest_point(hist_points, target)
            if hist is None:
                continue
            energy_diff = abs(float(point["e"]) - float(hist.get("e", 0))) / max(
                float(hist.get("e", 0)), 0.05
            )
            power_diff = abs(float(point["p"]) - float(hist.get("p", 0))) / max(
                float(hist.get("p", 0)), 80.0
            )
            comparisons.append(0.65 * min(energy_diff, 3.0) + 0.35 * min(power_diff, 3.0))

        if not comparisons:
            target = max(0.0, self._last_checkpoint + shift)
            hist = self._nearest_point(hist_points, target)
            if hist is None:
                return None
            energy_diff = abs(current_energy - float(hist.get("e", 0))) / max(
                float(hist.get("e", 0)), 0.05
            )
            power_diff = abs(current_power - float(hist.get("p", 0))) / max(
                float(hist.get("p", 0)), 80.0
            )
            comparisons.append(0.65 * min(energy_diff, 3.0) + 0.35 * min(power_diff, 3.0))

        return sum(comparisons) / len(comparisons) + abs(shift) * 0.008

    @staticmethod
    def _nearest_point(points: list[dict[str, Any]], minute: float) -> dict[str, Any] | None:
        if not points:
            return None
        best = min(points, key=lambda p: abs(float(p.get("m", 0)) - minute))
        if abs(float(best.get("m", 0)) - minute) > 7:
            return None
        return best

    def _bias_for_elapsed(self, elapsed: float) -> float:
        values: list[float] = []
        for cycle in self.history[-20:]:
            errors = cycle.get("errors", [])
            if not errors:
                continue
            nearest = min(errors, key=lambda e: abs(float(e.get("m", 0)) - elapsed))
            if abs(float(nearest.get("m", 0)) - elapsed) <= 15:
                values.append(float(nearest.get("error", 0)))
        if not values:
            return 0.0
        values.sort()
        median = values[len(values) // 2]
        return _clamp(median, -BIAS_MAX_MINUTES, BIAS_MAX_MINUTES)

    def _stabilize(self, elapsed: float, raw_remaining: float) -> float:
        if self._last_remaining is None:
            self._last_remaining = raw_remaining
            self._last_prediction_elapsed = elapsed
            return raw_remaining

        delta = max(0.0, elapsed - self._last_prediction_elapsed)
        expected = max(0.0, self._last_remaining - delta)
        predicted_total = max(elapsed + raw_remaining, 1.0)
        progress = elapsed / predicted_total
        allowance = 7.0 if progress < 0.33 else 4.0 if progress < 0.75 else 2.0
        stabilized = _clamp(raw_remaining, max(0.0, expected - allowance), expected + allowance)
        self._last_remaining = stabilized
        self._last_prediction_elapsed = elapsed
        return stabilized

    def _set_prediction(
        self, now: datetime, elapsed: float, remaining: float, confidence: int, profile: str
    ) -> None:
        remaining_int = max(0, int(round(remaining)))
        self.values.update(
            {
                "remaining_time": remaining_int,
                "expected_end": now + timedelta(minutes=remaining_int),
                "expected_duration": max(0, int(round(elapsed + remaining))),
                "confidence": confidence,
                "cycle_profile": profile,
            }
        )
        if not self.prediction_samples or elapsed - self.prediction_samples[-1]["m"] >= 5:
            self.prediction_samples.append(
                {"m": round(elapsed, 1), "remaining": float(remaining_int)}
            )

    def _assign_profile(self, duration: float, energy: float) -> int:
        profiles: dict[int, list[dict[str, Any]]] = {}
        for cycle in self.history:
            pid = int(cycle.get("profile", 1))
            profiles.setdefault(pid, []).append(cycle)

        for pid, cycles in profiles.items():
            avg_duration = sum(float(c.get("duration", 0)) for c in cycles) / len(cycles)
            avg_energy = sum(float(c.get("energy", 0)) for c in cycles) / len(cycles)
            duration_diff = abs(duration - avg_duration) / max(avg_duration, 1.0)
            energy_diff = abs(energy - avg_energy) / max(avg_energy, 0.05)
            if (
                duration_diff <= PROFILE_DURATION_TOLERANCE
                and energy_diff <= PROFILE_ENERGY_TOLERANCE
            ):
                return pid
        return max(profiles, default=0) + 1

    def _sanitize_history(self, cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cleaned: list[dict[str, Any]] = []
        for cycle in cycles:
            if not isinstance(cycle, dict):
                continue
            try:
                duration = float(cycle.get("duration", 0))
                energy = float(cycle.get("energy", 0))
            except (TypeError, ValueError):
                continue
            if not (MIN_LEARN_DURATION <= duration <= self.max_learn_duration):
                continue
            if energy < MIN_LEARN_ENERGY:
                continue
            points: list[dict[str, float]] = []
            for point in cycle.get("points", []):
                try:
                    minute = float(point.get("m", -1))
                    if 0 <= minute <= duration + 1:
                        points.append(
                            {
                                "m": round(minute, 1),
                                "e": round(max(0.0, float(point.get("e", 0))), 4),
                                "p": round(max(0.0, float(point.get("p", 0))), 1),
                            }
                        )
                except (TypeError, ValueError, AttributeError):
                    continue
            copy = dict(cycle)
            copy["duration"] = int(round(duration))
            copy["energy"] = round(energy, 4)
            copy["points"] = points
            cleaned.append(copy)
        return cleaned[-MAX_CYCLES:]

    def _status_entity_running(self) -> bool | None:
        if self.mode != DETECTION_STATUS:
            return False
        entity_id = self.config.get(CONF_STATUS_ENTITY)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        raw_state = state.state.strip().lower()
        if raw_state in {"unknown", "unavailable", "none", ""}:
            return None
        configured = str(self.config.get(CONF_RUNNING_STATES, DEFAULT_RUNNING_STATES))
        running_states = {item.strip().lower() for item in configured.split(",") if item.strip()}
        return raw_state in running_states

    def _read_power_w(self) -> float | None:
        state = self.hass.states.get(self.power_entity)
        if state is None or state.state in {"unknown", "unavailable", "none", ""}:
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        unit = str(state.attributes.get("unit_of_measurement", "W")).lower()
        if unit == "kw":
            return value * 1000.0
        if unit == "mw":
            return value * 1_000_000.0
        return value

    def _read_energy_kwh(self) -> float | None:
        state = self.hass.states.get(self.energy_entity)
        if state is None or state.state in {"unknown", "unavailable", "none", ""}:
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        unit = str(state.attributes.get("unit_of_measurement", "kWh")).lower()
        if unit == "wh":
            return value / 1000.0
        if unit == "mwh":
            return value * 1000.0
        return value

    async def async_reset_history(self) -> None:
        """Clear learned cycle history without interrupting an active cycle."""
        self.history = []
        self.values["learned_cycles"] = 0
        self._last_remaining = None
        self.prediction_samples = []
        if self.active:
            self.values.update(
                {
                    "remaining_time": None,
                    "expected_end": None,
                    "expected_duration": None,
                    "confidence": 0,
                    "cycle_profile": "Learning",
                }
            )
        else:
            self.values.update(
                {
                    "remaining_time": None,
                    "expected_end": None,
                    "expected_duration": None,
                    "confidence": 0,
                    "cycle_profile": "Waiting for cycle",
                }
            )
        await self._store.async_save(self._serialize())
        self._notify()
        _LOGGER.info("%s: learned cycle history cleared", self.name)

    def _serialize(self) -> dict[str, Any]:
        active: dict[str, Any] | None = None
        if self.active and self.start_time is not None:
            active = {
                "start_time": self.start_time.isoformat(),
                "energy_start": self.energy_start,
                "points": self.points,
                "prediction_samples": self.prediction_samples,
                "last_checkpoint": self._last_checkpoint,
            }
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "cycles": self.history[-MAX_CYCLES:],
            "active": active,
        }

    def _restore_active(self, active: dict[str, Any]) -> None:
        try:
            start = datetime.fromisoformat(str(active["start_time"]))
            if start.tzinfo is None:
                start = start.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            age = (dt_util.now() - start).total_seconds() / 60.0
            if age < 0 or age > MAX_ACTIVE_MINUTES:
                return
            self.active = True
            self.start_time = start
            self.energy_start = float(active.get("energy_start", 0.0))
            self.points = list(active.get("points", []))
            self.prediction_samples = list(active.get("prediction_samples", []))
            self._last_checkpoint = int(active.get("last_checkpoint", 0))
        except (KeyError, TypeError, ValueError):
            return

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._serialize, 5)
