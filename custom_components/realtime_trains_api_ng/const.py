"""Constants for the Realtime Trains API (Next Generation) integration."""

DOMAIN = "realtime_trains_api_ng"

# Configuration keys - these match what appears in configuration.yaml
CONF_API_AUTH_TOKEN = "api_auth_token"  # Long-lived token from api-portal.rtt.io
CONF_BEARER_TOKEN = "bearer_token"  # Short-lived token (30 mins), exchanged from API auth token
CONF_BEARER_TOKEN_EXPIRY = "bearer_token_expiry"  # Timestamp when bearer token expires
CONF_QUERIES = "queries"
CONF_ORIGIN = "origin"
CONF_DESTINATION = "destination"
CONF_JOURNEY_DATA_FOR_NEXT_X_TRAINS = "journey_data_for_next_x_trains"
CONF_STOPS_OF_INTEREST = "stops_of_interest"
CONF_SENSOR_NAME = "sensor_name"
CONF_TIME_OFFSET = "time_offset"
CONF_INCLUDE_PAST_TRAINS = "include_past_trains"
CONF_PAST_HOURS = "past_hours"

# Default values
DEFAULT_SCAN_INTERVAL = 90  # seconds between API calls

# RTT API Configuration
RTT_API_BASE_URL = "https://data.rtt.io"
RTT_API_VERSION = "v1"

# Rate limits (from RTT API documentation)
RTT_RATE_LIMIT_MINUTE = 30
RTT_RATE_LIMIT_HOUR = 750
RTT_RATE_LIMIT_DAY = 9000
RTT_RATE_LIMIT_WEEK = 30000
