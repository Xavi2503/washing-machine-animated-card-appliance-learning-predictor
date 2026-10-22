# HACS / plug-and-play installation

This is the easiest way to use Appliance Learning Predictor.

## 1. Add the repository to HACS

Until the project is included in the default HACS catalog, add this repository as a **custom repository** of type **Integration**:

`https://github.com/Xavi2503/washing-machine-animated-card-appliance-learning-predictor`

Install **Appliance Learning Predictor** and restart Home Assistant.

## 2. Add the integration

Go to:

**Settings → Devices & services → Add integration → Appliance Learning Predictor**

Choose:

- appliance type;
- a power sensor;
- a cumulative energy sensor;
- cycle detection mode.

### Automatic power detection

For a smart plug, choose **Automatic from power**. Defaults are deliberately conservative:

- start threshold: `50 W`;
- stop threshold: `15 W`;
- start delay: `10 s`;
- stop delay: `15 min`;
- maximum learned cycle: `360 min`.

The 15-minute stop delay is intentional. Washing machines can spend several minutes at very low power during a normal cycle. A short stop delay can therefore split one physical wash into multiple cycles.

### Existing status entity

If Home Assistant already has a reliable running/status entity, choose **Existing status entity** and select it. Enter the states that mean the appliance is actively in a cycle.

## 3. Predictor sensors

The integration automatically creates entities for:

- Remaining time (minutes)
- Expected end (timestamp)
- Expected duration (minutes)
- Prediction confidence (%)
- Cycle profile
- Learned cycles

The **Remaining time** sensor is the primary generic output intended for cards such as Washing Machine Animated Card.

## Learning

The first cycle cannot be predicted accurately because there is no history yet. Prediction quality improves as the integration records completed cycles. Up to 40 cycles are retained.

Bad/merged cycles longer than the configured maximum are rejected from the learning history.
