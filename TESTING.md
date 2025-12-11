# Testing Guide

This document describes how to test the ACWD integration locally before deploying to Home Assistant.

## Prerequisites

- Python 3.8 or higher
- ACWD portal account credentials
- Required packages: `requests`, `beautifulsoup4`

Install dependencies:

```bash
pip install requests beautifulsoup4
```

## Running Tests

The `test_login.py` script tests the ACWD API client's login functionality and session management.

### Option 1: Environment Variables (Recommended)

Set your credentials as environment variables:

**Windows (cmd):**

```cmd
set ACWD_USERNAME=your_email@example.com
set ACWD_PASSWORD=your_password
python test_login.py
```

**Windows (PowerShell):**

```powershell
$env:ACWD_USERNAME="your_email@example.com"
$env:ACWD_PASSWORD="your_password"
python test_login.py
```

**Linux/Mac:**

```bash
export ACWD_USERNAME="your_email@example.com"
export ACWD_PASSWORD="your_password"
python test_login.py
```

### Option 2: Command-Line Arguments

```bash
python test_login.py your_email@example.com your_password
```

### Option 3: Interactive Prompt

Simply run the script and enter credentials when prompted:

```bash
python test_login.py
```

## What the Tests Do

The test suite performs four comprehensive tests:

1. **Fresh Client Instances** - Creates multiple independent client instances, each with their own login session. This validates the fix for CSRF token errors during initial history import.

2. **Reused Session** - Tests fetching data from multiple days using a single session. This validates that the session management works correctly for the coordinator's continuous polling.

3. **Hourly Data Conversion** - Shows the actual hourly water usage data as it would be imported into Home Assistant's statistics database. Displays usage by hour, cumulative totals, and daily summaries.

4. **Cumulative Sum Across Days** - Validates that cumulative sums are correctly calculated across day boundaries, preventing negative values at midnight. This test ensures yesterday's final sum is properly used as the baseline for today's first hour.

All tests must pass for the integration to work correctly.

## Expected Output

```bash
============================================================
ACWD API Login Test Suite
============================================================
Using credentials from environment variables

============================================================
🧪 Test 1: Fresh Client Instances
============================================================
  Creating client instance 1...
    [PASS] Login successful
    [PASS] Fetched 24 hourly records for 2025-12-03
    [PASS] Logout successful

  Creating client instance 2...
    [PASS] Login successful
    [PASS] Fetched 24 hourly records for 2025-12-03
    [PASS] Logout successful

  Creating client instance 3...
    [PASS] Login successful
    [PASS] Fetched 24 hourly records for 2025-12-03
    [PASS] Logout successful

[PASS] All fresh client instances worked correctly

============================================================
🧪 Test 2: Reused Session
============================================================
[PASS] Login successful

  Fetching data for 2025-12-03...
    [PASS] Retrieved 24 hourly records
  Fetching data for 2025-12-02...
    [PASS] Retrieved 24 hourly records
  Fetching data for 2025-12-01...
    [PASS] Retrieved 24 hourly records

[PASS] Reused session test succeeded

============================================================
🧪 Test 3: Hourly Data Conversion
============================================================
Fetching hourly data for: 2025-12-09

Hourly Usage Breakdown (as stored in Home Assistant):
  Hour         Gallons         Cumulative
  ----------------------------------------
  00:00        2.17            2.17
  01:00        2.69            4.86
  02:00        4.11            8.97
  ...
  23:00        3.82            172.34
  ========================================

  Daily Total: 172.34 gallons (24 hours)
  Average per hour: 7.18 gallons

  This is stored in HA as statistic: acwd:<meter_number>_hourly_usage

[PASS] Hourly data conversion test succeeded

============================================================
🤖 Test 4: Cumulative Sum Across Days
============================================================

1. Fetching YESTERDAY (2025-12-09) data...
   Yesterday total: 172.34 gallons (24 hours)
   Yesterday final cumulative sum: 172.34 gallons

2. Fetching TODAY (2025-12-10) data...

3. Calculating today's cumulative sum starting from yesterday's final sum...
   Baseline (yesterday final): 172.34 gallons

   Hour         Usage (gal)     Cumulative (gal)
   ---------------------------------------------
   00:00        3.89            176.23
   01:00        2.54            178.77
   ...

4. Validating cumulative sum calculations...
   ✅ PASS: First hour cumulative is positive (176.23 gallons)
   ✅ PASS: First hour matches yesterday final + first hour usage
      (172.34 + 3.89 = 176.23)
   ✅ PASS: Final cumulative matches expected
      (172.34 + 46.81 = 219.15)

[PASS] Cumulative sum across days validated successfully!

============================================================
Test Summary:
============================================================
✅ [PASS]: Fresh Client Instances
✅ [PASS]: Reused Session
✅ [PASS]: Hourly Data Conversion
✅ [PASS]: Cumulative Sum Across Days
============================================================
```

