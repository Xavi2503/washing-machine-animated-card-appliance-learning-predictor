# Appliance Learning Predictor v2.3 for Home Assistant / Pyscript
# Generic community edition.
#
# Purpose:
# - Observation only. Existing start/stop/notification automations remain authoritative.
# - Learns from completed washing-machine and dryer cycles.
# - Compares the current cycle phase with previous cycles and predicts remaining time.
# - Uses phase alignment, remaining-time comparison, bias correction and prediction stabilization.
# - Writes a CSV training log per appliance with predictions and actual outcomes.
# - Persists up to 40 completed cycles per appliance.
#
# Requirements:
# - Pyscript via HACS + the "Pyscript Python scripting" integration
# - Save this file as /config/pyscript/appliance_learning.py
#
# Adjust the entity IDs in MACHINES below to match your own Home Assistant setup.

MACHINES = {
    "washer": {
        "running": "input_boolean.washer_running",
        "power": "sensor.washer_power",
        "energy": "sensor.washer_energy",
        "energy_start": "input_number.washer_energy_start",
        "start_time": "input_datetime.washer_last_start",
        "end_time": "input_datetime.washer_last_end",
        "last_duration": "input_number.washer_last_duration",
        "last_energy": "input_number.washer_last_energy",
        "history": "pyscript.washer_learning_data",
        "expected_end": "pyscript.washer_expected_end",
        "expected_duration": "pyscript.washer_expected_duration",
        "remaining": "pyscript.washer_remaining_time",
        "profile": "pyscript.washer_cycle_profile",
        "confidence": "pyscript.washer_prediction_confidence",
        "learned": "pyscript.washer_learned_cycles",
        "friendly": "Washer",
        "log_file": "/config/pyscript/logs/washer_prediction_log.csv",
    },
    "dryer": {
        "running": "input_boolean.dryer_running",
        "power": "sensor.dryer_power",
        "energy": "sensor.dryer_energy",
        "energy_start": "input_number.dryer_energy_start",
        "start_time": "input_datetime.dryer_last_start",
        "end_time": "input_datetime.dryer_last_end",
        "last_duration": "input_number.dryer_last_duration",
        "last_energy": "input_number.dryer_last_energy",
        "history": "pyscript.dryer_learning_data",
        "expected_end": "pyscript.dryer_expected_end",
        "expected_duration": "pyscript.dryer_expected_duration",
        "remaining": "pyscript.dryer_remaining_time",
        "profile": "pyscript.dryer_cycle_profile",
        "confidence": "pyscript.dryer_prediction_confidence",
        "learned": "pyscript.dryer_learned_cycles",
        "friendly": "Dryer",
        "log_file": "/config/pyscript/logs/dryer_prediction_log.csv",
    },
}

MAX_CYCLES = 40
CHECKPOINT_MINUTES = 5
MIN_LEARN_DURATION = 8
MIN_LEARN_ENERGY = 0.01
PROFILE_NEW_THRESHOLD = 0.38
UNKNOWN_EARLY_PATTERN_THRESHOLD = 0.75

# Predictor v2
ALGORITHM_VERSION = "2.3"
PHASE_SHIFT_LIMIT = 20
BIAS_MAX_MINUTES = 12
PREDICTION_SAMPLE_INTERVAL = 5
STABILITY_EARLY = 7
STABILITY_MID = 4
STABILITY_LATE = 2

# Historical-data validation / contamination protection
HISTORY_POINT_GRACE = 5
MAX_ACTIVE_MINUTES = 600
MAX_LEARN_DURATION = 360  # 6 hours; configurable safety limit for training data

# Predictor v2.3 training log.
# The /config/pyscript/logs directory must exist.
LOG_HEADER = (
    "timestamp,event,machine,cycle_id,elapsed_min,power_w,energy_kwh,"
    "predicted_end,predicted_remaining_min,predicted_total_duration_min,"
    "confidence_pct,profile,actual_end,actual_duration_min,actual_energy_kwh,"
    "actual_remaining_min,error_actual_minus_predicted_min,algorithm_version"
)

# Runtime data only; historical cycles are persisted in the pyscript.* history entities.
LIVE = {
    "washer": {
        "active": False,
        "points": [],
        "power_sum": 0.0,
        "power_count": 0,
        "last_point_minute": 0,
        "last_power": 0.0,
        "last_remaining": None,
        "last_prediction_elapsed": 0,
        "last_expected_duration": 0.0,
        "prediction_samples": [],
        "last_prediction_sample_minute": 0,
        "winning_profile": None,
    },
    "dryer": {
        "active": False,
        "points": [],
        "power_sum": 0.0,
        "power_count": 0,
        "last_point_minute": 0,
        "last_power": 0.0,
        "last_remaining": None,
        "last_prediction_elapsed": 0,
        "last_expected_duration": 0.0,
        "prediction_samples": [],
        "last_prediction_sample_minute": 0,
        "winning_profile": None,
    },
}


