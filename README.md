# ACWD Water Usage Integration for Home Assistant

A **HACS-compatible custom integration** that brings your ACWD (Alameda County Water District) water usage data directly into Home Assistant, with full support for the **Home Assistant Energy Dashboard**. ACWD services the cities of Fremont, Newark, and Union City, CA.

## Background

After ACWD deployed [AMI (Advanced Metering Infrastructure) smart meters](https://en.wikipedia.org/wiki/Smart_meter#Advanced_metering_infrastructure), third-party solutions like Flume Water lost direct access to real-time water usage data. This integration bridges that gap by importing hourly water usage directly from the ACWD portal into Home Assistant.

**What you get:**

- ✅ Hourly water usage data in the Energy Dashboard
- ✅ Near real-time updates (hourly polling with 3-4 hour portal delay)
- ✅ Historical statistics and long-term tracking
- ⚠️ Not real-time like Flume (data reflects ACWD portal availability)

![Energy Dashboard Water Consumption](images/ha_energy_dashboard_water_consumption_graph.png)

## Quick Start

1. **Install via HACS** (see [INSTALLATION.md](INSTALLATION.md) for detailed instructions)
2. **Add Integration** in Settings → Devices & Services
3. **Enter your ACWD portal credentials** (stored securely in Home Assistant's encrypted credential storage)
4. **Add to Energy Dashboard** - Use the "ACWD Water Hourly Usage - Meter xxxxxxxxx" statistic

## Available Entities

| Entity | Description | Unit |
|--------|-------------|------|
| Current Cycle Usage | Water used in current billing cycle | Gallons |
| Current Cycle Projected | Projected total for current billing cycle | Gallons |
| Last Billing Cycle | Previous billing cycle usage | Gallons |
| Average Usage | Historical average per billing cycle | Gallons |
| Highest Usage Ever | Peak usage record | Gallons |

The integration updates **every hour** and automatically imports **hourly water usage data**, providing water usage breakdown in the Energy Dashboard.

## Installation

See [INSTALLATION.md](INSTALLATION.md) for complete setup instructions including:

- HACS installation (recommended)
- Manual installation
- Energy Dashboard configuration
- Hourly data import (automatic & manual)
- Troubleshooting

## Key Features

- **Near Real-Time Updates**: Hourly polling automatically imports today's partial usage data (adapts to ACWD's variable reporting delay)
- **Automatic Initial Import**: On first installation, imports yesterday's complete hourly data for immediate feedback
- **Manual Import Services**: Import historical data for any date range via Home Assistant services
- **Energy Dashboard Integration**: Full compatibility with Home Assistant's Energy Dashboard
- **Long-term Statistics**: Data stored in HA's statistics database for historical analysis
- **15-Minute Interval Support**: Optional 15-minute data available via manual service (note: Energy Dashboard displays hourly granularity; 15-min data useful for custom cards, automations, and advanced analysis)
- **Smart Duplicate Handling**: Statistics system automatically handles re-imports by replacing existing timestamps

## Data Availability

⚠️ **The ACWD portal has a variable reporting delay** (typically 3-4 hours). This means:

- Today's usage data **is available**, but with a delay
- The integration fetches whatever ACWD has available every hour
- Example: At 2 PM, you'll typically see data up to ~11 AM
- This delay applies to the ACWD portal itself, not the integration. The integration can only import data into Home Assistant if it exists on the ACWD side

## Contributing

Found a bug or want to add a feature? Pull requests welcome!

## Disclaimer

This is an unofficial tool and is not affiliated with or endorsed by ACWD. Use at your own risk.
