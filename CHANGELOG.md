# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.18] - 2025-12-11

### Changed

- Reduced manual import date constraint from 2 days to 1 day to align with ACWD's reporting delay
- Users can now manually re-import yesterday's data to fix incomplete imports (e.g., on Dec 12, can import Dec 11)

## [1.0.17] - 2025-12-11

### Changed

- Extended yesterday's data import window from 12-6 AM to 12 AM-12 PM (noon)
- Provides 12 hourly attempts instead of 6 to catch yesterday's final hours (9-11 PM) due to ACWD's reporting delay which can span 6+ hours
- Reduces likelihood of missing last few hours of yesterday's usage data

## [1.0.16] - 2025-12-10

### Fixed

- Fixed negative water usage values caused by incorrect timezone handling in baseline calculation
- Baseline now properly uses local timezone midnight (e.g., Dec 10 00:00 PST = Dec 10 08:00 UTC) to correctly identify yesterday's final hour

## [1.0.15] - 2025-12-09

### Fixed

- Fixed missing last few hours of yesterday's data by automatically re-importing yesterday's complete data during early morning hours (midnight - 6 AM)
- This addresses the edge case where yesterday's final hours (typically 9 PM - 11 PM) only become available after midnight due to ACWD's 3-4 hour reporting delay

## [1.0.14] - 2025-12-09

### Fixed

- Fixed type comparison error when timestamp is returned as float instead of datetime object

## [1.0.13] - 2025-12-09

### Fixed

- Fixed negative cumulative values at midnight by ensuring baseline starts from previous day's final sum
- Added validation test to verify cumulative sum calculations across day boundaries

## [1.0.12] - 2025-12-09

### Fixed

- Fixed statistics import database error by removing `mean_type=None` parameter (NOT NULL constraint)

## [1.0.11] - 2025-12-08

### Fixed

- Fixed statistics import error
- Fixed initial import error

## [1.0.10] - 2025-12-07

### Added

- One-time initial import of yesterday's data on first setup

### Changed

- Changed automatic import to fetch today's partial data every hour instead of yesterday's complete data once per day

## [1.0.9] - 2025-12-07

### Changed

- **Reduced update interval from 6 hours to 1 hour for more frequent data checks**
- **Changed automatic import to fetch yesterday's data (1 day ago) instead of 2 days ago**
  - Allows for faster data availability in Home Assistant
  - Integration will now attempt to import yesterday's data and log when data becomes available
- **Added logging to show the last hourly window with non-zero usage**
  - Helps identify actual ACWD data reporting delay
  - Logged as: "Last hour with data for YYYY-MM-DD: HH:MM AM/PM"

## [1.0.8] - 2025-12-07

### Removed

- **Removed automatic initial 7-day history import on first setup**
  - Eliminates complexity and prevents duplicate import issues
  - Users can still import historical data using the `acwd.import_usage_data` service
  - Automatic daily import continues to work normally (imports yesterday's data each day)
  - Simplifies codebase and makes integration more reliable

### Fixed

- Added `mean_type=None` to all StatisticMetaData to comply with Home Assistant 2026.11 requirements

## [1.0.7] - 2025-12-07

### Changed

- **Statistics ID now uses meter number instead of internal account number**
  - Provides clearer identification of which meter the statistics belong to
  - **Note**: This creates a new statistic. Old statistics with the previous ID will remain but won't receive new data.

## [1.0.6] - 2025-12-07

### Fixed

- **CRITICAL**: Fixed sensor values being inflated by 748x (showing millions of gallons instead of thousands)
  - Billing API returns values already in gallons, not HCF
  - Removed incorrect HCF-to-gallons conversion from all billing cycle sensors
  - Affected sensors: Current Cycle Usage, Current Cycle Projected, Last Billing Cycle, Average Usage, Highest Usage Ever
  - Example: Sensor now correctly shows ~8,873 gallons instead of 6,637,281 gallons

## [1.0.5] - 2025-12-07

### Fixed

- Added missing `recorder` dependency to manifest.json (required for statistics import functionality)
- Fixed hourly timestamp parsing to correctly parse "12:00 AM" format from API (was showing all hours as 00:00)

### Changed

- Updated repository URLs to correct location (funkadelic/ha-acwd)
- Added hassfest GitHub workflow for automated validation

## [1.0.4] - 2025-12-06

### Fixed

- Fixed statistics import inflating water usage by 748x due to incorrect HCF-to-gallons conversion
- Fixed Energy Dashboard showing misleading billing cycle totals instead of daily consumption

### Changed

- Removed state_class from Current Cycle Usage sensor to prevent it from appearing in Energy Dashboard (use imported hourly statistics instead)
- Statistics import now correctly uses raw gallon values from API without conversion

## [1.0.3] - 2025-12-06

### Fixed

- Fixed hourly usage data not being retrieved from ACWD portal API
- Fixed API request format to match browser behavior (Type='G' for graph mode, lowercase csrftoken header)
- Fixed date format for API requests (changed from MM/DD/YYYY to "Month D, YYYY")
- Implemented automatic AMI (smart) water meter discovery via BindMultiMeter API endpoint
- Added proper meter selection to prioritize AMI-enabled meters with hourly data capability

### Changed

- Updated API client to automatically detect and use AMI water meters for hourly usage data
- Improved CSRF token handling with fresh token fetched from usage page before each request

## [1.0.2] - 2025-12-05

### Added

- Added test_login.py script for local testing with credentials via environment variables, CLI args, or interactive prompt
- Added TESTING.md with comprehensive testing documentation
- Added .github/workflows/release.yml for automated releases

### Fixed

- Fixed statistics import failing due to CSRF token errors by creating fresh client instances for initial import and manual services

### Changed

- Updated .gitignore to exclude credential files

## [1.0.1] - 2025-12-05

### Fixed

- Fixed statistics import failing due to CSRF token errors from repeated login/logout cycles
- Fixed Energy Dashboard showing confusing partial data for current day
- Changed Current Cycle Usage sensor from TOTAL_INCREASING to TOTAL state class

### Changed

- Initial history import now reuses single session instead of login/logout per day
- Manual import services now create fresh client instances

## [1.0.0] - 2025-12-05

### Added

- Initial release
- ACWD Water Usage integration for Home Assistant
- Support for Energy Dashboard with hourly statistics
- Automatic import of last 7 days on first installation
- Manual import services for hourly and daily data
- Five water usage sensors (current cycle, projected, last billing, average, highest)
- 15-minute interval support via manual service

[Unreleased]: https://github.com/funkadelic/ha-acwd/compare/v1.0.4...HEAD
[1.0.4]: https://github.com/funkadelic/ha-acwd/compare/v1.0.3...v1.0.4
[1.0.3]: https://github.com/funkadelic/ha-acwd/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/funkadelic/ha-acwd/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/funkadelic/ha-acwd/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/funkadelic/ha-acwd/releases/tag/v1.0.0