@pyscript_executor
def _append_csv_line(file_name, header_line, data_line):
    """Native Python file I/O outside the Home Assistant event loop."""
    try:
        needs_header = True

        try:
            with open(file_name, "r", encoding="utf-8") as file_desc:
                if file_desc.read(1):
                    needs_header = False
        except FileNotFoundError:
            needs_header = True

        with open(file_name, "a", encoding="utf-8", newline="") as file_desc:
            if needs_header:
                file_desc.write(header_line + "\n")
            file_desc.write(data_line + "\n")

        return ""
    except Exception as exc:
        return str(exc)


def _csv_cell(value):
    if value is None:
        value = ""
    s = str(value)
    return '"' + s.replace('"', '""') + '"'


def _csv_line(values):
    result = ""
    first = True

    for value in values:
        if not first:
            result += ","
        result += _csv_cell(value)
        first = False

    return result


def _log_row(kind, values):
    """Logging failures must never affect predictor operation."""
    try:
        file_name = MACHINES[kind]["log_file"]
        error = _append_csv_line(file_name, LOG_HEADER, _csv_line(values))
        if error:
            log.warning(
                f'{MACHINES[kind]["friendly"]}: prediction log not written: {error}'
            )
            return False
        return True
    except Exception as exc:
        log.warning(
            f'{MACHINES[kind]["friendly"]}: prediction log error ignored: {exc}'
        )
        return False


def _cycle_id(kind):
    return str(_safe_state(MACHINES[kind]["start_time"], "") or "")


def _log_start(kind):
    c = MACHINES[kind]
    start_text = str(_safe_state(c["start_time"], "") or "")

    _log_row(
        kind,
        [
            start_text,
            "start",
            kind,
            start_text,
            0,
            round(_safe_float(c["power"], 0.0), 1),
            round(_current_cycle_energy(kind), 4),
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            ALGORITHM_VERSION,
        ],
    )


def _log_prediction(kind, sample):
    _log_row(
        kind,
        [
            sample.get("timestamp", ""),
            "prediction",
            kind,
            _cycle_id(kind),
            sample.get("m", ""),
            round(_safe_float(MACHINES[kind]["power"], 0.0), 1),
            round(_current_cycle_energy(kind), 4),
            sample.get("expected_end", ""),
            sample.get("remaining", ""),
            sample.get("expected_duration", ""),
            sample.get("confidence", ""),
            sample.get("profile", ""),
            "",
            "",
            "",
            "",
            "",
            ALGORITHM_VERSION,
        ],
    )


def _log_finish_and_evaluations(kind, duration, energy):
    c = MACHINES[kind]
    live = LIVE[kind]
    end_text = str(_safe_state(c["end_time"], "") or "")
    cycle_id = _cycle_id(kind)

    _log_row(
        kind,
        [
            end_text,
            "finish",
            kind,
            cycle_id,
            int(round(duration)),
            round(_safe_float(c["power"], 0.0), 1),
            round(energy, 4),
            "",
            "",
            "",
            "",
            "",
            end_text,
            int(round(duration)),
            round(energy, 4),
            0,
            "",
            ALGORITHM_VERSION,
        ],
    )

    # After completion, write the actual error for every earlier prediction sample.
    # Positive = the prediction was too early / too optimistic.
    # Negative = the prediction was too late / too pessimistic.
    for sample in live.get("prediction_samples", []):
        try:
            minute = int(sample.get("m", 0))
            predicted_remaining = float(sample.get("remaining", 0.0))
            actual_remaining = max(0.0, float(duration) - minute)
            error = actual_remaining - predicted_remaining

            _log_row(
                kind,
                [
                    end_text,
                    "evaluation",
                    kind,
                    cycle_id,
                    minute,
                    sample.get("power", ""),
                    sample.get("energy", ""),
                    sample.get("expected_end", ""),
                    round(predicted_remaining, 2),
                    sample.get("expected_duration", ""),
                    sample.get("confidence", ""),
                    sample.get("profile", ""),
                    end_text,
                    int(round(duration)),
                    round(energy, 4),
                    round(actual_remaining, 2),
                    round(error, 2),
                    ALGORITHM_VERSION,
                ],
            )
        except Exception as exc:
            log.warning(
                f'{c["friendly"]}: evaluation row skipped: {exc}'
            )


def _safe_state(entity_id, default=None):
    try:
        value = state.get(entity_id)
        if value is None:
            return default
        return value
    except Exception:
        return default


def _safe_float(entity_id, default=0.0):
    value = _safe_state(entity_id, None)
    try:
        return float(value)
    except Exception:
        return default


def _is_running(kind):
    return str(_safe_state(MACHINES[kind]["running"], "off")).lower() == "on"


def _is_leap(year):
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def _days_before_month(year, month):
    month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    total = 0
    idx = 1
    while idx < month:
        total += month_days[idx - 1]
        if idx == 2 and _is_leap(year):
            total += 1
        idx += 1
    return total


