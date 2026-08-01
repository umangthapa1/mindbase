# Mindbase Backend - config.py

## Overview
Configuration management module that loads environment variables and defines application-wide constants including paths, API settings, and default values.

## Responsibilities
- Load environment variables from `.env` file or system environment
- Define path constants for important directories and files
- Set default values for API configuration
- Provide configuration values to other modules throughout the application

## Key Constants

### Path Configuration
- `BASE_DIR`: Root directory of the project
- `DATA_DIR`: Directory for persistent data (`data/`)
- `FRONTEND_PATH`: Path to frontend static files
- `CHROMA_PATH`: Directory for ChromaDB vector store
- `UPLOADS_DIR`: Directory for uploaded documents
- `ENV_FILE`: Path to `.env` configuration file

### API Configuration
- `API_HOST`: Host address for the API server (default: `127.0.0.1`)
- `API_PORT`: Port for the API server (default: `8000`)
- `OLLAMA_HOST`: URL for Ollama service (default: `http://localhost:11434`)
- `DEFAULT_MODEL`: Default LLM model to use (default: `mistral`)
- `CORS_ORIGINS`: Comma-separated list of allowed origins for CORS
- `CORS_ALLOW_CREDENTIALS`: Whether to allow credentials in CORS requests

### Email Configuration
- Email-related constants would be loaded from environment or default values

## Environment Variables
The module uses the following environment variables (with defaults in parentheses):

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `DEFAULT_MODEL` | `mistral` | Default chat model |
| `API_HOST` | `127.0.0.1` | API bind address |
| `API_PORT` | `8000` | API port |
| `CORS_ORIGINS` | *(empty)* | CORS allow-list (empty = wildcard without credentials) |

## Usage
Other modules import configuration values directly:
```python
from config import API_HOST, API_PORT, DEFAULT_MODEL, BASE_DIR
```

The configuration is loaded once at import time and remains constant throughout the application lifecycle.

## Security Notes
- No secrets should be stored in this module
- Email credentials are handled separately in `data/email_config.json`
- The `.env` file should be added to `.gitignore` to prevent committing sensitive data