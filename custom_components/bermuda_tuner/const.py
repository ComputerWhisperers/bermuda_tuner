"""Constants for Bermuda Tuner."""

DOMAIN = "bermuda_tuner"
BERMUDA_DOMAIN = "bermuda"
VERSION = "1.0.0"

CONF_CONVERSATION_AGENT = "conversation_agent"
CONF_AI_ENABLED = "ai_enabled"

TUNABLE_KEYS = {
    "attenuation",
    "devtracker_nothome_timeout",
    "max_area_radius",
    "max_velocity",
    "ref_power",
    "rssi_offsets",
    "smoothing_samples",
    "update_interval",
}

DEFAULTS = {
    "attenuation": 3.0,
    "devtracker_nothome_timeout": 30,
    "max_area_radius": 20,
    "max_velocity": 3.0,
    "ref_power": -55.0,
    "rssi_offsets": {},
    "smoothing_samples": 20,
    "update_interval": 10,
}
