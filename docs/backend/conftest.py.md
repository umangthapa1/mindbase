# conftest.py

Pytest configuration file for backend tests.

## Purpose

This file contains pytest fixtures and configuration that are automatically discovered by pytest for backend test modules.

## Contents

- Test fixtures for database setup/teardown
- Mock objects for external services
- Common test utilities
- Pytest plugin configuration

## Usage

This file is automatically loaded by pytest when running `pytest backend/tests/`. No explicit import is needed in test files.
