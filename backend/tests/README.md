# Backend Tests

This directory contains test files for the backend components.

## Test Files

- `test.py` - Standalone test script
- `test_scheduling.py` - Schedule-related tests
- `conftest.py` - Pytest configuration
- `backend/tests/` - Pytest test suite for hot paths

## Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Install test dependencies
pip install -r backend/requirements-dev.txt

# Run pytest
pytest backend/tests/
```
