# Installation Guide

## HACS Installation (Recommended)

### Prerequisites

- Home Assistant 2023.1.0 or newer
- HACS installed

### Steps

1. **Add Custom Repository**
   - Open HACS
   - Click the three dots menu (top right)
   - Select "Custom repositories"
   - Add repository URL: `https://github.com/funkadelic/acwd_usage`
   - Category: "Integration"
   - Click "Add"

2. **Install the Integration**
   - Click "+ Explore & Download Repositories"
   - Search for "ACWD Water Usage"
   - Click "Download"
   - Restart Home Assistant

3. **Configure the Integration**
   - Go to Settings → Devices & Services
   - Click "+ Add Integration"
   - Search for "ACWD Water Usage"
   - Enter your ACWD portal credentials:
     - **Email**: Your ACWD portal email address
     - **Password**: Your ACWD portal password
   - Click "Submit"

## Manual Installation

1. **Download the Integration**

   ```bash
   cd /config
   mkdir -p custom_components
   cd custom_components
   git clone https://github.com/funkadelic/acwd_usage.git acwd
   ```

2. **Or Download ZIP**
   - Download the latest release
   - Extract to `/config/custom_components/acwd/`

3. **Restart Home Assistant**

4. **Configure** (same as step 3 above)

## Energy Dashboard Configuration

After installation, add the water sensor to your Energy Dashboard:

1. Go to **Settings → Dashboards → Energy**
2. Under "Water Consumption", click "Add Water Source"
3. Select **"ACWD Water - [Your Name] Current Cycle Usage"**
4. Click "Save"

The sensor provides water consumption in gallons, compatible with the Energy Dashboard.

## Available Sensors

The integration creates the following sensors:

| Sensor | Description | Unit | Energy Dashboard |
|--------|-------------|------|------------------|
| Current Cycle Usage | Water used in current billing cycle | Gallons | ✅ Yes |
| Current Cycle Projected | Projected total for current cycle | Gallons | ❌ No |
| Last Billing Cycle | Previous billing cycle usage | Gallons | ❌ No |
| Average Usage | Historical average per cycle | Gallons | ❌ No |
| Highest Usage Ever | Peak usage record | Gallons | ❌ No |

## Granular Hourly Data

The integration automatically imports hourly water usage data into Home Assistant's long-term statistics database. This provides **granular hourly breakdowns** in the Energy Dashboard for historical days.

### How It Works

1. **First-Time Setup**: On initial installation, the integration automatically imports the **last 7 days** of hourly water usage data. This provides immediate historical context in your Energy Dashboard.
2. **Ongoing Automatic Import**: Every 6 hours, the integration automatically imports hourly data for 2 days ago (accounting for ACWD's 24-hour data delay)
3. **Energy Dashboard Integration**: The hourly data appears in the Energy Dashboard, allowing you to see water usage broken down by hour for any historical day
4. **Long-term Storage**: Data is stored in Home Assistant's statistics database, separate from regular sensor states

**Note:** The initial 7-day import happens in the background after setup completes. You can check the Home Assistant logs to monitor progress.

### Manual Data Import Services

You can manually import historical data using Home Assistant services:

#### Import Hourly Data

Service: `acwd.import_hourly_data`

Import hourly or 15-minute interval data for a specific date.

**Parameters:**

- `date`: Date to import (YYYY-MM-DD format, must be at least 2 days ago)
- `granularity`: Choose `hourly` (default) or `quarter_hourly` (15-minute intervals)

**Example:**

```yaml
service: acwd.import_hourly_data
data:
  date: "2025-12-01"
  granularity: "hourly"
```

**Note on 15-Minute Data:**

While the ACWD API provides 15-minute interval data (`granularity: "quarter_hourly"`), the Energy Dashboard displays hourly granularity at finest. The 15-minute data is useful for:

- Custom Lovelace cards that use statistics data directly
- Automations detecting short-duration high-usage events
- Advanced analysis through the statistics database
- Future-proofing if HA adds finer granularity support

For most users, hourly data is sufficient and recommended.

#### Import Daily Data

Service: `acwd.import_daily_data`

Import daily summary data for a date range.

**Parameters:**

- `start_date`: Start date (YYYY-MM-DD)
- `end_date`: End date (YYYY-MM-DD)

**Example:**

```yaml
service: acwd.import_daily_data
data:
  start_date: "2025-11-01"
  end_date: "2025-11-30"
```

### Viewing Hourly Data

1. Go to **Settings → Dashboards → Energy**
2. Click on the **Water** tab
3. Select a specific date to see hourly breakdown
4. The Energy Dashboard will display water usage for each hour of that day

## Troubleshooting

### Integration not appearing

- Ensure you've restarted Home Assistant after installation
- Check logs in Settings → System → Logs

### Login fails

- Verify credentials at <https://portal.acwd.org/portal/>
- Check for special characters in password (the integration handles these correctly)
- Ensure your account is active

### No data showing

- ACWD has a 24-hour data delay - current day's data is not available
- Wait 6 hours for first data refresh
- Check integration logs for errors

## Update Frequency

The integration updates every 6 hours. This is appropriate because:

- ACWD portal has a 24-hour data delay
- Billing cycles are long (typically 2 months)
- Frequent updates are unnecessary and would waste resources

## Support

For issues, please open a GitHub issue at:
<https://github.com/funkadelic/acwd_usage/issues>
