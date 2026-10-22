"""Constants for Appliance Learning Predictor."""

DOMAIN = "appliance_learning_predictor"
NAME = "Appliance Learning Predictor"
VERSION = "0.1.0"
ALGORITHM_VERSION = "3.0-ha"


CONF_APPLIANCE_TYPE = "appliance_type"
CONF_POWER_ENTITY = "power_entity"
CONF_ENERGY_ENTITY = "energy_entity"
CONF_DETECTION_MODE = "detection_mode"
CONF_STATUS_ENTITY = "status_entity"
CONF_RUNNING_STATES = "running_states"
CONF_START_THRESHOLD = "start_threshold"
CONF_STOP_THRESHOLD = "stop_threshold"
CONF_START_DELAY = "start_delay"
CONF_STOP_DELAY = "stop_delay"
CONF_MAX_LEARN_DURATION = "max_learn_duration"

DETECTION_POWER = "power"
DETECTION_STATUS = "status"

APPLIANCE_TYPES = ["washer", "dryer", "dishwasher", "oven", "microwave"]

DEFAULT_START_THRESHOLD = 50.0
DEFAULT_STOP_THRESHOLD = 15.0
DEFAULT_START_DELAY = 10
DEFAULT_STOP_DELAY = 15
DEFAULT_MAX_LEARN_DURATION = 360
DEFAULT_RUNNING_STATES = "on,running,run,washing,drying,spinning,rinsing,heating,baking"

MAX_CYCLES = 40
MAX_ACTIVE_MINUTES = 600
MIN_LEARN_DURATION = 8
MIN_LEARN_ENERGY = 0.01
CHECKPOINT_MINUTES = 5
PHASE_SHIFT_LIMIT = 20
BIAS_MAX_MINUTES = 12
PROFILE_DURATION_TOLERANCE = 0.18
PROFILE_ENERGY_TOLERANCE = 0.35
UNKNOWN_SCORE_THRESHOLD = 0.90

STORAGE_VERSION = 1
POLL_SECONDS = 30
