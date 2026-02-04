# Installation Guide

## Quick Install (Easiest Method)

**The fastest way to install is using the "My Home Assistant" link:**

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=funkadelic&repository=ha-acwd&category=integration)

Click the badge above, and it will:

1. Open HACS directly in your Home Assistant instance
2. Navigate to the ACWD Water Usage integration
3. Allow you to download and install with one click

Then restart Home Assistant and proceed to [Configuration](#configuration).

## HACS Installation (Alternative Method)

### Prerequisites

- Home Assistant 2024.2.0 or newer
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

3. **Proceed to Configuration** (see below)

## Configuration

After installing via either method above:

1. Go to **Settings → Devices & Services**
2. Click **"+ Add Integration"**
3. Search for **"ACWD Water Usage"**
4. Enter your ACWD portal credentials (stored securely in Home Assistant's encrypted credential storage):
   - **Email**: Your ACWD portal email address
   - **Password**: Your ACWD portal password
5. Click **"Submit"**

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

The integration automatically imports hourly water usage data into Home Assistant's long-term statistics database. This provides **hourly breakdowns** in the Energy Dashboard based on ACWD's batch update schedule.

### How It Works

1. **First-Time Setup**: On initial installation, the integration automatically imports **yesterday's complete hourly data**. This provides immediate feedback that the integration is working.
2. **Hourly Polling**: The integration checks for new data every hour and imports whatever ACWD has released
3. **Morning Completion**: Between midnight and noon, the integration re-imports **yesterday's data** to capture the final hours (9 PM - midnight) that become available around 8 AM
4. **Energy Dashboard Integration**: The hourly data appears in the Energy Dashboard, allowing you to see water usage broken down by hour
5. **Long-term Storage**: Data is stored in Home Assistant's statistics database, separate from regular sensor states
6. **Smart Duplicate Handling**: Re-importing the same hour automatically replaces the old value - no duplicates created
7. **Cumulative Sum Tracking**: The integration correctly maintains cumulative water usage totals across day boundaries, ensuring accurate historical tracking

### ACWD Data Update Schedule

ACWD releases water usage data in **4 batches per day** (times are consistent within 1-hour windows):

- **7:00-8:00 AM** - Yesterday's final 3 hours (9 PM - midnight) + Today's first 8 hours (midnight - 7 AM)
- **12:00-1:00 PM** - Today's next 5 hours (8 AM - 12 PM)
- **5:00-6:00 PM** - Today's next 5 hours (1 PM - 5 PM)
- **8:00-9:00 PM** - Today's next 3 hours (6 PM - 8 PM)

**Key points:**

- Each day's data arrives in 4 batches totaling 21 hours (midnight - 8 PM)
- The final 3 hours (9 PM - midnight) appear the next morning at 7-8 AM
- Yesterday's complete 24-hour usage typically available by 8 AM daily (based on ACWD's schedule)

**Example:** At 3 PM Tuesday, you'll see Monday's complete 24 hours + Tuesday's first 13 hours (midnight - noon). Tuesday's 9 PM - midnight won't appear until Wednesday morning at 7-8 AM.

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

- ACWD releases data in batches 4 times per day (see schedule above)
- Data for current time may not be available yet depending on batch schedule
- Check integration logs for "Latest available data" messages
- Wait up to 1 hour for next automatic import
- Check integration logs for errors

## Update Frequency

The integration checks for new data **every hour**. This provides:

- Automatic imports whenever ACWD releases new batches
- Yesterday's complete data typically captured by 8 AM daily
- Today's data imported as ACWD releases it throughout the day
- Energy Dashboard shows water usage based on ACWD's batch schedule

## Support

For issues, please open a GitHub issue at:
<https://github.com/funkadelic/ha-acwd/issues>