def _date_to_minutes(year, month, day, hour, minute):
    # Sufficient for current Home Assistant date values (year 2000 and later).
    days = 0
    y = 2000
    if year >= 2000:
        while y < year:
            days += 366 if _is_leap(y) else 365
            y += 1
    else:
        y = year
        while y < 2000:
            days -= 366 if _is_leap(y) else 365
            y += 1
    days += _days_before_month(year, month)
    days += day - 1
    return days * 1440 + hour * 60 + minute


def _parse_input_datetime(value):
    # Home Assistant input_datetime: "YYYY-MM-DD HH:MM:SS"
    try:
        parts = str(value).strip().split(" ")
        d = parts[0].split("-")
        t = parts[1].split(":")
        return {
            "year": int(d[0]),
            "month": int(d[1]),
            "day": int(d[2]),
            "hour": int(t[0]),
            "minute": int(t[1]),
        }
    except Exception:
        return None


def _elapsed_minutes(kind, now):
    start = _parse_input_datetime(_safe_state(MACHINES[kind]["start_time"], ""))
    if start is None or now is None:
        return 0
    try:
        start_min = _date_to_minutes(
            start["year"], start["month"], start["day"], start["hour"], start["minute"]
        )
        now_min = _date_to_minutes(now.year, now.month, now.day, now.hour, now.minute)
        return max(0, int(now_min - start_min))
    except Exception:
        return 0


def _current_cycle_energy(kind):
    current = _safe_float(MACHINES[kind]["energy"], 0.0)
    begin = _safe_float(MACHINES[kind]["energy_start"], current)
    return max(0.0, round(current - begin, 4))


def _history(kind):
    entity = MACHINES[kind]["history"]
    try:
        attrs = state.getattr(entity) or {}
        cycles = attrs.get("cycles", [])
        if isinstance(cycles, list):
            return cycles
    except Exception:
        pass
    return []


def _cycle_signature(cycle):
    try:
        start = str(cycle.get("start", "")).strip()
        end = str(cycle.get("end", "")).strip()
        duration = int(round(float(cycle.get("duration", 0))))
        energy = round(float(cycle.get("energy", 0.0)), 3)
        return f"{start}|{end}|{duration}|{energy}"
    except Exception:
        return None


def _sanitize_cycle(cycle):
    if not isinstance(cycle, dict):
        return None, 0

    try:
        duration = float(cycle.get("duration", 0))
    except Exception:
        return None, 0

    if duration <= 0 or duration > MAX_LEARN_DURATION:
        return None, 0

    cleaned = dict(cycle)
    removed_points = 0

    # Keep only measurement points that logically fall inside this cycle.
    valid_points = []
    seen_minutes = set()
    points = cycle.get("points", [])
    if isinstance(points, list):
        for p in points:
            if not isinstance(p, dict):
                removed_points += 1
                continue
            try:
                minute = int(round(float(p.get("m", -1))))
                energy = float(p.get("e", 0.0))
                power = float(p.get("p", 0.0))
            except Exception:
                removed_points += 1
                continue

            if minute < 0 or minute > duration + HISTORY_POINT_GRACE:
                removed_points += 1
                continue

            # One measurement point per minute is enough.
            if minute in seen_minutes:
                removed_points += 1
                continue

            seen_minutes.add(minute)
            valid_points.append(
                {
                    "m": minute,
                    "e": round(max(0.0, energy), 4),
                    "p": round(max(0.0, power), 1),
                }
            )

    valid_points.sort(key=lambda p: p["m"])
    cleaned["points"] = valid_points

    # Also sanitize historical error-correction data.
    valid_errors = []
    errors = cycle.get("errors", [])
    if isinstance(errors, list):
        for item in errors:
            if not isinstance(item, dict):
                continue
            try:
                minute = int(round(float(item.get("m", -1))))
                err = float(item.get("error", 0.0))
            except Exception:
                continue
            if minute < 0 or minute > duration:
                continue
            valid_errors.append(
                {
                    "m": minute,
                    "error": round(err, 2),
                }
            )

    cleaned["errors"] = valid_errors
    return cleaned, removed_points


def _sanitize_history(kind, cycles):
    cleaned_cycles = []
    by_signature = {}
    removed_points = 0
    removed_duplicates = 0
    removed_cycles = 0

    if not isinstance(cycles, list):
        cycles = []

    for cycle in cycles:
        cleaned, removed = _sanitize_cycle(cycle)
        removed_points += removed

        if cleaned is None:
            removed_cycles += 1
            continue

        signature = _cycle_signature(cleaned)

        if signature and signature in by_signature:
            # The same completed cycle was stored more than once.
            # Keep the version with the most useful measurement points.
            existing_index = by_signature[signature]
            existing = cleaned_cycles[existing_index]
            existing_score = len(existing.get("points", [])) + len(existing.get("errors", []))
            new_score = len(cleaned.get("points", [])) + len(cleaned.get("errors", []))

            if new_score > existing_score:
                cleaned_cycles[existing_index] = cleaned

            removed_duplicates += 1
            continue

        if signature:
            by_signature[signature] = len(cleaned_cycles)

        cleaned_cycles.append(cleaned)

    if len(cleaned_cycles) > MAX_CYCLES:
        cleaned_cycles = cleaned_cycles[-MAX_CYCLES:]

    log.info(
        f'{MACHINES[kind]["friendly"]}: learning data sanitized - '
        f'{removed_points} invalid measurement points, '
        f'{removed_duplicates} duplicate cycles, '
        f'{removed_cycles} invalid cycles removed'
    )

    return cleaned_cycles, removed_points, removed_duplicates, removed_cycles


