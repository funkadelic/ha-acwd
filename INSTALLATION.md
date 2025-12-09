# Installation Guide

## HACS Installation (Recommended)

### Prerequisites

- Home Assistant 2023.1.0 or newer (tested through 2025.x)
- HACS installed

### Steps

1. **Add Custom Repository**
   - Open HACS
   - Click the three dots menu (top right)
   - Select "Custom repositories"
   - Add repository URL: `https://github.com/funkadelic/ha-acwd`
   - Category: "Integration"
   - Click "Add"

2. **Install the Integration**
   - From the HACS search bar, search for "ACWD Water Usage"
   - Click "Download" from either the three dots menu (top right) or the Download button at the bottom right
   - Restart Home Assistant

3. **Configure the Integration**
   - Go to Settings → Devices & Services
   - Click "+ Add Integration"
   - Search for "ACWD Water Usage"
   - Enter your ACWD portal credentials (stored securely in Home Assistant's encrypted credential storage):
     - **Email**: Your ACWD portal email address
     - **Password**: Your ACWD portal password
   - Click "Submit"

## Manual Installation

1. **Download the Integration**

   ```bash
   cd /config
   mkdir -p custom_components
   cd custom_components
   git clone https://github.com/funkadelic/ha-acwd.git acwd
   ```

2. **Or Download ZIP**
   - Download the latest release
   - Extract to `/config/custom_components/acwd/`

3. **Restart Home Assistant**

4. **Configure** (same as step 3 above)

## Energy Dashboard Configuration

After installation, add the hourly water usage statistic to your Energy Dashboard:

1. Go to **Settings → Dashboards → Energy**
2. Under "Water Consumption", click "Add Water Source"
3. Select **"ACWD Water Hourly Usage - Meter XXXXXXXXX"** (where XXXXXXXXX is your actual AMI meter number)
4. Click "Save"

## Available Entities

The integration creates the following entities:

| Entity | Description | Unit |
|--------|-------------|------|
| Current Cycle Usage | Water used in current billing cycle | Gallons |
| Current Cycle Projected | Projected total for current billing cycle | Gallons |
| Last Billing Cycle | Previous billing cycle usage | Gallons |
| Average Usage | Historical average per billing cycle | Gallons |
| Highest Usage Ever | Peak usage record | Gallons |

## Granular Hourly Data

The integration automatically imports hourly water usage data into Home Assistant's long-term statistics database. This provides **near real-time hourly breakdowns** in the Energy Dashboard.

### How It Works

1. **First-Time Setup**: On initial installation, the integration automatically imports **yesterday's complete hourly data**. This provides immediate feedback that the integration is working.
2. **Ongoing Automatic Import**: Every hour, the integration automatically imports **today's partial hourly data** (whatever ACWD has available, typically with a 3-4 hour delay)
3. **Energy Dashboard Integration**: The hourly data appears in the Energy Dashboard, allowing you to see water usage broken down by hour
4. **Long-term Storage**: Data is stored in Home Assistant's statistics database, separate from regular sensor states
5. **Smart Duplicate Handling**: Re-importing the same hour automatically replaces the old value - no duplicates created
6. **Cumulative Sum Tracking**: The integration correctly maintains cumulative water usage totals across day boundaries, ensuring accurate historical tracking

**Example:** At 2 PM, you'll typically see today's data up to ~11 AM. The integration fetches updates every hour as more data becomes available.

### Manual Data Import Services

You can manually import historical data using Home Assistant services:

#### Import Hourly Data

Service: `acwd.import_hourly_data`

Import hourly or 15-minute interval data for a specific date.

**Parameters:**

- `date`: Date to import (YYYY-MM-DD format)
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
- Ensure your account is active
- After several failed login attempts, the ACWD portal will temporarily lock your account. You'll need to wait a few hours before trying to log in again

### No data showing

- ACWD has a variable reporting delay (typically 3-4 hours)
- Today's data is available, but with a delay
- Check integration logs for "Latest available data" messages
- Wait up to 1 hour for next automatic import
- Check integration logs for errors

## Update Frequency

The integration updates **every hour**. This provides:

- Near real-time water usage updates
- Today's partial data imported automatically
- Adapts to ACWD's variable reporting delay
- Energy Dashboard shows current day usage with minimal lag

## Support

For issues, please open a GitHub issue at:
<https://github.com/funkadelic/ha-acwd/issues>
