"""Sensor platform for Realtime Trains API."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_ORIGIN,
    CONF_DESTINATION,
    CONF_SENSOR_NAME,
    CONF_JOURNEY_DATA_FOR_NEXT_X_TRAINS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform.

    Called when the integration is set up. Creates a sensor for each query.
    """

    data = hass.data[DOMAIN][entry.entry_id]
    coordinators = data["coordinators"]
    queries = data["queries"]

    _LOGGER.info(f"Setting up sensor platform with {len(queries)} queries")

    sensors = []

    # Create a sensor for each query
    for idx, (query, coordinator) in enumerate(zip(queries, coordinators.values())):
        _LOGGER.info(f"Creating sensor for query {idx}: {query}")
        sensors.append(
            RttTrainSensor(
                coordinator=coordinator,
                query=query,
                query_idx=idx,
                entry_id=entry.entry_id,
            )
        )

    _LOGGER.info(f"Adding {len(sensors)} sensors")
    async_add_entities(sensors)


class RttTrainSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing next train departures."""
    
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:train"
    _attr_unit_of_measurement = "min"
    
    def __init__(
        self,
        coordinator,
        query: Dict[str, Any],
        query_idx: int,
        entry_id: str,
    ):
        """Initialize the sensor.
        
        Args:
            coordinator: Data update coordinator
            query: Query configuration
            query_idx: Index of this query
            entry_id: Config entry ID
        """
        super().__init__(coordinator)
        
        self.query = query
        self.query_idx = query_idx
        self._attr_unique_id = f"rtt_{entry_id}_query_{query_idx}"
        
        # Generate sensor name
        origin = query.get(CONF_ORIGIN, "Unknown")
        destination = query.get(CONF_DESTINATION, "Unknown")
        custom_name = query.get(CONF_SENSOR_NAME)
        
        if custom_name:
            self._attr_name = custom_name
        else:
            self._attr_name = f"Next train from {origin} to {destination}"
        
        self.origin = origin
        self.destination = destination
    
    @property
    def native_value(self) -> Optional[int]:
        """Return the number of minutes until next train departure.
        
        This is the main state of the sensor - shown as a number.
        """
        if not self.coordinator.data:
            return None
        
        departures = self.coordinator.data.get("departures", [])
        if not departures:
            return None
        
        # Get the next/first train
        next_train = departures[0]
        
        # Parse scheduled departure time from temporalData.departure
        temporal_data = next_train.get("temporalData", {})
        departure_data = temporal_data.get("departure", {})
        scheduled = departure_data.get("scheduleAdvertised")
        if not scheduled:
            return None
        
        try:
            # ISO-8601 format: 2024-01-15T14:30:00+00:00
            departure_time = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
            now = datetime.now(departure_time.tzinfo)
            
            # Calculate minutes until departure
            delta = departure_time - now
            minutes = int(delta.total_seconds() // 60)
            
            # Don't return negative values
            return max(0, minutes)
        
        except Exception as err:
            _LOGGER.error(f"Error parsing departure time: {err}")
            return None
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes with detailed train information.
        
        These show up in Home Assistant as additional data you can use
        in automations and templates.
        """
        if not self.coordinator.data:
            return {}
        
        departures = self.coordinator.data.get("departures", [])
        
        attributes = {
            "station": self.coordinator.data.get("station", {}),
            "next_trains": [],
        }
        
        # Add details for first 10 upcoming trains
        for service in departures[:10]:
            train_data = self._parse_service(service)
            attributes["next_trains"].append(train_data)
        
        # Add rate limit information if available
        if hasattr(self.coordinator.api, "rate_limit_info"):
            attributes["rate_limit_info"] = self.coordinator.api.rate_limit_info
        
        return attributes
    
    def _parse_service(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Parse service data into a readable format.
        
        Converts API response into a nice dict structure.
        """
        
        # Extract schedule metadata
        schedule_metadata = service.get("scheduleMetadata", {})
        
        # Extract temporal data for departure
        temporal_data = service.get("temporalData", {})
        departure_data = temporal_data.get("departure", {})
        scheduled_dep = departure_data.get("scheduleAdvertised", "")
        estimated_dep = departure_data.get("realtimeForecast") or scheduled_dep
        
        # Calculate minutes until departure
        minutes_until = None
        try:
            dep_time = datetime.fromisoformat(scheduled_dep.replace("Z", "+00:00"))
            now = datetime.now(dep_time.tzinfo)
            delta = dep_time - now
            minutes_until = max(0, int(delta.total_seconds() // 60))
        except Exception:
            pass
        
        # Extract location metadata for platform
        location_metadata = service.get("locationMetadata", {})
        platform_data = location_metadata.get("platform", {})
        platform = platform_data.get("planned") if platform_data else None
        
        # Extract origin and destination
        origin_list = service.get("origin", [])
        dest_list = service.get("destination", [])
        
        # Debug logging to see actual structure
        _LOGGER.debug(f"Origin list structure: {origin_list}")
        _LOGGER.debug(f"Destination list structure: {dest_list}")
        
        origin_name = origin_list[0].get("location", {}).get("description", "Unknown") if origin_list else "Unknown"
        # Try multiple possible locations for CRS code
        origin_crs = "Unknown"
        if origin_list:
            loc = origin_list[0].get("location", {})
            origin_crs = loc.get("shortCodes", ["Unknown"])[0] if loc.get("shortCodes") else "Unknown"
            if origin_crs == "Unknown":
                # Try crs field directly
                origin_crs = loc.get("crs", "Unknown")
        
        dest_name = dest_list[0].get("location", {}).get("description", "Unknown") if dest_list else "Unknown"
        dest_crs = "Unknown"
        if dest_list:
            loc = dest_list[0].get("location", {})
            dest_crs = loc.get("shortCodes", ["Unknown"])[0] if loc.get("shortCodes") else "Unknown"
            if dest_crs == "Unknown":
                # Try crs field directly
                dest_crs = loc.get("crs", "Unknown")
        
        # Extract basic service info
        train_info = {
            "service_uid": schedule_metadata.get("uniqueIdentity"),
            "operator": schedule_metadata.get("operator", {}).get("name", "Unknown"),
            "scheduled_departure": scheduled_dep,
            "estimated_departure": estimated_dep,
            "platform": platform,
            "origin": origin_name,
            "origin_crs": origin_crs,
            "destination": dest_name,
            "destination_crs": dest_crs,
            "minutes": minutes_until,
            "stops": None,
            "journey_time_mins": None,
            "scheduled_arrival": None,
            "estimated_arrival": None,
            "stops_of_interest": None,
        }
        
        # Add journey data if it was fetched
        if "journey_data" in service:
            journey = service["journey_data"]
            train_info["stops"] = journey.get("stops")
            train_info["scheduled_arrival"] = journey.get("scheduled_arrival")
            train_info["estimated_arrival"] = journey.get("estimated_arrival")
            
            # Calculate journey time if we have both times
            if (
                scheduled_dep
                and journey.get("scheduled_arrival")
            ):
                try:
                    dep = datetime.fromisoformat(scheduled_dep.replace("Z", "+00:00"))
                    arr = datetime.fromisoformat(
                        journey["scheduled_arrival"].replace("Z", "+00:00")
                    )
                    train_info["journey_time_mins"] = int((arr - dep).total_seconds() // 60)
                except Exception:
                    pass
            
            # Add stops of interest
            if journey.get("stops_of_interest"):
                train_info["stops_of_interest"] = journey["stops_of_interest"]
        
        return train_info
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
