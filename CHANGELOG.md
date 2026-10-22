# Changelog

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
