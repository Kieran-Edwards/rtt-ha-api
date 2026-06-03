# Building a Home Assistant Integration from Scratch

## What We Just Built

A complete Home Assistant integration for the **Realtime Trains Next Generation API**. Here's the structure:

```
custom_components/
└── realtime_trains_api_ng/
    ├── manifest.json      ← Integration metadata
    ├── const.py          ← Configuration constants
    ├── rtt_api.py        ← API wrapper (talks to RTT)
    ├── __init__.py       ← Main integration logic & coordinator
    ├── config_flow.py    ← UI for setup
    └── sensor.py         ← Sensor entities
```

## File-by-File Breakdown

### 1. **manifest.json**
This tells Home Assistant:
- **What** this integration is (Realtime Trains API)
- **Where** to find documentation
- **What version** it is
- **Minimum HA version** required

```json
{
  "domain": "realtime_trains_api_ng",
  "name": "Realtime Trains API (Next Generation)",
  "config_flow": true,
  "version": "1.0.0"
}
```

### 2. **const.py** - The Configuration Dictionary
Central place for all constants:
- Configuration keys that appear in YAML
- Default values
- API endpoints and rate limits

**Why separate?** Makes it easy to change values and ensures consistency.

```python
CONF_TOKEN = "token"           # Config key in YAML
DEFAULT_SCAN_INTERVAL = 90     # Seconds between API calls
RTT_API_BASE_URL = "https://api.realtimetrains.co.uk"
```

### 3. **rtt_api.py** - The API Client
This is the **core API wrapper** that:
- Handles HTTP requests with Bearer token auth
- Parses RTT responses
- Manages rate limiting
- Catches and reports errors

**Main methods:**
- `search_departures(crs, destination_crs)` - Get trains leaving a station
- `search_arrivals(crs, origin_crs)` - Get trains arriving at a station  
- `fetch_service_details(service_uid, date)` - Get full train journey details

```python
api = RttApi(token="your_bearer_token")
departures = await api.search_departures(crs="LDS", destination_crs="KGX")
```

### 4. **__init__.py** - The Integration Coordinator
This is the **main integration file** that:
- Creates the API client
- Creates a `DataUpdateCoordinator` for each query
- Fetches data periodically
- Passes data to sensors

**Key class: `RttDataUpdateCoordinator`**
- Runs every 90 seconds by default
- Fetches departures from origin station
- Optionally fetches detailed journey data
- Handles errors gracefully

```python
# Setup flow:
async_setup_entry() → creates API → creates coordinators → 
  first refresh → forward to platforms (sensor)
```

### 5. **config_flow.py** - The Setup UI
Handles the configuration flow in Home Assistant:
1. **Step 1 (User)**: User enters Bearer token
2. Token is validated by calling `api.get_api_info()`
3. **Step 2 (Queries)**: User configures origin/destination stations

This creates a `ConfigEntry` with:
```python
{
    "token": "rtt_abc123...",
    "queries": [
        {
            "origin": "LDS",
            "destination": "KGX"
        }
    ]
}
```

### 6. **sensor.py** - The Sensor Entity
Creates the actual **sensor** that appears in Home Assistant:

**Main sensor class: `RttTrainSensor`**
- **State**: Minutes until next train (integer)
- **Attributes**: Detailed train information

Example state:
```
sensor.next_train_from_lds_to_kgx = "23"
```

Example attributes:
```python
{
    "station": {
        "crs": "LDS",
        "name": "Leeds"
    },
    "next_trains": [
        {
            "operator": "LNER",
            "platform": "5",
            "scheduled_departure": "2024-01-15T14:30:00+00:00",
            "minutes": 23,
            "stops": 8,
            "journey_time_mins": 142
        },
        ...
    ]
}
```

## Data Flow

```
User Configuration
        ↓
config_flow.py (get token + queries)
        ↓
__init__.py (async_setup_entry)
        ↓
RttApi (API client created)
        ↓
RttDataUpdateCoordinator (created per query)
        ↓
coordinator.async_config_entry_first_refresh()
        ↓
_async_update_data() ← calls api.search_departures()
        ↓
Returns dict with "departures", "station"
        ↓
sensor.py (receives data)
        ↓
RttTrainSensor.native_value (calculate minutes)
        ↓
RttTrainSensor.extra_state_attributes (full details)
        ↓
Home Assistant Frontend (shows sensor)
```

