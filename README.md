# Realtime Trains API (Next Generation) - Home Assistant Integration

A Home Assistant integration for the **new Realtime Trains Next Generation API** with Bearer token authentication and ISO-8601 datetimes.

## ⚠️ Important Migration Info

The old RTT API (`api.rtt.io`) is being shut down on **September 30, 2026**. This integration uses the new API at `api.realtimetrains.co.uk`.

## Prerequisites

- Home Assistant 2024.1.0 or later
- Bearer token from https://api-portal.rtt.io/
- Internet connection

## Installation

### Method 1: HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right → "Custom repositories"
4. Add repository: https://github.com/yourusername/ha_realtime_trains_api_ng
5. Category: "Integration"
6. Click "Add"
7. Search for "Realtime Trains API (Next Generation)" and install
8. Restart Home Assistant

### Method 2: Manual Installation

**On Home Assistant with SSH:**
```bash
cd ~/.homeassistant/custom_components
git clone https://github.com/yourusername/ha_realtime_trains_api_ng.git
mv ha_realtime_trains_api_ng realtime_trains_api_ng
```

**Or manually:**
1. Download the integration files
2. Extract to: `~/.homeassistant/custom_components/realtime_trains_api_ng/`

### Step 2: Restart Home Assistant
Settings → System → Restart

### Step 3: Get Your API Token

1. Visit https://api-portal.rtt.io/
2. Sign up or log in
3. Request a **Bearer token** (not Basic Auth credentials)
4. Copy the token

### Step 4: Configure the Integration

**Via UI (Recommended):**
1. Settings → Devices & Services → Create Integration
2. Search for "Realtime Trains API (Next Generation)"
3. Enter your Bearer token
4. Configure origin/destination stations

**Or via YAML:**
```yaml
realtime_trains_api_ng:
  token: "your_bearer_token_here"
  queries:
    - origin: "LDS"
      destination: "KGX"
```

## Configuration

### Basic Configuration

```yaml
realtime_trains_api_ng:
  token: !secret rtt_token
  queries:
    - origin: "LDS"      # Leeds
      destination: "KGX" # King's Cross
```

### Advanced Configuration

```yaml
realtime_trains_api_ng:
  token: !secret rtt_token
  queries:
    # Route 1: Leeds to London
    - origin: "LDS"
      destination: "KGX"
      sensor_name: "Morning Commute"
      journey_data_for_next_x_trains: 5
      stops_of_interest:
        - "WAL"  # Walton
        - "VXH"  # Vauxhall
      time_offset:
        minutes: 20  # Station is 20 mins walk away
    
    # Route 2: Return journey
    - origin: "KGX"
      destination: "LDS"
      journey_data_for_next_x_trains: 3
```

### Configuration Options

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `token` | string | Yes | - | Bearer token from api-portal.rtt.io |
| `origin` | string | Yes (per query) | - | CRS code of departure station |
| `destination` | string | Yes (per query) | - | CRS code of arrival station |
| `sensor_name` | string | No | Auto | Custom name for the sensor |
| `journey_data_for_next_x_trains` | int | No | 0 | Fetch detailed info for X trains (1-5 recommended) |
| `stops_of_interest` | list | No | [] | CRS codes to track during journey |
| `time_offset.minutes` | int | No | 0 | Display trains from N minutes from now |

## Station CRS Codes

Common codes:
- **LDS** = Leeds
- **KGX** = King's Cross (London)
- **WAT** = Waterloo (London)
- **MAN** = Manchester Piccadilly
- **BHM** = Birmingham New Street
- **EDI** = Edinburgh
- **GLQ** = Glasgow Queen Street

Find more: https://www.realtimetrains.co.uk/about/developer/

## Sensor Output

Each query creates a sensor named:
- `sensor.next_train_from_{origin}_to_{destination}` (auto)
- Or your custom `sensor_name` if specified

### Sensor State
Integer: **Minutes until next train** (e.g., `23`)

