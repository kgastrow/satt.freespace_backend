# Geolocation Setup Guide

This guide explains how to enable IP-based geolocation for session tracking, which displays user login locations in the session management interface.

## Overview

The application uses MaxMind's GeoLite2 database to resolve IP addresses to geographic locations. When enabled, each user session displays the city and country from which the user logged in.

## Prerequisites

- Free MaxMind account
- Access to the backend server filesystem

## Setup Instructions

### 1. Create a MaxMind Account

1. Go to [MaxMind GeoLite2 Sign Up](https://www.maxmind.com/en/geolite2/signup)
2. Complete the registration form
3. Verify your email address

### 2. Download the Database

1. Log in to your MaxMind account
2. Navigate to **Download Files**
3. Download **GeoLite2 City** in MMDB format (`GeoLite2-City.mmdb`)

### 3. Install the Database

```bash
# Create the data directory
mkdir -p app/backend/data/

# Copy the database file
cp ~/Downloads/GeoLite2-City.mmdb app/backend/data/
```

### 4. Verify Configuration

The default configuration in `app/backend/src/core/config.py` is:

```python
GEOIP_DATABASE_PATH: str = "./data/GeoLite2-City.mmdb"
GEOIP_ENABLED: bool = True
```

No changes are needed unless you want a custom path.

### 5. Restart the Backend

```bash
cd app/backend
make dev
```

On startup, you should see in the logs:
```
GeoIP database loaded from ./data/GeoLite2-City.mmdb
```

## Configuration Options

### Using config.json

```json
{
  "geoip": {
    "enabled": true,
    "database_path": "./data/GeoLite2-City.mmdb"
  }
}
```

### Using Environment Variables

```bash
export GEOIP_ENABLED=true
export GEOIP_DATABASE_PATH="/path/to/GeoLite2-City.mmdb"
```

### Disabling Geolocation

Set `GEOIP_ENABLED=false` to disable geolocation lookups entirely.

## How It Works

1. User logs in
2. Backend captures the client IP address
3. IP is looked up in the GeoLite2 database
4. City, country, and country code are stored with the session
5. Frontend displays location with country flag in session list

## Privacy Considerations

- IP addresses are masked before storage (e.g., `192.168.1.100` → `192.168.x.x`)
- Location data is only captured at login time
- Private/local IPs (127.*, 10.*, 192.168.*, etc.) are skipped

## Troubleshooting

### Sessions Show "Unknown location"

**Cause:** Database file missing or lookup failed.

**Solution:**
1. Verify the database file exists at the configured path
2. Check backend logs for warnings about missing database
3. Ensure `GEOIP_ENABLED` is `true`

### Existing Sessions Still Show "Unknown location"

**Expected behavior.** Location is captured at login time. Existing sessions created before the database was installed will not have location data. Users must log in again to capture their location.

### Local Development Shows "Unknown location"

**Expected behavior.** Local/private IP addresses (localhost, 127.0.0.1, etc.) cannot be geolocated. Test with a real public IP or in a deployed environment.

## Keeping the Database Updated

MaxMind updates the GeoLite2 database weekly. For accuracy, consider:

1. **Manual updates:** Download periodically from MaxMind
2. **Automated updates:** Use MaxMind's `geoipupdate` tool

### Using geoipupdate

1. Install: `apt install geoipupdate` or download from MaxMind
2. Configure `/etc/GeoIP.conf` with your license key
3. Run: `geoipupdate`
4. Set up a cron job for weekly updates

## License

GeoLite2 databases are free under the [GeoLite2 End User License Agreement](https://www.maxmind.com/en/geolite2/eula). Attribution is required for public-facing applications.
