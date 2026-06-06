"""Config flow for Realtime Trains API integration."""
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_API_AUTH_TOKEN,
    CONF_QUERIES,
    CONF_ORIGIN,
    CONF_DESTINATION,
    CONF_JOURNEY_DATA_FOR_NEXT_X_TRAINS,
    CONF_STOPS_OF_INTEREST,
    CONF_SENSOR_NAME,
    CONF_TIME_OFFSET,
    CONF_INCLUDE_PAST_TRAINS,
    CONF_PAST_HOURS,
)
from .rtt_api import RttApi, RttApiError


class RttConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RTT integration."""

    VERSION = 1
    
    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial setup step - API auth token entry."""

        errors = {}

        if user_input is not None:
            api_auth_token = user_input[CONF_API_AUTH_TOKEN].strip()

            # Validate token by testing token exchange
            api = RttApi(api_auth_token=api_auth_token)
            try:
                # Try to exchange for a bearer token
                bearer_token = await api._exchange_token()
                if not bearer_token:
                    errors["base"] = "invalid_token"
                else:
                    # Token is valid! Create config entry
                    await api.close()
                    return self.async_create_entry(
                        title="Realtime Trains API",
                        data={
                            CONF_API_AUTH_TOKEN: api_auth_token,
                            CONF_QUERIES: [],
                        },
                    )

            except RttApiError as err:
                errors["base"] = "cannot_connect"
                _LOGGER.error(f"Token validation error: {err}")

            finally:
                await api.close()

        # Show API auth token input form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_AUTH_TOKEN): str,
            }),
            errors=errors,
            description_placeholders={
                "learn_more": "Get your API authorization token from https://api-portal.rtt.io/",
            },
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return RttOptionsFlow()


class RttOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for RTT integration."""

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle options flow - add a new query."""

        errors = {}

        if user_input is not None:
            origin = user_input.get(CONF_ORIGIN, "").strip().upper()
            destination = user_input.get(CONF_DESTINATION, "").strip().upper()
            include_past_trains = user_input.get(CONF_INCLUDE_PAST_TRAINS, False)
            past_hours = user_input.get(CONF_PAST_HOURS, 2)
            journey_data_for_x_trains = user_input.get(CONF_JOURNEY_DATA_FOR_NEXT_X_TRAINS, 10)
            stops_of_interest_str = user_input.get("stops_of_interest_str", "").strip()

            if not origin or not destination:
                errors["base"] = "required_fields"
            else:
                # Add new query to existing queries
                current_queries = self.config_entry.options.get(CONF_QUERIES, [])
                new_query = {
                    CONF_ORIGIN: origin,
                    CONF_DESTINATION: destination,
                    CONF_JOURNEY_DATA_FOR_NEXT_X_TRAINS: journey_data_for_x_trains,
                }
                
                # Add optional past trains configuration
                if include_past_trains:
                    new_query[CONF_INCLUDE_PAST_TRAINS] = True
                    new_query[CONF_PAST_HOURS] = past_hours
                
                # Parse stops of interest if provided
                if stops_of_interest_str:
                    # Split by comma and strip whitespace
                    stops = [s.strip().upper() for s in stops_of_interest_str.split(",") if s.strip()]
                    if stops:
                        new_query[CONF_STOPS_OF_INTEREST] = stops
                
                current_queries.append(new_query)

                _LOGGER.info(f"Saving {len(current_queries)} queries to options: {current_queries}")

                # Update config entry options with new queries
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    options={
                        CONF_QUERIES: current_queries,
                    },
                )
                return self.async_create_entry(title="", data=None)

        # Show form for adding a query
        current_queries = self.config_entry.options.get(CONF_QUERIES, [])
        _LOGGER.info(f"Current queries in options: {current_queries}")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_ORIGIN): str,
                vol.Required(CONF_DESTINATION): str,
                vol.Optional(CONF_JOURNEY_DATA_FOR_NEXT_X_TRAINS, default=10): vol.Coerce(int),
                vol.Optional("stops_of_interest_str", default=""): str,
                vol.Optional(CONF_INCLUDE_PAST_TRAINS, default=False): bool,
                vol.Optional(CONF_PAST_HOURS, default=2): vol.Coerce(int),
            }),
            description_placeholders={
                "example": "LDS for Leeds, KGX for King's Cross",
            },
        )


# Helper imports
import logging

_LOGGER = logging.getLogger(__name__)
