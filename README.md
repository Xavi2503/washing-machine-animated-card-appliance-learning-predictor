# Washing Machine Animated Card – Appliance Learning Predictor

A local learning predictor for Home Assistant appliances such as washing machines and dryers.

The project provides both a **native Home Assistant/HACS integration** and an advanced **Pyscript** implementation. Both learn from completed cycles, compare the live power/energy pattern with historical cycles, and expose entities that dashboards or Lovelace cards can display.

It is deliberately **UI-independent**: the predictor does the learning, while the card only displays the result.

## Three ways to use this project

### 1. HACS / Home Assistant integration — recommended

For most users, install **Appliance Learning Predictor** as a Home Assistant custom integration through HACS.

The setup wizard lets you:

- choose the appliance type;
- select the power and cumulative-energy sensors;
- use automatic power-based cycle detection, or an existing status entity;
- adjust start/stop thresholds and learning safety limits without editing Python.

The integration creates native Home Assistant sensors for remaining time, expected end, expected duration, prediction confidence, cycle profile and learned cycles.

See [HACS_INSTALLATION.md](HACS_INSTALLATION.md).

### 2. Pyscript — advanced/manual

The original `appliance_learning.py` remains available for advanced Home Assistant users who prefer complete control over helpers, cycle detection and entity IDs.

It uses the same learning concepts and remains a valid standalone option.

### 3. Washing Machine Animated Card integration