## Key Concepts

### 1. **Bearer Token Authentication**
Unlike the old API which used HTTP Basic Auth (username:password), the new API uses:
```python
headers = {
    "Authorization": f"Bearer {self.token}",
    "Accept": "application/json"
}
```

### 2. **Async/Await**
All API calls are async for non-blocking I/O:
```python
async def search_departures(...):
    async with session.request(...) as response:
        return await response.json()
```

### 3. **Data Coordinator Pattern**
Home Assistant's recommended pattern for periodic data fetching:
- Fetches data in background
- Handles retries automatically
- Notifies entities when data updates
- Prevents rate limiting from multiple entities

### 4. **ISO-8601 Datetimes**
The new API returns times in ISO-8601 format:
```
2024-01-15T14:30:00+00:00  ← Includes timezone info!
```

Parse with:
```python
dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
```

### 5. **Error Handling**
Errors at each level:
- **API Level**: `RttApiError` for API problems
- **Coordinator Level**: `UpdateFailed` for retries
- **Sensor Level**: Returns `None` if data unavailable

## How Home Assistant Discovers This

1. HA scans `custom_components/` directory
2. Finds `manifest.json`
3. Loads the integration
4. Shows in Settings → Devices & Services
5. User clicks "Create Integration"
6. Runs config_flow steps
7. Creates ConfigEntry
8. Calls `async_setup_entry()`
9. Entities appear in Home Assistant

## Installation Instructions for Users

### Copy to Home Assistant:
```bash
# From your computer
scp -r custom_components/realtime_trains_api_ng \
  user@homeassistant.local:/home/homeassistant/.homeassistant/custom_components/

# Or via HACS custom repository
```

### Restart Home Assistant
Settings → System → Restart

### Add Integration
Settings → Devices & Services → Create Integration → Search for "Realtime Trains API"

## Testing the Integration

### Test Token Validation
```python
from .rtt_api import RttApi

api = RttApi(token="test_token")
info = await api.get_api_info()
# If this returns data, token is valid
```

### Test API Call
```python
departures = await api.search_departures(
    crs="LDS",  # Leeds
    destination_crs="KGX"  # King's Cross
)
print(departures)  # Should print departures
```

### Test Coordinator
Once installed, check:
1. Home Assistant Settings → Devices & Services
2. Find "Realtime Trains API" integration
3. Click on it
4. Should show device with sensor entities

## Extending the Integration

### Add Arrivals Support
In `sensor.py`, create an `RttArrivalsSensor`:
```python
class RttArrivalsSensor(CoordinatorEntity, SensorEntity):
    async def _async_update_data(self):
        return await self.api.search_arrivals(...)
```

### Add Service Calls
In `__init__.py`:
```python
async def async_service_handler(call):
    # Do something when service is called
    pass

hass.services.async_register(DOMAIN, "get_service_info", async_service_handler)
```

### Add More Attributes
In `sensor.py._parse_service()`, add more fields from the API response.

## Common Issues & Solutions

### "Invalid Token"
→ Token must be from https://api-portal.rtt.io/ (not old api.rtt.io)

### "Cannot Connect"
→ Check internet connection, token expiry, API status

### No Trains Found
→ Verify CRS codes are correct, trains run between those stations

### Integration Won't Load
→ Check Home Assistant logs for errors:
   Settings → System → Logs (look for "realtime_trains_api_ng")

## Architecture Decisions Made

1. **Separate API wrapper** - Easy to test, reuse, maintain
2. **Constants file** - Single source of truth for config
3. **Coordinator pattern** - Standard HA pattern for periodic updates
4. **Async throughout** - Non-blocking I/O
5. **Config flow** - User-friendly setup (not just YAML)
6. **Sensor platform** - Standard way to display data
7. **Bearer tokens** - Secure, modern authentication

## Next Steps

1. **Test in your Home Assistant instance**
2. **Add to GitHub** - Create a repo for users
3. **Submit to HACS** - Make it discoverable
4. **Add automations** - Show users example automations
5. **Document response structure** - Help users create templates

---

**Congratulations!** You've built a complete, production-ready Home Assistant integration from scratch! 🎉