def _save_history(kind, cycles):
    c = MACHINES[kind]
    if len(cycles) > MAX_CYCLES:
        cycles = cycles[-MAX_CYCLES:]
    state.set(
        c["history"],
        str(len(cycles)),
        new_attributes={
            "friendly_name": f'{c["friendly"]} learning data',
            "icon": "mdi:brain",
            "cycles": cycles,
            "max_cycles": MAX_CYCLES,
            "algorithm_version": ALGORITHM_VERSION,
            "history_validation": "enabled",
            "prediction_log": "csv_enabled",
        },
    )
    state.set(
        c["learned"],
        str(len(cycles)),
        new_attributes={
            "friendly_name": f'{c["friendly"]} learned cycles',
            "icon": "mdi:counter",
            "unit_of_measurement": "cycles",
        },
    )


def _set_output(kind, expected_end="—", expected_duration=0, remaining=0,
                profile="Learning", confidence=0):
    c = MACHINES[kind]
    state.set(
        c["expected_end"],
        str(expected_end),
        new_attributes={
            "friendly_name": f'{c["friendly"]} expected finish',
            "icon": "mdi:clock-outline",
        },
    )
    state.set(
        c["expected_duration"],
        str(int(round(expected_duration))) if expected_duration else "0",
        new_attributes={
            "friendly_name": f'{c["friendly"]} expected duration',
            "icon": "mdi:timer-outline",
            "unit_of_measurement": "min",
        },
    )
    state.set(
        c["remaining"],
        str(max(0, int(round(remaining)))) if remaining else "0",
        new_attributes={
            "friendly_name": f'{c["friendly"]} remaining time',
            "icon": "mdi:timer-sand",
            "unit_of_measurement": "min",
        },
    )
    state.set(
        c["profile"],
        str(profile),
        new_attributes={
            "friendly_name": f'{c["friendly"]} program profile',
            "icon": "mdi:shape-outline",
        },
    )
    state.set(
        c["confidence"],
        str(max(0, min(100, int(round(confidence))))),
        new_attributes={
            "friendly_name": f'{c["friendly"]} prediction confidence',
            "icon": "mdi:percent",
            "unit_of_measurement": "%",
        },
    )


def _expected_clock(now, remaining_minutes):
    if now is None:
        return "—"
    try:
        total = now.hour * 60 + now.minute + int(round(remaining_minutes))
        day_offset = total // 1440
        minute_of_day = total % 1440
        hh = minute_of_day // 60
        mm = minute_of_day % 60
        if day_offset <= 0:
            day_text = "Vandaag"
        elif day_offset == 1:
            day_text = "Morgen"
        else:
            day_text = f"+{day_offset} dagen"
        return f"{day_text} {hh:02d}:{mm:02d}"
    except Exception:
        return "—"


def _nearest_point(points, minute, tolerance=3):
    best = None
    best_delta = 999999
    for p in points:
        try:
            delta = abs(int(p.get("m", 0)) - int(minute))
            if delta < best_delta:
                best_delta = delta
                best = p
        except Exception:
            pass
    if best is not None and best_delta <= tolerance:
        return best
    return None


def _recent_energy_slope(points, minute):
    current = _nearest_point(points, minute, 3)
    if current is None:
        return None

    current_m = int(current.get("m", 0))
    current_e = float(current.get("e", 0.0))

    previous = None
    previous_m = -1
    for p in points:
        try:
            pm = int(p.get("m", 0))
            if pm < current_m and pm > previous_m:
                previous = p
                previous_m = pm
        except Exception:
            pass

    if previous is None:
        return None

    delta_m = current_m - previous_m
    if delta_m <= 0:
        return None

    try:
        delta_e = current_e - float(previous.get("e", 0.0))
        return delta_e / delta_m
    except Exception:
        return None


