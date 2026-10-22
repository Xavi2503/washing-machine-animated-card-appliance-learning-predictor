# Entity reference

The exact entity IDs are configurable in `MACHINES` at the top of `appliance_learning.py`.

## Inputs

| Mapping key | Expected value | Description |
| --- | --- | --- |
| `running` | `on` / `off` | Source of truth for whether a cycle is active |
| `power` | W | Current appliance power |
| `energy` | kWh | Cumulative smart-plug energy |
| `energy_start` | kWh | Cumulative energy captured at cycle start |
| `start_time` | datetime | Actual cycle start |
| `end_time` | datetime | Actual cycle end |
| `last_duration` | min | Actual duration of the completed cycle |
| `last_energy` | kWh | Actual energy used by the completed cycle |

## Predictor outputs

| Mapping key | Example | Description |
| --- | --- | --- |
| `remaining` | `37` | Predicted remaining minutes |
| `expected_end` | `Today 14:52` | Human-readable expected finish |
| `expected_duration` | `91` | Predicted total cycle duration in minutes |
| `profile` | `Profile 1` | Learned cycle profile |
| `confidence` | `86` | Prediction confidence percentage |
| `learned` | `12` | Number of stored learned cycles |
| `history` | state + attributes | Persistent cycle-learning data |

## Important

The predictor assumes `last_duration`, `last_energy` and `end_time` are updated before the `running` helper turns off. This allows the finish trigger to learn the actual completed result.
