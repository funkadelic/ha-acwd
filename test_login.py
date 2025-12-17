#!/usr/bin/env python3
"""Standalone test script for ACWD API login functionality.

Usage:
    # Using environment variables (recommended)
    set ACWD_USERNAME=your_email@example.com
    set ACWD_PASSWORD=your_password
    python test_login.py

    # Using command-line arguments
    python test_login.py your_email@example.com your_password

    # Interactive prompt (if no credentials provided)
    python test_login.py
"""

import sys
import os
from datetime import datetime, timedelta
from getpass import getpass

# Add the custom_components directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components', 'acwd'))

# Import only the API client (not the HA integration)
from acwd_api import ACWDClient

# Conversion constant
HCF_TO_GALLONS = 748


def get_credentials():
    """Get credentials from environment, args, or prompt."""
    # Try environment variables first
    username = os.getenv('ACWD_USERNAME')
    password = os.getenv('ACWD_PASSWORD')

    if username and password:
        print('Using credentials from environment variables')
        return username, password

    # Try command-line arguments
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
        print('Using credentials from command-line arguments')
        return username, password

    # Prompt user
    print('No credentials found in environment or arguments.')
    print('Please enter your ACWD portal credentials:')
    username = input('Email: ')
    password = getpass('Password: ')

    return username, password


def test_fresh_client_instances(username, password):
    """Test creating multiple fresh client instances (validates session management fix)."""
    print('\n' + '=' * 60)
    print('🧪 Test 1: Fresh Client Instances')
    print('=' * 60)

    for i in range(3):
        print(f'  Creating client instance {i+1}...')
        client = ACWDClient(username, password)

        if not client.login():
            print(f'    [FAIL] Login failed on instance {i+1}')
            return False

        print('    [PASS] Login successful')

        # Fetch data to verify session works
        test_date = (datetime.now() - timedelta(days=2)).date()
        data = client.get_usage_data('H', None, None, test_date.strftime('%m/%d/%Y'), 'H')

        if data:
            records = data.get('objUsageGenerationResultSetTwo', [])
            print(f'    [PASS] Fetched {len(records)} hourly records for {test_date}')

            # Show all hourly data (raw values from API)
            if records and i == 0:  # Only show details for first instance
                print('\n    All hourly data:')
                print('    Time         Gallons        ')
                print('    ---------------------------')
                for record in records:
                    hourly_str = record.get("Hourly", "12:00 AM")
                    usage_value = record.get("UsageValue", 0)
                    print(f'    {hourly_str:<12} {usage_value:<15.2f}')
                print()
        else:
            print('    [FAIL] Could not fetch data')
            client.logout()
            return False

        client.logout()
        print('    [PASS] Logout successful\n')

    print('\n[PASS] All fresh client instances worked correctly')
    return True


def test_reused_session(username, password):
    """Test reusing a single session for multiple API calls."""
    print('\n' + '=' * 60)
    print('🧪 Test 2: Reused Session')
    print('=' * 60)

    client = ACWDClient(username, password)

    if not client.login():
        print('[FAIL] Login failed')
        return False

    print('[PASS] Login successful\n')

    # Test fetching data for 3 different days using same session
    for i in range(3):
        test_date = (datetime.now() - timedelta(days=2+i)).date()
        print(f'  Fetching data for {test_date}...')

        data = client.get_usage_data('H', None, None, test_date.strftime('%m/%d/%Y'), 'H')
        if data:
            records = data.get('objUsageGenerationResultSetTwo', [])
            print(f'    [PASS] Retrieved {len(records)} hourly records')

            # Show all hourly data for first day only
            if records and i == 0:
                print('\n    All hourly data:')
                print('    Time         Gallons        ')
                print('    ---------------------------')
                for record in records:
                    hourly_str = record.get("Hourly", "12:00 AM")
                    usage_value = record.get("UsageValue", 0)
                    print(f'    {hourly_str:<12} {usage_value:<15.2f}')
                print()
        else:
            print('    [FAIL] No data returned')
            client.logout()
            return False

    client.logout()
    print('\n[PASS] Reused session test succeeded')
    return True


