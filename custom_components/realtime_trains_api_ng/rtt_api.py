"""Wrapper for the Realtime Trains Next Generation API."""
import aiohttp
import asyncio
import logging
import time
import datetime
from typing import Optional, Dict, Any

from .const import RTT_API_BASE_URL, RTT_API_VERSION

_LOGGER = logging.getLogger(__name__)


class RttApi:
    """Client for the Realtime Trains Next Generation API."""
    
    def __init__(self, api_auth_token: str):
        """Initialize the RTT API client.
        
        Args:
            api_auth_token: API authorization token from https://api-portal.rtt.io/
                           This is used to exchange for a bearer token
        """
        self.api_auth_token = api_auth_token
        self.bearer_token: Optional[str] = None
        self.bearer_token_expiry: Optional[float] = None
        self.base_url = RTT_API_BASE_URL
        self.auth_url = f"{RTT_API_BASE_URL}/api/get_access_token"
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
    
    async def _exchange_token(self) -> str:
        """Exchange API auth token for bearer token.
        
        Returns:
            Bearer token string
            
        Raises:
            RttApiError: If token exchange fails
        """
        session = await self._get_session()
        
        headers = {
            "Authorization": f"Bearer {self.api_auth_token}",
        }
        
        _LOGGER.debug(f"Attempting token exchange at {self.auth_url}")
        
        try:
            async with session.get(
                self.auth_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                _LOGGER.debug(f"Token exchange response status: {response.status}")
                
                if response.status == 401:
                    raise RttApiError("Invalid API authorization token")
                elif response.status >= 400:
                    error_text = await response.text()
                    _LOGGER.error(f"Token exchange failed with status {response.status}: {error_text}")
                    raise RttApiError(f"Token exchange failed with status {response.status}")
                
                data = await response.json()
                _LOGGER.debug(f"Token exchange response data: {data}")
                bearer_token = data.get("token")
                
                if not bearer_token:
                    raise RttApiError("No bearer token in response")
                
                # Parse expiry time from validUntil field
                valid_until = data.get("validUntil")
                if valid_until:
                    # validUntil is an ISO-8601 datetime string
                    expiry_dt = datetime.datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
                    self.bearer_token_expiry = expiry_dt.timestamp()
                    # Add 5 minute buffer
                    self.bearer_token_expiry -= (5 * 60)
                else:
                    # Fallback to 30 minutes from now
                    self.bearer_token_expiry = time.time() + (30 * 60) - (5 * 60)
                
                self.bearer_token = bearer_token
                
                _LOGGER.debug("Successfully exchanged API auth token for bearer token")
                return bearer_token
                
        except asyncio.TimeoutError:
            raise RttApiError("Token exchange timeout (10 seconds)")
        except aiohttp.ClientError as err:
            _LOGGER.error(f"Token exchange connection error: {err}")
            raise RttApiError(f"Token exchange connection error: {err}")
    
    def _is_token_expired(self) -> bool:
        """Check if bearer token is expired or will expire soon.
        
        Returns:
            True if token needs refresh, False otherwise
        """
        if self.bearer_token is None or self.bearer_token_expiry is None:
            return True
        
        # Refresh if we have less than 5 minutes remaining
        return time.time() >= self.bearer_token_expiry
    
    async def _ensure_valid_token(self) -> str:
        """Ensure we have a valid bearer token, refreshing if needed.
        
        Returns:
            Valid bearer token
            
        Raises:
            RttApiError: If token refresh fails
        """
        if self._is_token_expired():
            await self._exchange_token()
        
        return self.bearer_token
    
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
        
        # Ensure we have a valid bearer token
        token = await self._ensure_valid_token()
        
        # Bearer token authentication header
        headers = {
            "Authorization": f"Bearer {token}",
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
                    error_text = await response.text()
                    _LOGGER.error(f"API request failed: {response.status} - {error_text}")
                    raise RttApiError(f"API returned status {response.status}: {error_text}")
                
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
        from_datetime: Optional[str] = None,
        to_datetime: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get departures from a station.

        Args:
            crs: CRS code of origin station (e.g., 'LDS' for Leeds)
            destination_crs: Optional CRS to filter by destination
            time_offset_minutes: Minutes from now to start looking (deprecated, use from_datetime)
            time_window_minutes: Time window width (deprecated, use to_datetime)
            from_datetime: ISO-8601 datetime string for start of window (e.g., "2026-06-06T17:00:00Z")
            to_datetime: ISO-8601 datetime string for end of window (e.g., "2026-06-06T23:00:00Z")

        Returns:
            Dictionary with 'location' and 'services' keys
        """
        try:
            # Try Network Rail specific endpoint first (uses CRS codes)
            endpoint = "gb-nr/location"

            params = {"code": crs}

            if destination_crs:
                params["filterTo"] = destination_crs

            # Use explicit from/to datetimes if provided (preferred method)
            if from_datetime:
                params["from"] = from_datetime
            if to_datetime:
                params["to"] = to_datetime

            # Fallback to timeWindow if no explicit datetimes provided
            if not from_datetime and not to_datetime and time_window_minutes != 120:
                params["timeWindow"] = str(time_window_minutes)

            _LOGGER.debug(f"Fetching departures with params: {params}")
            data = await self._request("GET", endpoint, params)

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
            # Use Network Rail specific endpoint (uses CRS codes)
            endpoint = "gb-nr/location"

            params = {"code": crs}

            if origin_crs:
                params["filterFrom"] = origin_crs
            
            if time_window_minutes != 120:
                params["timeWindow"] = time_window_minutes
            
            data = await self._request("GET", endpoint, params)
            
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
            service_uid: Unique service identifier (e.g., "gb-nr:L01525:2025-10-26")
            service_date: Service date in format YYYY-MM-DD (not used if service_uid includes date)
            
        Returns:
            Dictionary with detailed service information including all stops
        """
        try:
            endpoint = "rtt/service"
            
            # If service_uid includes the full unique identity (namespace:identity:date), use that
            if ":" in service_uid:
                params = {"uniqueIdentity": service_uid}
            else:
                # Otherwise use identity and date separately
                params = {
                    "identity": service_uid,
                    "departureDate": service_date,
                }
            
            return await self._request("GET", endpoint, params)
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
