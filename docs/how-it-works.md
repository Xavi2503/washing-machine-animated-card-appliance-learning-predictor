# How the predictor works

The Appliance Learning Predictor does not attempt to identify a manufacturer's program name. It learns recurring **cycle shapes** from Home Assistant data.

## 1. Cycle boundaries

The surrounding Home Assistant setup owns cycle detection. When the configured `running` helper turns on, the predictor starts an in-memory cycle. When it turns off, the predictor evaluates and optionally learns that completed cycle.

This design keeps the predictor independent from appliance brands and smart-plug thresholds.

## 2. Checkpoints

During an active cycle the sampler runs once per minute. At the configured checkpoint interval (default: five minutes), it stores:

- elapsed minute (`m`)
- cycle energy (`e`)
- average power (`p`)

The energy value is the energy consumed during the current cycle, not the lifetime cumulative smart-plug reading.

## 3. Historical matching

For a prediction, the current checkpoints are compared with historical completed cycles. The matcher considers both energy and power behavior.

A limited phase shift is allowed. This matters because an otherwise similar cycle can reach rinse/spin/heating phases a few minutes earlier or later depending on load, temperature and appliance decisions.

## 4. Profiles

Completed cycles with similar total duration and energy usage are grouped into simple learned profiles. A new cycle can therefore match a family of historically similar cycles rather than one exact run.

If the live pattern differs too much from known history, the predictor reports a new/unknown profile and lowers confidence.

## 5. Remaining-time estimate

Historical matches produce candidate remaining times. Better matches contribute more strongly. Newer history also receives a small additional weight.

The raw estimate is then adjusted using learned prediction error (bias correction).

## 6. Stabilization

Appliance power is noisy and individual phases can vary. A useful countdown should not jump wildly every minute. The stabilizer therefore limits how quickly a predicted remaining time can move unless the evidence is strong.

## 7. Confidence

Confidence combines several signals, including:

- quality of the historical match
- progress through the current cycle
- amount of learning history available
- whether the pattern appears known or unknown

Confidence is intentionally lower early in a cycle and with very little history.

## 8. Learning from prediction error

During a cycle, periodic prediction samples are kept in memory. At completion, the script compares each prediction with the actual remaining time at that point.

For example:

```text
elapsed: 60 min
predicted remaining: 20 min
actual final duration: 88 min
actual remaining at minute 60: 28 min
error: +8 min
```

Positive error means the prediction was too optimistic (too early). Negative error means it was too pessimistic (too late).

Those errors are stored with the learned cycle and can be used as bias correction for later similar cycles.

## 9. History validation

Bad cycle detection can contaminate a learning model. Version 2.3 sanitizes persistent history on startup and rejects unrealistic long cycles.

The default training maximum is 360 minutes. Users with legitimately longer appliance programs can raise `MAX_LEARN_DURATION`.

## 10. UI indepence

The predictor exposes states; it does not render a dashboard. The main output for generic integrations is:

```text
pyscript.washer_remaining_time
```

which is expressed as whole minutes.

A Lovelace card can then decide whether that value belongs in a ring, display, text row or other UI element.