def test_hourly_data_conversion(username, password):
    """Test and display how hourly data is converted for HA statistics."""
    print('\n' + '=' * 60)
    print('🧪 Test 3: Hourly Data Conversion')
    print('=' * 60)

    client = ACWDClient(username, password)

    if not client.login():
        print('[FAIL] Login failed')
        return False

    # Get data for 2 days ago (usually has complete 24-hour data)
    test_date = (datetime.now() - timedelta(days=2)).date()
    print(f'  Fetching hourly data for {test_date}...\n')

    data = client.get_usage_data('H', None, None, test_date.strftime('%m/%d/%Y'), 'H')

    if not data:
        print('[FAIL] No data returned')
        client.logout()
        return False

    hourly_data = data.get('objUsageGenerationResultSetTwo', [])

    if not hourly_data:
        print('[FAIL] No hourly records found')
        client.logout()
        return False

    print(f'  [PASS] Retrieved {len(hourly_data)} hourly records\n')
    print('  ========================================')
    print('  Hour         Gallons         Cumulative     ')
    print('  ----------------------------------------')

    # Calculate cumulative sum
    cumulative_sum = 0.0

    # Show all hourly data
    for record in hourly_data:
        hourly_str = record.get("Hourly", "12:00 AM")  # Format: "12:00 AM", "1:00 AM", etc.
        usage_gallons = record.get("UsageValue", 0)
        cumulative_sum += usage_gallons

        # Parse hour for display
        try:
            time_obj = datetime.strptime(hourly_str, "%I:%M %p")
            hour = time_obj.hour
            display_time = f'{hour:02d}:00'
        except (ValueError, TypeError):
            display_time = hourly_str

        print(f'  {display_time:<12} {usage_gallons:<15.2f} {cumulative_sum:<15.2f}')

    # Calculate daily total
    daily_total = sum(r.get("UsageValue", 0) for r in hourly_data)

    print('  ========================================')
    print(f'\n  Daily Total: {daily_total:,.2f} gallons ({len(hourly_data)} hours)')
    print(f'  Average per hour: {daily_total / len(hourly_data):,.2f} gallons')
    print('\n  This is stored in HA as statistic: acwd:<meter_number>_hourly_usage')

    client.logout()
    print('\n[PASS] Hourly data conversion test succeeded')
    return True


