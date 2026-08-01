# mise.toml

Configuration file for development tool management.

## Purpose

This file configures [mise](https://mise.jdx.dev/) (formerly rtx), a developer tool manager that handles:
- Runtime versions (Python, Node.js, etc.)
- Development tools and linters
- Environment variables
- Task definitions

## Contents

- Python version specification
- Node.js version specification (if applicable)
- Installed packages and dependencies
- Environment variables for development
- Custom task definitions (dev, test, build, etc.)

## Usage

With mise installed, run:
```bash
mise install   # Install specified versions and tools
mise activate  # Activate the environment
mise run dev   # Run development tasks
```

This ensures consistent development environments across team members.