### Sensor Attributes
```python
{
  "station": {
    "crs": "LDS",
    "name": "Leeds",
    "tiploc": "LEEDS"
  },
  "next_trains": [
    {
      "service_uid": "Q46478",
      "operator": "LNER",
      "origin": "London Kings Cross",
      "destination": "Leeds",
      "scheduled_departure": "2024-01-15T14:30:00+00:00",
      "estimated_departure": "2024-01-15T14:30:00+00:00",
      "platform": "5",
      "minutes": 23,
      "stops": 8,           # Total stops (if journey_data enabled)
      "journey_time_mins": 142,
      "scheduled_arrival": "2024-01-15T16:52:00+00:00",
      "estimated_arrival": "2024-01-15T16:52:00+00:00",
      "stops_of_interest": [
        {
          "stop_code": "WAL",
          "name": "Walton",
          "scheduled_arrival": "2024-01-15T14:45:00+00:00",
          "estimated_arrival": "2024-01-15T14:45:00+00:00"
        }
      ]
    },
    ...more trains...
  ],
  "rate_limit_info": {
    "X-RateLimit-Limit-Minute": 30,
    "X-RateLimit-Remaining-Minute": 28
  }
}
```

## Automations

### Alert 10 Minutes Before Train
```yaml
automation:
  - alias: "Train Reminder"
    trigger:
      - platform: numeric_state
        entity_id: sensor.next_train_from_lds_to_kgx
        below: 10
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "Your train leaves in {{ states('sensor.next_train_from_lds_to_kgx') }} minutes!"
```

### Display Next Train Operator
```yaml
template:
  - sensor:
      - name: "Next Train Operator"
        unique_id: next_train_operator
        state: >
          {% if state_attr('sensor.next_train_from_lds_to_kgx', 'next_trains') %}
            {{ state_attr('sensor.next_train_from_lds_to_kgx', 'next_trains')[0]['operator'] }}
          {% else %}
            N/A
          {% endif %}
```

## Troubleshooting

### "Invalid Token" Error
- Verify token is from https://api-portal.rtt.io/ (not old api.rtt.io)
- Check token hasn't expired
- Ensure it's a Bearer token, not Basic Auth credentials

### "Cannot Connect" Error
- Check internet connection
- Verify API is online at https://api-portal.rtt.io/
- Check Home Assistant logs: Settings → System → Logs

### No Trains Appearing
- Verify CRS codes are correct (check realtimetrains.co.uk)
- Ensure trains run between those stations at this time
- Check if `time_offset` is hiding available trains

### Rate Limited (429 Errors)
- Increase `scan_interval` to 120+ seconds
- Reduce number of queries
- Disable or reduce `journey_data_for_next_x_trains`

### Integration Won't Load
1. Check logs: Settings → System → Logs
2. Search for "realtime_trains_api_ng"
3. Restart Home Assistant
4. Verify all files are in correct location

## Rate Limits

RTT API enforces:
- **30 requests/minute**
- **750 requests/hour**
- **9000 requests/day**
- **30000 requests/week**

Default scan interval is 90 seconds. Don't set below 60 seconds.

## Secrets Configuration

In `secrets.yaml`:
```yaml
rtt_token: "your_bearer_token_here"
```

In `configuration.yaml`:
```yaml
realtime_trains_api_ng:
  token: !secret rtt_token
  queries:
    - origin: "LDS"
      destination: "KGX"
```

## File Structure

```
custom_components/realtime_trains_api_ng/
├── manifest.json      # Integration metadata
├── const.py          # Configuration constants
├── rtt_api.py        # API wrapper
├── __init__.py       # Main integration + coordinator
├── config_flow.py    # Setup UI
└── sensor.py         # Sensor platform
```

See `BUILD_GUIDE.md` for detailed architecture explanation.

## API Documentation

- **RTT API Portal**: https://api-portal.rtt.io/
- **RTT API Specification**: https://realtimetrains.github.io/api-specification/
- **RTT Website**: https://www.realtimetrains.co.uk/

## License

Apache License 2.0

## Support

- Report issues on GitHub
- Check RTT API status at https://api-portal.rtt.io/
- See `BUILD_GUIDE.md` for architecture details

## Migrating from Old API

If you're upgrading from the old `api.rtt.io`:

1. Get new token from https://api-portal.rtt.io/
2. Uninstall old integration
3. Install this integration
4. Change config:
   - Replace `username`/`password` with `token`
   - That's it! Rest of config is the same

**Deadline**: Old API shuts down September 30, 2026.