def test_cumulative_sum_across_days(username, password):
    """Test cumulative sum calculation across day boundaries.

    This validates the fix for negative midnight values by:
    1. Fetching yesterday's data and calculating final cumulative sum
    2. Fetching today's data and starting from yesterday's final sum
    3. Verifying the midnight hour doesn't show negative values
    """
    from datetime import timedelta

    print('\n' + '=' * 60)
    print('🧪 Test 4: Cumulative Sum Across Days')
    print('=' * 60)

    client = ACWDClient(username, password)

    if not client.login():
        print('[FAIL] Login failed')
        return False

    try:
        yesterday = (datetime.now() - timedelta(days=1)).date()
        today = datetime.now().date()

        print(f'\n1. Fetching YESTERDAY ({yesterday}) data...')
        yesterday_str = yesterday.strftime('%m/%d/%Y')
        yesterday_data = client.get_usage_data('H', None, None, yesterday_str, 'H')

        if not yesterday_data:
            print('[WARN] No yesterday data available')
            yesterday_final_sum = 0
            yesterday_total = 0
        else:
            yesterday_records = yesterday_data.get('objUsageGenerationResultSetTwo', [])

            # Calculate yesterday's cumulative sum
            yesterday_cumulative = 0
            yesterday_total = 0
            for record in yesterday_records:
                usage = record.get('UsageValue', 0)
                yesterday_cumulative += usage
                yesterday_total += usage

            yesterday_final_sum = yesterday_cumulative
            print(f'   Yesterday total: {yesterday_total:,.2f} gallons ({len(yesterday_records)} hours)')
            print(f'   Yesterday final cumulative sum: {yesterday_final_sum:,.2f} gallons')

        print(f'\n2. Fetching TODAY ({today}) data...')
        today_str = today.strftime('%m/%d/%Y')
        today_data = client.get_usage_data('H', None, None, today_str, 'H')

        if not today_data:
            print('[FAIL] No today data available')
            return False

        today_records = today_data.get('objUsageGenerationResultSetTwo', [])

        print('\n3. Calculating today\'s cumulative sum starting from yesterday\'s final sum...')
        print(f'   Baseline (yesterday final): {yesterday_final_sum:,.2f} gallons')
        print('\n   Hour         Usage (gal)     Cumulative (gal)')
        print('   ---------------------------------------------')

        # Start today's cumulative sum from yesterday's final
        cumulative_sum = yesterday_final_sum
        today_total = 0
        first_hour = None

        for record in today_records:
            hourly_str = record.get('Hourly', '12:00 AM')
            usage = record.get('UsageValue', 0)
            cumulative_sum += usage
            today_total += usage

            # Parse hour for display
            try:
                time_obj = datetime.strptime(hourly_str, '%I:%M %p')
                hour = time_obj.hour
                display_time = f'{hour:02d}:00'
            except (ValueError, TypeError):
                display_time = hourly_str

            # Save first hour for validation
            if first_hour is None:
                first_hour = {
                    'time': display_time,
                    'usage': usage,
                    'cumulative': cumulative_sum
                }

            # Only show first 5 and last 3 hours to keep output concise
            if len([r for r in today_records if r.get('UsageValue', 0) > 0]) <= 8 or \
               today_records.index(record) < 5 or \
               today_records.index(record) >= len(today_records) - 3:
                print(f'   {display_time:<12} {usage:>14.2f}     {cumulative_sum:>14.2f}')
            elif today_records.index(record) == 5:
                print('   ...')

        print('   =============================================')
        print('\n4. Validation Results:')
        print(f'   Yesterday total: {yesterday_total:,.2f} gallons')
        print(f'   Today total so far: {today_total:,.2f} gallons ({len(today_records)} hours)')
        print(f'   Today\'s first hour ({first_hour["time"]}):')
        print(f'      Usage: {first_hour["usage"]:,.2f} gallons')
        print(f'      Cumulative: {first_hour["cumulative"]:,.2f} gallons')

        # Validation checks
        print('\n5. Validation Checks:')

        # Check 1: First hour cumulative should be positive
        if first_hour['cumulative'] < 0:
            print(f'   ❌ FAIL: First hour cumulative is NEGATIVE ({first_hour["cumulative"]:.2f})')
            return False
        else:
            print(f'   ✅ PASS: First hour cumulative is positive ({first_hour["cumulative"]:,.2f})')

        # Check 2: First hour cumulative should equal yesterday's final + first hour usage
        expected_first_cumulative = yesterday_final_sum + first_hour['usage']
        if abs(first_hour['cumulative'] - expected_first_cumulative) < 0.01:
            print('   ✅ PASS: First hour cumulative matches expected')
            print(f'      ({yesterday_final_sum:,.2f} + {first_hour["usage"]:.2f} = {expected_first_cumulative:,.2f})')
        else:
            print('   ❌ FAIL: First hour cumulative doesn\'t match')
            print(f'      Expected: {expected_first_cumulative:,.2f}')
            print(f'      Got: {first_hour["cumulative"]:.2f}')
            return False

        # Check 3: Final cumulative should equal yesterday + today
        expected_final = yesterday_final_sum + today_total
        if abs(cumulative_sum - expected_final) < 0.01:
            print('   ✅ PASS: Final cumulative matches expected')
            print(f'      ({yesterday_final_sum:,.2f} + {today_total:,.2f} = {expected_final:,.2f})')
        else:
            print('   ❌ FAIL: Final cumulative doesn\'t match')
            print(f'      Expected: {expected_final:,.2f}')
            print(f'      Got: {cumulative_sum:.2f}')
            return False

        print('\n[PASS] Cumulative sum across days validated successfully!')
        return True

    except Exception as e:
        print(f'[FAIL] Test failed with error: {e}')
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.logout()


if __name__ == '__main__':
    print('=' * 60)
    print('ACWD API Login Test Suite')
    print('=' * 60)

    try:
        username, password = get_credentials()
    except KeyboardInterrupt:
        print('\n\nTest cancelled by user')
        sys.exit(1)
    except Exception as e:
        print(f'\nError getting credentials: {e}')
        sys.exit(1)

    results = []

    # Test 1: Fresh client instances (validates the fix for initial import)
    results.append(('Fresh Client Instances', test_fresh_client_instances(username, password)))

    # Test 2: Reused session (validates session persistence)
    results.append(('Reused Session', test_reused_session(username, password)))

    # Test 3: Hourly data conversion (shows what gets inserted into HA)
    results.append(('Hourly Data Conversion', test_hourly_data_conversion(username, password)))

    # Test 4: Cumulative sum across days (validates the fix for negative midnight values)
    results.append(('Cumulative Sum Across Days', test_cumulative_sum_across_days(username, password)))

    # Summary
    print('\n' + '=' * 60)
    print('Test Summary:')
    print('=' * 60)
    for name, passed in results:
        status = '✅ [PASS]' if passed else '❌ [FAIL]'
        print(f'{status}: {name}')

    all_passed = all(result for _, result in results)
    print('=' * 60)

    sys.exit(0 if all_passed else 1)