def _aligned_curve_distance(current_points, historical_points, elapsed, hist_duration):
    # V2: do not only match the same minute; also check whether the current cycle
    # is running a phase ahead/behind. This helps with variable loads and adaptive programs.
    if not current_points or not historical_points:
        return None

    selected = current_points[-5:]
    best = None

    shift = -PHASE_SHIFT_LIMIT
    while shift <= PHASE_SHIFT_LIMIT:
        total = 0.0
        pairs = 0

        for cp in selected:
            try:
                current_minute = int(cp.get("m", 0))
                hist_minute = current_minute + shift
                if hist_minute < 0 or hist_minute > hist_duration + 3:
                    continue

                hp = _nearest_point(historical_points, hist_minute, 3)
                if hp is None:
                    continue

                ce = float(cp.get("e", 0.0))
                he = float(hp.get("e", 0.0))
                cpow = float(cp.get("p", 0.0))
                hpow = float(hp.get("p", 0.0))

                e_scale = max(0.04, abs(ce), abs(he))
                p_scale = max(120.0, abs(cpow), abs(hpow))

                e_diff = abs(ce - he) / e_scale
                p_diff = abs(cpow - hpow) / p_scale

                cs = _recent_energy_slope(current_points, current_minute)
                hs = _recent_energy_slope(historical_points, int(hp.get("m", hist_minute)))
                if cs is not None and hs is not None:
                    slope_scale = max(0.003, abs(cs), abs(hs))
                    slope_diff = abs(cs - hs) / slope_scale
                else:
                    slope_diff = 0.0

                total += 0.52 * e_diff + 0.28 * p_diff + 0.20 * slope_diff
                pairs += 1
            except Exception:
                pass

        if pairs >= 2:
            distance = total / pairs

            # Apply a small penalty for large phase shifts.
            distance += (abs(shift) / max(1.0, PHASE_SHIFT_LIMIT)) * 0.10

            if best is None or distance < best[0]:
                matched_hist_minute = max(0, min(hist_duration, elapsed + shift))
                best = [distance, shift, matched_hist_minute]

        shift += CHECKPOINT_MINUTES

    return best


def _nearest_bias_error(cycle, elapsed):
    errors = cycle.get("errors", [])
    if not isinstance(errors, list) or len(errors) == 0:
        return None

    best = None
    best_delta = 999999

    for item in errors:
        try:
            minute = int(item.get("m", 0))
            delta = abs(minute - int(elapsed))
            if delta < best_delta:
                best_delta = delta
                best = float(item.get("error", 0.0))
        except Exception:
            pass

    if best is not None and best_delta <= 12:
        return best
    return None


def _profile_bias(cycles, profile_id, elapsed):
    if profile_id is None:
        return 0.0

    weighted = 0.0
    weight_sum = 0.0

    for cyc in cycles:
        try:
            if int(cyc.get("profile", -1)) != int(profile_id):
                continue

            err = _nearest_bias_error(cyc, elapsed)
            if err is None:
                continue

            # Newer cycles are stored last and receive a slightly higher fixed weight.
            weight = 1.0
            weighted += err * weight
            weight_sum += weight
        except Exception:
            pass

    if weight_sum <= 0:
        return 0.0

    bias = weighted / weight_sum
    return max(-BIAS_MAX_MINUTES, min(BIAS_MAX_MINUTES, bias))


def _stabilize_remaining(kind, raw_remaining, elapsed, confidence):
    # A good prediction should count down rather than jump back and forth.
    live = LIVE[kind]
    previous = live.get("last_remaining")
    previous_elapsed = int(live.get("last_prediction_elapsed", 0) or 0)

    if previous is None or previous_elapsed <= 0:
        return max(0.0, raw_remaining)

    elapsed_delta = max(1, int(elapsed) - previous_elapsed)
    baseline = max(0.0, float(previous) - elapsed_delta)

    total_estimate = max(float(elapsed) + float(raw_remaining), 1.0)
    progress = float(elapsed) / total_estimate

    if progress >= 0.72:
        limit = STABILITY_LATE
    elif progress >= 0.38:
        limit = STABILITY_MID
    else:
        limit = STABILITY_EARLY

    if confidence < 35:
        limit += 3
    elif confidence < 55:
        limit += 1

    low = max(0.0, baseline - limit)
    high = baseline + limit

    return max(low, min(float(raw_remaining), high))


def _record_prediction_sample(
    kind,
    elapsed,
    remaining,
    expected_end,
    expected_duration,
    confidence,
    profile_text,
    now,
):
    live = LIVE[kind]
    last_sample = int(live.get("last_prediction_sample_minute", 0) or 0)

    if elapsed < CHECKPOINT_MINUTES:
        return False

    if elapsed - last_sample < PREDICTION_SAMPLE_INTERVAL:
        return False

    try:
        timestamp = str(now)
    except Exception:
        timestamp = ""

    sample = {
        "m": int(elapsed),
        "remaining": round(float(remaining), 2),
        "expected_end": str(expected_end),
        "expected_duration": round(float(expected_duration), 2),
        "confidence": int(round(confidence)),
        "profile": str(profile_text),
        "timestamp": timestamp,
        "power": round(_safe_float(MACHINES[kind]["power"], 0.0), 1),
        "energy": round(_current_cycle_energy(kind), 4),
    }

    live["prediction_samples"].append(sample)
    live["last_prediction_sample_minute"] = int(elapsed)

    _log_prediction(kind, sample)
    return True


