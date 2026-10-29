# Washing Machine Animated Card – Predictor Extension (prototype)

This is an **optional companion extension** for
[sionetta/wm_animated_ha_card](https://github.com/sionetta/wm_animated_ha_card).

It does **not** replace, fork, or bundle the original card. The official
Washing Machine Animated Card remains installed and updated separately.

The extension waits for the existing \`washing-machine-card\` web component,
then adds predictor-specific information inside the same card when the extra
entities are configured.

## Prototype status

This folder is groundwork for a future HACS frontend/plugin package.

Current target: Washing Machine Animated Card **v1.5.0**.

The prototype is deliberately fail-safe:

- if the original card is not available, nothing is changed;
- if the expected internal insertion point is not found, nothing is changed;
- extension errors are caught so the original card keeps working;
- no predictor fields configured = no extension UI.

## Planned configuration

The normal card configuration remains the same. The extension only reacts to
additional optional keys:

\`\`\`yaml
type: custom:washing-machine-card

status_entity: input_boolean.washer_running
power_entity: sensor.washer_power

# Official v1.5.0 option
remaining_entity: sensor.washer_remaining_time

# Optional Predictor Extension options
expected_end_entity: sensor.washer_expected_end
last_end_entity: input_datetime.washer_last_end
confidence_entity: sensor.washer_prediction_confidence
profile_entity: sensor.washer_cycle_profile
learned_cycles_entity: sensor.washer_learned_cycles

# Existing card entities reused by the extension
last_wash_entity: input_datetime.washer_last_start
duration_entity: input_number.washer_last_duration
\`\`\`

When enabled, the extension adds a predictor panel to the **same**
\`custom:washing-machine-card\` with:

**Start | Expected | Remaining | End | Duration**

and optional metadata:

**Confidence | Profile | Learned cycles**

## How the prototype attaches

The extension waits for:

\`\`\`js
customElements.whenDefined("washing-machine-card")
\`\`\`

and then augments the already registered card class.

It currently hooks the card's internal \`_build()\` and \`_update()\` methods.
This is useful for proving the concept, but those methods are not a public API.

If the upstream maintainer prefers a public extension hook, event, slot, or
other integration point, this prototype should be adapted to use that instead.

## Installation for development only

Load the official Washing Machine Animated Card resource first, then this
extension as a second Lovelace JavaScript module.

Do not publish this prototype as a final HACS plugin yet. A production version
should live in its own frontend/plugin repository so the predictor integration
and the companion frontend can be versioned independently.

## Design goal

Keep responsibilities separate:

\`\`\`text
Appliance / smart plug
        ↓
Appliance Learning Predictor
        ↓
remaining_entity + predictor metadata
        ↓
Washing Machine Animated Card
        +
optional Predictor Extension
\`\`\`

The original card remains the primary UI component. The extension only exposes
additional information produced by the predictor.
