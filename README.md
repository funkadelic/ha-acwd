# ACWD Water Usage Integration for Home Assistant

A **HACS-compatible custom integration** that brings your ACWD (Alameda County Water District) water usage data directly into Home Assistant, with full support for the **Energy Dashboard**.

## Quick Start

1. **Install via HACS** (see [INSTALLATION.md](INSTALLATION.md) for detailed instructions)
2. **Add Integration** in Settings → Devices & Services
3. **Enter your ACWD portal credentials**
4. **Add to Energy Dashboard** - Use the "Current Cycle Usage" sensor

## Available Sensors

| Sensor | Description | Unit | Energy Dashboard |
|--------|-------------|------|------------------|
| Current Cycle Usage | Water used in current billing cycle | Gallons | ✅ Compatible |
| Current Cycle Projected | Projected total for current cycle | Gallons | ❌ No |
| Last Billing Cycle | Previous billing cycle usage | Gallons | ❌ No |
| Average Usage | Historical average per cycle | Gallons | ❌ No |
| Highest Usage Ever | Peak usage record | Gallons | ❌ No |

The integration updates every **6 hours** and automatically imports **hourly water usage data** for historical days, providing granular breakdowns in the Energy Dashboard.

## Installation

See [INSTALLATION.md](INSTALLATION.md) for complete setup instructions including:

- HACS installation (recommended)
- Manual installation
- Energy Dashboard configuration
- Hourly data import (automatic & manual)
- Troubleshooting

## Key Features

- **Automatic Initial Import**: On first installation, automatically imports the last 7 days of hourly data
- **Continuous Hourly Tracking**: Automatically imports yesterday's hourly usage every 6 hours
- **Manual Import Services**: Import historical data for any date range via Home Assistant services
- **Energy Dashboard Integration**: Full compatibility with Home Assistant's Energy Dashboard
- **Long-term Statistics**: Data stored in HA's statistics database for historical analysis
- **15-Minute Interval Support**: Optional 15-minute data available via manual service (note: Energy Dashboard displays hourly granularity; 15-min data useful for custom cards, automations, and advanced analysis)

## Data Availability

⚠️ **The ACWD portal has a 24-hour data delay**. This means:

- Today's usage data is **NOT** available
- You can only retrieve data from yesterday and earlier
- This limitation applies to the ACWD portal itself

## Contributing

Found a bug or want to add a feature? Pull requests welcome!

## Disclaimer

This is an unofficial tool and is not affiliated with or endorsed by ACWD. Use at your own risk.