The predictor is designed to provide a generic remaining-time source for [Washing Machine Animated Card](https://github.com/sionetta/wm_animated_ha_card).

The upstream card does **not yet** expose its planned `remaining_entity` option in the current release. When that interface is available, the predictor's native remaining-time sensor is intended to plug into it directly. Until then, the predictor can still be used independently or with dashboards/custom card versions that support its entities.

## Why this project exists

Many appliances do not expose a reliable remaining-time sensor. Smart plugs usually provide only power and cumulative energy. This project uses those signals, together with previous completed cycles, to estimate the current cycle's remaining time.

This makes it a good companion for generic appliance cards such as [`sionetta/wm_animated_ha_card`](https://github.com/sionetta/wm_animated_ha_card). The card author has indicated that future remaining-time support will accept values from optional entities rather than implementing prediction inside the card itself. This predictor follows that same separation of responsibilities.

## Features

- Learns from completed washer and dryer cycles.
- Uses power and cycle-energy checkpoints.
- Phase-aligns the current cycle with historical cycles.
- Predicts remaining time and expected finish time.
- Estimates total cycle duration.
- Groups similar cycles into learned profiles.
- Exposes a confidence percentage.
- Applies bias correction based on earlier prediction errors.
- Stabilizes predictions to avoid excessive end-time jumping.
- Stores up to 40 completed cycles per appliance.
- Validates and sanitizes historical learning data on startup.
- Rejects unrealistic long cycles from training data.
- Writes CSV logs so predictions can be evaluated after a cycle.
- Runs locally in Home Assistant; no cloud API or paid service is required.

## Architecture

```text
Smart plug / appliance sensors
        │
        ├── power (W)
        ├── cumulative energy (kWh)
        └── cycle-running helper
                │
                ▼
      Appliance Learning Predictor
                │
        ┌───────┼──────────────────────┐
        ▼       ▼          ▼           ▼
 remaining   expected    profile    confidence
  minutes      end
        │
        ▼
Any Lovelace card / dashboard
```

The predictor **does not start or stop appliances** and does not decide when a physical appliance is finished. Your Home Assistant setup should provide a reliable `input_boolean` (or equivalent helper) representing whether the appliance cycle is active.

## Requirements

- Home Assistant
- [Pyscript](https://github.com/custom-components/pyscript) installed through HACS
- A power sensor in watts
- A cumulative energy sensor in kWh
- A reliable cycle-running helper
- Helpers for start/end time, last duration, cycle energy start and last cycle energy

## Installation

1. Install Pyscript through HACS and add the Pyscript integration to Home Assistant.
2. Create the helpers and sensors referenced in the `MACHINES` mapping, or change that mapping to your own entity IDs.
3. Create the directory:

   ```text
   /config/pyscript/logs/
   ```

4. Copy `appliance_learning.py` to:

   ```text
   /config/pyscript/appliance_learning.py
   ```

5. Reload/restart Pyscript.
6. Verify that the `pyscript.*` output entities are created.

See [`examples/helpers.yaml`](examples/helpers.yaml) for helper examples.

## Configuration

Configuration is intentionally kept in one mapping at the top of `appliance_learning.py`:

```python
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
}
```

Change only the entity IDs you need. A dryer mapping is included in the script as well.

## Output entities

For the example washer mapping, the predictor creates:

| Entity | Purpose |
| --- | --- |
| `pyscript.washer_remaining_time` | Remaining time in whole minutes |
| `pyscript.washer_expected_end` | Human-readable expected finish |
| `pyscript.washer_expected_duration` | Predicted total duration in minutes |
| `pyscript.washer_cycle_profile` | Learned/matched cycle profile |
| `pyscript.washer_prediction_confidence` | Confidence from 0–100% |
| `pyscript.washer_learned_cycles` | Number of learned cycles |
| `pyscript.washer_learning_data` | Persistent learning history and metadata |

The most important entity for generic card integration is:

```text
pyscript.washer_remaining_time
```

Its state is a number of **minutes**, which is suitable for a future generic `remaining_entity` interface.

## Example card integration

A future stock card that accepts a remaining-time entity could use:

```yaml
type: custom:washing-machine-card
status_entity: input_boolean.washer_running
power_entity: sensor.washer_power
remaining_entity: pyscript.washer_remaining_time
```

Additional optional predictor entities can also be exposed by cards that support them:

```yaml
expected_end_entity: pyscript.washer_expected_end
confidence_entity: pyscript.washer_prediction_confidence
profile_entity: pyscript.washer_cycle_profile
```

See [`examples/wm-animated-card.yaml`](examples/wm-animated-card.yaml).

## How learning works

Every minute, the script samples the active appliance. Every five minutes it creates a checkpoint containing:

- elapsed minutes
- cycle energy used so far
- average power around that checkpoint

For the current cycle it searches historical cycles for the closest pattern. It allows a small phase shift because real appliance cycles often change with load size, temperature, balancing and adaptive program logic.

The selected historical matches are converted into a remaining-time estimate. The predictor then applies:

1. profile matching,
2. historical weighting,
3. prediction confidence,
4. learned bias correction,
5. stability limits.

When the cycle ends, prediction samples are compared with the actual result. Those errors become part of the learning data for later cycles.

More detail is available in [`docs/how-it-works.md`](docs/how-it-works.md).

## Safety against bad cycle detection

The predictor depends on the external `running` helper being accurate. A stuck helper can otherwise make two physical cycles look like one very long cycle.

Version 2.3 therefore adds two protections:

- active runtimes above `MAX_ACTIVE_MINUTES` are flagged as invalid;
- completed cycles above `MAX_LEARN_DURATION` (default: 360 minutes) are **not learned** and are removed from historical training data during sanitization.

This protects the model from accidental merged cycles while still allowing long appliance programs.

`MAX_LEARN_DURATION` is deliberately configurable because appliance behavior varies.

## CSV prediction log

Each configured appliance writes a CSV file such as:

```text
/config/pyscript/logs/washer_prediction_log.csv
```

Fields include:

```text
timestamp,event,machine,cycle_id,elapsed_min,power_w,energy_kwh,
predicted_end,predicted_remaining_min,predicted_total_duration_min,
confidence_pct,profile,actual_end,actual_duration_min,actual_energy_kwh,
actual_remaining_min,error_actual_minus_predicted_min,algorithm_version
```

This makes it possible to see how a prediction converged and how large the prediction error was at each point in the cycle.

## Resetting learned data

The script exposes services:

```text
pyscript.washer_learning_data_reset
pyscript.dryer_learning_data_reset
```

Use these only when you intentionally want to erase the learned cycle history for that appliance.

## Current status

This repository contains the **v2.3 community edition** of a predictor that was originally developed and tested on a real Home Assistant washer/dryer setup.

It should currently be treated as an experimental/community project rather than a drop-in Home Assistant integration. Entity mapping and reliable cycle start/end detection remain installation-specific.

Feedback, real-world CSV logs and contributions are welcome.

## Related project

- [Washing Machine Animated Card](https://github.com/sionetta/wm_animated_ha_card) by `sionetta`

This predictor is a separate project and is not part of, or required by, the card above.

## License

MIT. See [`LICENSE`](LICENSE).