## Security Notes

**IMPORTANT:** Never commit credentials to git!

- The test script accepts credentials via environment variables or arguments
- Never hardcode credentials in the script
- `.gitignore` is configured to exclude credential files
- Use environment variables for automated testing

## Troubleshooting

### "No CSRF token found!"

This indicates a problem with the ACWD portal login page structure. The integration may need to be updated.

### "Login failed"

- Verify your credentials are correct
- Check if you can log in to <https://portal.acwd.org/portal/> manually
- Ensure your account is active

### Connection timeouts

- Check your internet connection
- The ACWD portal might be down or experiencing issues
- Try again later

---

## Unit Tests (pytest)

The integration includes unit tests to prevent regressions of critical bugs.

### Running Unit Tests

**Install test dependencies:**

```bash
pip install -r requirements-test.txt
```

**Run all tests:**

```bash
pytest
```

**Run with verbose output:**

```bash
pytest -v
```

**Run with coverage report:**

```bash
pytest --cov=custom_components.acwd --cov-report=term-missing
```

**Run specific test file:**

```bash
pytest tests/test_coordinator.py -v
```

### Test Coverage

The unit test suite currently covers:

**Coordinator Logic (8 tests)** - Validates early morning import timing and data handling

- Early morning import timing (3 tests)
  - Import runs during 0-6 AM window
  - Import correctly skips outside this window
- DateTime creation with timezones (2 tests)
  - PST timezone handling
  - EST timezone handling
- Data availability edge cases (3 tests)
  - Handles no data returned
  - Handles empty record sets

### Expected Output

```bash
$ pytest tests/test_coordinator.py -v
========================== test session starts ==========================
collected 8 items

tests/test_coordinator.py::TestEarlyMorningImport::test_early_morning_import_at_midnight PASSED
tests/test_coordinator.py::TestEarlyMorningImport::test_early_morning_import_at_5am PASSED
tests/test_coordinator.py::TestEarlyMorningImport::test_early_morning_import_at_6am PASSED
tests/test_coordinator.py::TestEarlyMorningImport::test_early_morning_import_at_noon PASSED
tests/test_coordinator.py::TestDateTimeCreation::test_create_local_datetime_pst PASSED
tests/test_coordinator.py::TestDateTimeCreation::test_create_local_datetime_est PASSED
tests/test_coordinator.py::TestDataAvailability::test_handle_no_data_returned PASSED
tests/test_coordinator.py::TestDataAvailability::test_handle_empty_records PASSED

========================== 8 passed in 0.25s ==========================

```

### Continuous Integration

Tests run automatically on GitHub Actions for every push and pull request:

- **Python Version**: 3.12 (matches Home Assistant 2024.2+ requirements)
- **Platform**: Ubuntu latest
- **Coverage Reporting**: Codecov

View test results at: `https://github.com/funkadelic/ha-acwd/actions`