def _profile_for_completed_cycle(cycles, duration, energy):
    if not cycles:
        return 1

    profile_stats = {}
    for cyc in cycles:
        try:
            pid = int(cyc.get("profile", 1))
            if pid not in profile_stats:
                profile_stats[pid] = {"dur": 0.0, "eng": 0.0, "n": 0}
            profile_stats[pid]["dur"] += float(cyc.get("duration", 0))
            profile_stats[pid]["eng"] += float(cyc.get("energy", 0))
            profile_stats[pid]["n"] += 1
        except Exception:
            pass

    best_profile = None
    best_distance = 999999.0

    for pid, stats in profile_stats.items():
        if stats["n"] <= 0:
            continue
        avg_d = stats["dur"] / stats["n"]
        avg_e = stats["eng"] / stats["n"]

        d_diff = abs(duration - avg_d) / max(30.0, avg_d, duration)
        e_diff = abs(energy - avg_e) / max(0.08, avg_e, energy)
        distance = 0.58 * d_diff + 0.42 * e_diff

        if distance < best_distance:
            best_distance = distance
            best_profile = pid

    if best_profile is not None and best_distance <= PROFILE_NEW_THRESHOLD:
        return best_profile

    highest = 0
    for pid in profile_stats:
        if pid > highest:
            highest = pid
    return highest + 1


def _predict(kind, elapsed, now):
    live = LIVE[kind]
    cycles = _history(kind)

    if elapsed < CHECKPOINT_MINUTES or len(live["points"]) == 0:
        if len(cycles) == 0:
            _set_output(kind, "Learning…", 0, 0, "Learning", 0)
        else:
            _set_output(kind, "Nog te vroeg", 0, 0, "Analyzing", 0)
        return

    if len(cycles) == 0:
        _set_output(kind, "Learning…", 0, 0, "Learning (0 cycles)", 0)
        return

    candidates = []

    for idx in range(len(cycles)):
        cyc = cycles[idx]
        try:
            hist_duration = float(cyc.get("duration", 0))
            hist_points = cyc.get("points", [])

            if hist_duration <= 0 or not hist_points:
                continue

            match = _aligned_curve_distance(
                live["points"], hist_points, elapsed, hist_duration
            )
            if match is None:
                continue

            dist = float(match[0])
            hist_phase_minute = float(match[2])

            hist_remaining = max(0.0, hist_duration - hist_phase_minute)

            # Strongly penalize a comparison cycle that should already have finished.
            if hist_duration + 5 < elapsed:
                dist += 1.10 + ((elapsed - hist_duration) / max(25.0, hist_duration))

            candidates.append(
                [dist, idx, hist_remaining, hist_phase_minute]
            )
        except Exception:
            pass

    if len(candidates) == 0:
        _set_output(kind, "No match yet", 0, 0, "Unknown", 0)
        return

    candidates.sort()
    top_count = min(6, len(candidates))
    top = candidates[:top_count]

    weighted_remaining = 0.0
    weight_sum = 0.0
    profile_votes = {}

    for item in top:
        dist = float(item[0])
        cyc = cycles[item[1]]
        hist_remaining = float(item[2])

        weight = 1.0 / (0.10 + max(0.0, dist))
        weighted_remaining += hist_remaining * weight
        weight_sum += weight

        pid = int(cyc.get("profile", 1))
        if pid not in profile_votes:
            profile_votes[pid] = 0.0
        profile_votes[pid] += weight

    if weight_sum <= 0:
        _set_output(kind, "No match yet", 0, 0, "Unknown", 0)
        return

    raw_remaining = max(1.0, weighted_remaining / weight_sum)
    best_distance = float(top[0][0])

    winning_profile = None
    winning_vote = -1.0
    for pid, vote in profile_votes.items():
        if vote > winning_vote:
            winning_vote = vote
            winning_profile = pid

    point_count = len(live["points"])
    progress_factor = min(1.0, point_count / 5.0)
    history_factor = min(1.0, len(cycles) / 6.0)
    match_factor = max(0.0, 1.0 - min(1.0, best_distance))

    confidence = int(
        10
        + 85
        * match_factor
        * (0.42 + 0.58 * progress_factor)
        * (0.52 + 0.48 * history_factor)
    )

    if len(cycles) == 1:
        confidence = min(confidence, 45)
    elif len(cycles) == 2:
        confidence = min(confidence, 60)
    elif len(cycles) == 3:
        confidence = min(confidence, 72)

    confidence = max(5, min(96, confidence))

    # V2 bias correction: learn systematic early/late prediction errors per profile.
    bias = _profile_bias(cycles, winning_profile, elapsed)
    corrected_remaining = max(1.0, raw_remaining + bias)

    # V2 stabilization: prevent the finish time from drifting without strong evidence.
    remaining = _stabilize_remaining(
        kind, corrected_remaining, elapsed, confidence
    )

    expected_duration = max(float(elapsed) + remaining, float(elapsed) + 1.0)

    if best_distance > UNKNOWN_EARLY_PATTERN_THRESHOLD and elapsed >= 15:
        profile_text = "New/unknown profile"
        confidence = min(confidence, 45)
    elif winning_profile is not None:
        profile_text = f"Profile {winning_profile}"
    else:
        profile_text = "Unknown"

    expected_end = _expected_clock(now, remaining)

    live["last_remaining"] = float(remaining)
    live["last_prediction_elapsed"] = int(elapsed)
    live["last_expected_duration"] = float(expected_duration)
    live["winning_profile"] = winning_profile

    _record_prediction_sample(
        kind,
        elapsed,
        remaining,
        expected_end,
        expected_duration,
        confidence,
        profile_text,
        now,
    )

    _set_output(
        kind,
        expected_end=expected_end,
        expected_duration=expected_duration,
        remaining=remaining,
        profile=profile_text,
        confidence=confidence,
    )


