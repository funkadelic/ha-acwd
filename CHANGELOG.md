# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/funkadelic/acwd_usage/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/funkadelic/acwd_usage/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/funkadelic/acwd_usage/releases/tag/v1.0.0
