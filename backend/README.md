# Backend

This directory contains the FastAPI backend application for Mindbase AI.

## Structure

- `main.py` - Entry point for the FastAPI application
- `database.py` - Database connection and initialization
- `models.py` - Pydantic models for request/response validation
- `ollama.py` - Ollama client integration
- `research.py` - Research functionality
- `memory.py` - Memory management
- `tasks_service.py` - Task scheduling and management
- `documents.py` - Document processing
- `imap_service.py` - Email IMAP service
- `intelligence.py` - Intelligence processing
- `config.py` - Configuration settings
- `tests/` - Test files for backend components
- `requirements.txt` - Production dependencies
- `requirements-dev.txt` - Development dependencies

## Running the Backend

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn main:app
```
