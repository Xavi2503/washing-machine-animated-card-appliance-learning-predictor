# Changelog

## Home Assistant integration 0.1.0

- Prepared repository metadata for HACS validation.
- Added a HACS-installable Home Assistant custom integration.
- Added UI-based Config Flow and editable Options Flow.
- Added automatic power-based cycle detection with configurable thresholds/delays.
- Added optional existing-status-entity cycle detection.
- Added native sensors for remaining time, expected end, expected duration, confidence, profile and learned cycles.
- Added persistent learning history using Home Assistant storage.
- Added English and Dutch translations.
- Added HACS and hassfest validation workflows.
- Preserved the standalone Pyscript predictor as the advanced/manual installation path.

## 2.3

- Added `MAX_LEARN_DURATION` safety limit for training data.
- Rejects unrealistic long/merged cycles instead of learning them.
- Startup history sanitization removes previously stored cycles above the safety limit.
- Retains CSV prediction logging and v2 prediction logic.

## 2.2

- Added per-appliance CSV prediction/evaluation logging.
- Logs prediction samples and actual post-cycle error.

## 2.1

- Added stronger historical-data validation and cleanup.
- Added protection against invalid/stale checkpoint data.

## 2.0

- Added phase-aligned historical matching.
- Added profile-aware bias correction.
- Added prediction stabilization and confidence improvements.
