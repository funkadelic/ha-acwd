@echo off
REM ACWD Login Test Runner
REM
REM Usage:
REM   1. Copy this file to run_tests_local.bat (which is gitignored)
REM   2. Edit run_tests_local.bat and set your credentials
REM   3. Run: run_tests_local.bat
REM
REM DO NOT commit your credentials to git!

echo ============================================================
echo ACWD API Login Test Suite
echo ============================================================
echo.
echo Please set ACWD_USERNAME and ACWD_PASSWORD environment variables
echo or pass credentials as arguments to test_login.py
echo.
echo Example:
echo   set ACWD_USERNAME=your_email@example.com
echo   set ACWD_PASSWORD=your_password
echo   python test_login.py
echo.
pause
