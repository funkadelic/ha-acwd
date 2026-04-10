# Contributing to ha-acwd

Thanks for your interest in contributing! This guide covers everything you need to set up a local development environment and submit changes.

## Prerequisites

- **Python 3.13** — required by the test framework (`pytest-homeassistant-custom-component`)

Check your Python version:

```bash
python3 --version
```

If you need Python 3.13, install it via [pyenv](https://github.com/pyenv/pyenv), your system package manager, or [python.org](https://www.python.org/downloads/).

## Development Setup

### 1. Fork and clone

Fork the repository on GitHub, then clone your fork (replace `YOUR_USERNAME` with your GitHub username):

```bash
git clone https://github.com/YOUR_USERNAME/ha-acwd.git
cd ha-acwd
```

### 2. Create a virtual environment

Always use a virtual environment to isolate project dependencies from your system Python:

```bash
python3 -m venv .venv
```

Activate it:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (cmd)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

Your terminal prompt should now show `(.venv)` indicating the virtual environment is active. You'll need to activate it each time you open a new terminal.

### 3. Install dependencies

```bash
pip install -r requirements.txt -r requirements-test.txt
```

This installs both runtime dependencies (`beautifulsoup4`) and test dependencies (`pytest`, `pytest-homeassistant-custom-component`, `freezegun`, etc.).

## Running Tests

All test configuration lives in `pyproject.toml` — no extra flags needed:

```bash
pytest
```

This runs the full suite with coverage reporting. To run a specific test file:

```bash
pytest tests/test_acwd_api.py -v
```

To run tests by marker:

```bash
pytest -m unit         # Unit tests (no network, no HA core)
pytest -m integration  # Integration tests requiring HA fixtures
```

See [TESTING.md](TESTING.md) for details on the integration test script (`test_login.py`) that tests against the live ACWD portal.

## Linting and Formatting

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Run both before submitting a PR:

```bash
python -m ruff check --fix .
python -m ruff format .
```

Ruff configuration is in `pyproject.toml`.

## Submitting Changes

1. **Create a branch** off `main` for your changes:

   ```bash
   git checkout -b your-branch-name
   ```

2. **Make your changes** and verify they pass:

   ```bash
   pytest
   python -m ruff check --fix .
   python -m ruff format .
   ```

3. **Commit** with a descriptive message using [conventional commit](https://www.conventionalcommits.org/) format:

   ```text
   feat: add support for quarterly billing data
   fix: handle missing hourly records gracefully
   refactor: extract meter discovery into helper
   ```

4. **Push** and open a pull request against `main`.

## Project Structure

```text
custom_components/acwd/
├── __init__.py        # Integration setup, coordinator, services
├── acwd_api.py        # ACWD portal API client (web scraping)
├── config_flow.py     # Configuration UI flow
├── const.py           # Constants and unit conversions
├── helpers.py         # Shared utilities (parsing, timezone)
├── sensor.py          # Sensor entities (billing cycle data)
├── statistics.py      # Statistics import (hourly/daily data)
└── manifest.json      # Integration metadata

tests/
├── conftest.py        # Shared fixtures
├── test_init.py       # Coordinator, services, setup/unload
├── test_acwd_api.py   # API client login, data fetching
├── test_helpers.py    # Date/time parsing, API response parsing
├── test_sensor.py     # Sensor entities, billing data
├── test_statistics.py # Hourly statistics import, baselines
└── ...
```

## Code Style

- Use lazy `%s` formatting for logging (not f-strings) per ruff rule G004
- Use constants from `const.py` — avoid magic strings
- Use helpers from `helpers.py` for date/time parsing and API response handling
- Always log out in `finally` blocks when using the API client