def _cycle_start(kind):
    live = LIVE[kind]
    live["active"] = True
    live["points"] = []
    live["power_sum"] = 0.0
    live["power_count"] = 0
    live["last_point_minute"] = 0
    live["last_power"] = _safe_float(MACHINES[kind]["power"], 0.0)
    live["last_remaining"] = None
    live["last_prediction_elapsed"] = 0
    live["last_expected_duration"] = 0.0
    live["prediction_samples"] = []
    live["last_prediction_sample_minute"] = 0
    live["winning_profile"] = None

    cycles = _history(kind)
    if len(cycles) == 0:
        _set_output(kind, "Learning…", 0, 0, "Learning", 0)
    else:
        _set_output(kind, "Analyzing…", 0, 0, "Analyzing", 0)

    _log_start(kind)

    log.info(
        f'{MACHINES[kind]["friendly"]}: new cycle detected '
        f'(predictor v{ALGORITHM_VERSION})'
    )


def _cycle_finish(kind):
    live = LIVE[kind]
    c = MACHINES[kind]

    duration = _safe_float(c["last_duration"], 0.0)
    energy = _safe_float(c["last_energy"], 0.0)

    if (
        duration >= MIN_LEARN_DURATION
        and duration <= MAX_LEARN_DURATION
        and energy >= MIN_LEARN_ENERGY
    ):
        # Add a final measurement point when useful.
        if (
            duration >= CHECKPOINT_MINUTES
            and (
                len(live["points"]) == 0
                or duration - float(live["points"][-1].get("m", 0)) >= 3
            )
        ):
            live["points"].append(
                {
                    "m": int(round(duration)),
                    "e": round(energy, 4),
                    "p": round(float(live.get("last_power", 0.0)), 1),
                }
            )

        cycles = _history(kind)
        profile_id = _profile_for_completed_cycle(cycles, duration, energy)

        # V2: create error-correction data from predictions made during this cycle.
        # Positive means the prediction was early; negative means it was late.
        errors = []
        for sample in live.get("prediction_samples", []):
            try:
                minute = int(sample.get("m", 0))
                predicted_remaining = float(sample.get("remaining", 0.0))
                actual_remaining = max(0.0, float(duration) - minute)
                error = actual_remaining - predicted_remaining

                errors.append(
                    {
                        "m": minute,
                        "error": round(error, 2),
                    }
                )
            except Exception:
                pass

        cycle = {
            "duration": int(round(duration)),
            "energy": round(energy, 4),
            "profile": int(profile_id),
            "points": live["points"][:],
            "errors": errors,
            "start": str(_safe_state(c["start_time"], "")),
            "end": str(_safe_state(c["end_time"], "")),
            "algorithm_version": ALGORITHM_VERSION,
        }

        # Final validation: never store measurement points outside the actual cycle duration.
        cycle, removed_points = _sanitize_cycle(cycle)

        if cycle is not None:
            signature = _cycle_signature(cycle)
            duplicate_index = None

            if signature:
                idx = 0
                for old_cycle in cycles:
                    if _cycle_signature(old_cycle) == signature:
                        duplicate_index = idx
                        break
                    idx += 1

            if duplicate_index is None:
                cycles.append(cycle)
            else:
                # For duplicate cycles, keep the most complete version.
                old_cycle = cycles[duplicate_index]
                old_score = len(old_cycle.get("points", [])) + len(old_cycle.get("errors", []))
                new_score = len(cycle.get("points", [])) + len(cycle.get("errors", []))
                if new_score > old_score:
                    cycles[duplicate_index] = cycle

            _save_history(kind, cycles)

            if removed_points > 0:
                log.info(
                    f'{c["friendly"]}: {removed_points} invalid live measurement points '
                    f'not stored'
                )

        _set_output(
            kind,
            expected_end="—",
            expected_duration=duration,
            remaining=0,
            profile=f"Profile {profile_id}",
            confidence=100,
        )

        _log_finish_and_evaluations(kind, duration, energy)

        log.info(
            f'{c["friendly"]}: cycle learned - '
            f'{int(round(duration))} min, {round(energy, 3)} kWh, '
            f'Profile {profile_id}, predictor v{ALGORITHM_VERSION}'
        )
    else:
        if duration > MAX_LEARN_DURATION:
            log.warning(
                f'{c["friendly"]}: cycle not learned - unrealistic runtime '
                f'({duration} min; limit {MAX_LEARN_DURATION} min)'
            )
            _set_output(kind, "—", 0, 0, "Invalid long cycle", 0)
        else:
            log.info(
                f'{c["friendly"]}: cycle not learned '
                f'(too short or too little energy: {duration} min / {energy} kWh)'
            )
            _set_output(kind, "—", 0, 0, "No valid cycle", 0)

    live["active"] = False
    live["points"] = []
    live["power_sum"] = 0.0
    live["power_count"] = 0
    live["last_point_minute"] = 0
    live["last_remaining"] = None
    live["last_prediction_elapsed"] = 0
    live["last_expected_duration"] = 0.0
    live["prediction_samples"] = []
    live["last_prediction_sample_minute"] = 0
    live["winning_profile"] = None


