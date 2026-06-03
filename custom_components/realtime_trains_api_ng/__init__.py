"""The Realtime Trains API (Next Generation) integration."""
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .rtt_api import RttApi, RttApiError
from .const import (
    DOMAIN,
    CONF_API_AUTH_TOKEN,
    CONF_QUERIES,
    CONF_ORIGIN,
    CONF_DESTINATION,
    CONF_JOURNEY_DATA_FOR_NEXT_X_TRAINS,
    CONF_STOPS_OF_INTEREST,
    CONF_TIME_OFFSET,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Realtime Trains API from a config entry.

    This is called when the integration is added to Home Assistant.
    It creates the API client, coordinators for each query, and platforms.
    """

    api_auth_token = entry.data[CONF_API_AUTH_TOKEN]
    # Check both data and options for queries
    queries = entry.options.get(CONF_QUERIES, entry.data.get(CONF_QUERIES, []))

    _LOGGER.info(f"Setting up RTT integration with {len(queries)} queries")

    # Create API client
    api = RttApi(api_auth_token=api_auth_token)

    # Create a data coordinator for each query
    coordinators = {}
    for idx, query in enumerate(queries):
        _LOGGER.info(f"Creating coordinator for query {idx}: {query}")
        coordinator = RttDataUpdateCoordinator(
            hass=hass,
            api=api,
            query=query,
            query_idx=idx,
        )
        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()
        coordinators[idx] = coordinator

    # Store API and coordinators in hass.data for use by other components
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinators": coordinators,
        "queries": queries,
    }

    # Set up sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info(f"RTT integration setup complete with {len(coordinators)} coordinators")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry when the integration is removed."""

    # Unload all platforms (this removes entities)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Clean up data
        api = hass.data[DOMAIN][entry.entry_id]["api"]
        await api.close()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Update a config entry when options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)
    return True


class RttDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to manage fetching Realtime Trains API data.
    
    Home Assistant uses coordinators to manage periodic data updates.
    This coordinator fetches train data at regular intervals and handles errors.
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        api: RttApi,
        query: dict,
        query_idx: int,
    ):
        """Initialize the data update coordinator.
        
        Args:
            hass: Home Assistant instance
            api: RttApi client
            query: Query configuration dict with origin, destination, etc.
            query_idx: Index of this query
        """
        self.api = api
        self.query = query
        self.query_idx = query_idx
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"RTT Query {query_idx}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
    
    async def _async_update_data(self) -> dict:
        """Fetch data from RTT API.
        
        This is called periodically (every 90 seconds by default).
        Returns the data or raises UpdateFailed on error.
        """
        try:
            origin = self.query.get(CONF_ORIGIN)
            destination = self.query.get(CONF_DESTINATION)
            journey_data_for_x_trains = self.query.get(
                CONF_JOURNEY_DATA_FOR_NEXT_X_TRAINS, 0
            )
            stops_of_interest = self.query.get(CONF_STOPS_OF_INTEREST, [])
            time_offset_config = self.query.get(CONF_TIME_OFFSET, {})
            
            # Get time offset in minutes if specified
            time_offset_minutes = 0
            if time_offset_config:
                time_offset_minutes = time_offset_config.get("minutes", 0)
            
            # Fetch departures from origin station
            departures_data = await self.api.search_departures(
                crs=origin,
                destination_crs=destination,
                time_offset_minutes=time_offset_minutes,
            )
            
            if not departures_data:
                return {
                    "departures": [],
                    "station": None,
                    "destination": None,
                }
            
            # New API response structure: services array is at root
            departures = departures_data.get("services", [])
            # Location info is in query.location
            station = departures_data.get("query", {}).get("location", {})
            
            # Optionally fetch detailed journey data for first X trains
            if journey_data_for_x_trains > 0:
                for service in departures[:journey_data_for_x_trains]:
                    # New API structure: uniqueIdentity in scheduleMetadata
                    schedule_metadata = service.get("scheduleMetadata", {})
                    service_uid = schedule_metadata.get("uniqueIdentity", "")
                    
                    # Extract departure date from scheduleMetadata
                    departure_date = schedule_metadata.get("departureDate", "")
                    
                    if service_uid:
                        try:
                            # Get detailed service information
                            service_info = await self.api.fetch_service_details(
                                service_uid,
                                departure_date,
                            )
                            
                            if service_info:
                                # Extract locations information (new API calls it "locations")
                                locations = service_info.get("service", {}).get("locations", [])
                                
                                # Create journey data dict
                                service["journey_data"] = {
                                    "stops": len(locations),
                                    "estimated_arrival": None,
                                    "scheduled_arrival": None,
                                    "stops_of_interest": []
                                }
                                
                                # Get arrival time from temporalData
                                if locations:
                                    last_location = locations[-1]
                                    temporal_data = last_location.get("temporalData", {})
                                    arrival_data = temporal_data.get("arrival", {})
                                    if arrival_data:
                                        service["journey_data"]["scheduled_arrival"] = arrival_data.get("scheduleAdvertised")
                                        service["journey_data"]["estimated_arrival"] = arrival_data.get("realtimeForecast")
                                
                                # Find stops of interest within this journey
                                for stop_code in stops_of_interest:
                                    for location in locations:
                                        loc = location.get("location", {})
                                        if loc.get("shortCodes") and stop_code in loc.get("shortCodes", []):
                                            temporal_data = location.get("temporalData", {})
                                            arrival_data = temporal_data.get("arrival", {})
                                            service["journey_data"]["stops_of_interest"].append({
                                                "stop_code": stop_code,
                                                "name": loc.get("description"),
                                                "scheduled_arrival": arrival_data.get("scheduleAdvertised") if arrival_data else None,
                                                "estimated_arrival": arrival_data.get("realtimeForecast") if arrival_data else None,
                                            })
                        
                        except RttApiError as err:
                            _LOGGER.warning(
                                f"Could not fetch journey data for {service_uid}: {err}"
                            )
            
            return {
                "departures": departures,
                "station": station,
                "origin": origin,
                "destination": destination,
            }
        
        except RttApiError as err:
            raise UpdateFailed(f"Error from RTT API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err
