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


def get_credentials():
    """Get credentials from environment, args, or prompt."""
    # Try environment variables first
    username = os.getenv('ACWD_USERNAME')
    password = os.getenv('ACWD_PASSWORD')

    if username and password:
        print(f'Using credentials from environment variables')
        return username, password

    # Try command-line arguments
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
        print(f'Using credentials from command-line arguments')
        return username, password

    # Prompt user
    print('No credentials found in environment or arguments.')
    print('Please enter your ACWD portal credentials:')
    username = input('Email: ')
    password = getpass('Password: ')

    return username, password


def test_fresh_client_instances(username, password):
    """Test creating multiple fresh client instances (validates session management fix)."""
    print('Testing fresh client instances (simulates initial import behavior):\n')

    for i in range(3):
        print(f'  Creating client instance {i+1}...')
        client = ACWDClient(username, password)

        if not client.login():
            print(f'    [FAIL] Login failed on instance {i+1}')
            return False

        print(f'    [PASS] Login successful')

        # Fetch data to verify session works
        test_date = (datetime.now() - timedelta(days=2)).date()
        data = client.get_usage_data('H', None, None, test_date.strftime('%m/%d/%Y'), 'H')

        if data:
            records = data.get('objUsageGenerationResultSetTwo', [])
            print(f'    [PASS] Fetched {len(records)} hourly records for {test_date}')
        else:
            print(f'    [FAIL] Could not fetch data')
            client.logout()
            return False

        client.logout()
        print(f'    [PASS] Logout successful\n')

    print('[PASS] All fresh client instances worked correctly')
    return True


def test_reused_session(username, password):
    """Test reusing a single session for multiple API calls."""
    print('Testing reused session for multiple days:\n')

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
        else:
            print(f'    [FAIL] No data returned')
            client.logout()
            return False

    client.logout()
    print('\n[PASS] Reused session test succeeded')
    return True


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

    # Summary
    print('\n' + '=' * 60)
    print('Test Summary:')
    print('=' * 60)
    for name, passed in results:
        status = '[PASS]' if passed else '[FAIL]'
        print(f'{name}: {status}')

    all_passed = all(result for _, result in results)
    print('=' * 60)

    sys.exit(0 if all_passed else 1)
