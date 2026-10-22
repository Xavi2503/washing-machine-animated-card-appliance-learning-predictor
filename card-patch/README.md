# Washing Machine Animated Card — remaining_entity prototype

This directory contains an **upstream-ready prototype** for the planned `remaining_entity` support in [sionetta/wm_animated_ha_card](https://github.com/sionetta/wm_animated_ha_card).

It is based on upstream `main` blob:

`f0f919415f50cc0b41386bc12b3b983d6191d0e2`

This is **not an official release of the card**. It is provided so the card author and other contributors can review/test the interface before or during the upstream implementation.

## Interface

```yaml
type: custom:washing-machine-card
status_entity: binary_sensor.washing_in_progress
power_entity: sensor.washing_machine_power
remaining_entity: sensor.washing_machine_remaining_time
```

`remaining_entity` is optional. The prototype accepts:

- a numeric duration in minutes;
- a numeric duration with common Home Assistant units such as seconds or hours;
- an end timestamp;
- a duration string in `H:MM:SS` format.

When a valid remaining value is available during an active/paused cycle:

- the appliance display shows remaining time;
- the ring shows remaining time;
- the ring label changes to the localized **Remaining** label.

If the entity is missing, unavailable or cannot be parsed, the card falls back to its existing elapsed-time behavior. Existing configurations therefore remain backwards compatible.

## Languages

The prototype includes the remaining-time ring label for all languages currently shipped by the card:

- English
- Russian
- German
- French
- Dutch
- Portuguese

## Purpose

The card stays generic: it does not calculate predictions. Any Home Assistant entity can supply the remaining value.

The companion **Appliance Learning Predictor** integration in this repository is one possible source, but smart appliances, Home Connect, WashData or other integrations can provide the same interface.

## Upstream status

The card author has already indicated that generic remaining-time support is planned. This prototype is offered as implementation/testing material; the upstream maintainer remains free to use, adapt or replace any part of it.