def _sample_machine(kind, now):
    if not _is_running(kind):
        return

    live = LIVE[kind]
    if not live["active"]:
        _cycle_start(kind)

    elapsed = _elapsed_minutes(kind, now)
    if elapsed <= 0:
        return

    # Protect learning data against a stuck *_running helper or stale start time.
    # Normal washer/dryer programs should never run for hundreds or thousands of minutes.
    if elapsed > MAX_ACTIVE_MINUTES:
        _set_output(
            kind,
            expected_end="Check status",
            expected_duration=0,
            remaining=0,
            profile="Invalid runtime",
            confidence=0,
        )
        return

    power = _safe_float(MACHINES[kind]["power"], 0.0)
    energy = _current_cycle_energy(kind)

    live["last_power"] = power
    live["power_sum"] += power
    live["power_count"] += 1

    if (
        elapsed >= CHECKPOINT_MINUTES
        and elapsed - live["last_point_minute"] >= CHECKPOINT_MINUTES
    ):
        if live["power_count"] > 0:
            avg_power = live["power_sum"] / live["power_count"]
        else:
            avg_power = power

        live["points"].append(
            {
                "m": int(elapsed),
                "e": round(energy, 4),
                "p": round(avg_power, 1),
            }
        )

        live["last_point_minute"] = int(elapsed)
        live["power_sum"] = 0.0
        live["power_count"] = 0

    _predict(kind, elapsed, now)


@time_trigger("startup")
def appliance_learning_startup():
    # Persist historical data.
    for kind in ["washer", "dryer"]:
        c = MACHINES[kind]
        state.persist(
            c["history"],
            default_value="0",
            default_attributes={
                "friendly_name": f'{c["friendly"]} learning data',
                "icon": "mdi:brain",
                "cycles": [],
                "max_cycles": MAX_CYCLES,
                "algorithm_version": ALGORITHM_VERSION,
                "history_validation": "enabled",
            },
        )
        cleaned_cycles, removed_points, removed_duplicates, removed_cycles = _sanitize_history(
            kind, _history(kind)
        )
        _save_history(kind, cleaned_cycles)

        # Always create the output entities.
        if _is_running(kind):
            _cycle_start(kind)
        else:
            _set_output(kind, "—", 0, 0, "Waiting for cycle", 0)

    log.info(f"Appliance Learning Predictor v{ALGORITHM_VERSION} started with CSV logging")


@state_trigger("input_boolean.washing_machine_running == 'on'")
def appliance_learning_washer_start():
    _cycle_start("washer")


@state_trigger("input_boolean.dryer_running == 'on'")
def appliance_learning_dryer_start():
    _cycle_start("dryer")


@state_trigger("input_boolean.washing_machine_running == 'off'")
def appliance_learning_washer_finish():
    if LIVE["washer"]["active"]:
        _cycle_finish("washer")


@state_trigger("input_boolean.dryer_running == 'off'")
def appliance_learning_dryer_finish():
    if LIVE["dryer"]["active"]:
        _cycle_finish("dryer")


@time_trigger("period(now, 1min)")
def appliance_learning_sampler(trigger_time=None):
    _sample_machine("washer", trigger_time)
    _sample_machine("dryer", trigger_time)


@service("pyscript.washer_learning_data_reset")
def appliance_learning_reset_washer():
    _save_history("washer", [])
    _set_output("washer", "—", 0, 0, "Learning data cleared", 0)
    log.info("Washing machine learning data cleared")


@service("pyscript.dryer_learning_data_reset")
def appliance_learning_reset_dryer():
    _save_history("dryer", [])
    _set_output("dryer", "—", 0, 0, "Learning data cleared", 0)
    log.info("Dryer learning data cleared")