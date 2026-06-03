"""Wrapper for the Realtime Trains Next Generation API."""
import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any

from .const import RTT_API_BASE_URL, RTT_API_VERSION

_LOGGER = logging.getLogger(__name__)


class RttApi:
    """Client for the Realtime Trains Next Generation API."""
    
    def __init__(self, token: str):
        """Initialize the RTT API client.
        
        Args:
            token: Bearer token for API authentication from https://api-portal.rtt.io/
        """
        self.token = token
        self.base_url = f"{RTT_API_BASE_URL}/api/{RTT_API_VERSION}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit_info = {}
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to the RTT API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (without base URL)
            params: Query parameters
            
        Returns:
            Response JSON as dictionary
            
        Raises:
            RttApiError: If the API request fails
        """
        session = await self._get_session()
        url = f"{self.base_url}/{endpoint}"
        
        # Bearer token authentication header
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        
        try:
            async with session.request(
                method,
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                # Extract rate limit info from response headers
                self._extract_rate_limit_headers(response.headers)
                
                # Handle different response codes
                if response.status == 401:
                    raise RttApiError("Unauthorized - Check your bearer token")
                elif response.status == 429:
                    retry_after = response.headers.get('Retry-After', 'Unknown')
                    raise RttApiError(f"Rate limited - retry after {retry_after}s")
                elif response.status == 404:
                    _LOGGER.warning(f"Not found: {url}")
                    return {}
                elif response.status >= 400:
                    raise RttApiError(f"API returned status {response.status}")
                
                return await response.json()
                
        except asyncio.TimeoutError:
            raise RttApiError("API request timeout (10 seconds)")
        except aiohttp.ClientError as err:
            raise RttApiError(f"Connection error: {err}")
    
    def _extract_rate_limit_headers(self, headers):
        """Extract rate limit information from response headers.
        
        RTT API returns headers like:
        - X-RateLimit-Limit-Minute
        - X-RateLimit-Remaining-Minute
        - etc.
        """
        for header, value in headers.items():
            if header.lower().startswith("x-ratelimit"):
                try:
                    self.rate_limit_info[header] = int(value)
                except ValueError:
                    self.rate_limit_info[header] = value
    
    async def search_departures(
        self,
        crs: str,
        destination_crs: Optional[str] = None,
        time_offset_minutes: int = 0,
        time_window_minutes: int = 120,
    ) -> Dict[str, Any]:
        """Get departures from a station.
        
        Args:
            crs: CRS code of origin station (e.g., 'LDS' for Leeds)
            destination_crs: Optional CRS to filter by destination
            time_offset_minutes: Minutes from now to start looking
            time_window_minutes: Time window width
            
        Returns:
            Dictionary with 'location' and 'services' keys
        """
        try:
            endpoint = f"locations/{crs}/departures"
            
            params = {}
            if time_offset_minutes != 0:
                params["fromMinutes"] = time_offset_minutes
            if time_window_minutes != 120:
                params["toMinutes"] = time_offset_minutes + time_window_minutes
            
            data = await self._request("GET", endpoint, params)
            
            # Filter by destination if provided
            if destination_crs and data.get("services"):
                filtered = []
                for service in data["services"]:
                    # Check if this service goes to our destination
                    destinations = service.get("destination", [])
                    if destinations and destinations[0].get("crs") == destination_crs:
                        filtered.append(service)
                data["services"] = filtered
            
            return data
            
        except RttApiError as err:
            _LOGGER.error(f"Error fetching departures from {crs}: {err}")
            return {}
    
    async def search_arrivals(
        self,
        crs: str,
        origin_crs: Optional[str] = None,
        time_offset_minutes: int = 0,
        time_window_minutes: int = 120,
    ) -> Dict[str, Any]:
        """Get arrivals at a station.
        
        Args:
            crs: CRS code of destination station
            origin_crs: Optional CRS to filter by origin
            time_offset_minutes: Minutes from now to start looking
            time_window_minutes: Time window width
            
        Returns:
            Dictionary with 'location' and 'services' keys
        """
        try:
            endpoint = f"locations/{crs}/arrivals"
            
            params = {}
            if time_offset_minutes != 0:
                params["fromMinutes"] = time_offset_minutes
            if time_window_minutes != 120:
                params["toMinutes"] = time_offset_minutes + time_window_minutes
            
            data = await self._request("GET", endpoint, params)
            
            # Filter by origin if provided
            if origin_crs and data.get("services"):
                filtered = []
                for service in data["services"]:
                    origins = service.get("origin", [])
                    if origins and origins[0].get("crs") == origin_crs:
                        filtered.append(service)
                data["services"] = filtered
            
            return data
            
        except RttApiError as err:
            _LOGGER.error(f"Error fetching arrivals at {crs}: {err}")
            return {}
    
    async def fetch_service_details(
        self,
        service_uid: str,
        service_date: str,
    ) -> Dict[str, Any]:
        """Get detailed information about a specific train service.
        
        Args:
            service_uid: Unique service identifier
            service_date: Service date in format YYYY-MM-DD
            
        Returns:
            Dictionary with detailed service information including all stops
        """
        try:
            endpoint = f"services/{service_uid}/{service_date}"
            return await self._request("GET", endpoint)
        except RttApiError as err:
            _LOGGER.error(f"Error fetching service {service_uid}: {err}")
            return {}
    
    async def get_api_info(self) -> Dict[str, Any]:
        """Get API information including version.
        
        Useful for validating the token and checking API status.
        
        Returns:
            Dictionary with API version and info
        """
        try:
            return await self._request("GET", "api/info")
        except RttApiError as err:
            _LOGGER.error(f"Error fetching API info: {err}")
            return {}


class RttApiError(Exception):
    """Exception raised for RTT API errors."""
    pass
