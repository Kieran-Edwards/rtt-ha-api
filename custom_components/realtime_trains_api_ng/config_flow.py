"""Config flow for Realtime Trains API integration."""
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_TOKEN,
    CONF_QUERIES,
    CONF_ORIGIN,
    CONF_DESTINATION,
    CONF_JOURNEY_DATA_FOR_NEXT_X_TRAINS,
    CONF_STOPS_OF_INTEREST,
    CONF_SENSOR_NAME,
    CONF_TIME_OFFSET,
)
from .rtt_api import RttApi, RttApiError


class RttConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RTT integration."""
    
    VERSION = 1
    
    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial setup step - token entry."""
        
        errors = {}
        
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            
            # Validate token by testing API connection
            api = RttApi(token=token)
            try:
                info = await api.get_api_info()
                if not info:
                    errors["base"] = "invalid_token"
                else:
                    # Token is valid! Store it and move to queries step
                    await api.close()
                    return await self.async_step_queries()
            
            except RttApiError as err:
                errors["base"] = "cannot_connect"
                _LOGGER.error(f"Token validation error: {err}")
            
            finally:
                await api.close()
        
        # Show token input form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_TOKEN): str,
            }),
            errors=errors,
            description_placeholders={
                "learn_more": "Get your bearer token from https://api-portal.rtt.io/",
            },
        )
    
    async def async_step_queries(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle queries setup step."""
        
        if user_input is not None:
            # Get token from previous step
            token = self.context.get("token")
            
            # Create config entry with token and queries
            return self.async_create_entry(
                title="Realtime Trains API",
                data={
                    CONF_TOKEN: token,
                    CONF_QUERIES: user_input.get(CONF_QUERIES, []),
                },
            )
        
        # Show form for adding queries
        return self.async_show_form(
            step_id="queries",
            data_schema=vol.Schema({
                vol.Optional(CONF_QUERIES, default=[]): vol.All(
                    cv.ensure_list,
                    vol.Length(min=1),
                ),
            }),
            description_placeholders={
                "example": "Example query: origin=LDS destination=KGX",
            },
        )


# Helper imports
import homeassistant.helpers.config_validation as cv
import logging

_LOGGER = logging.getLogger(__name__)
