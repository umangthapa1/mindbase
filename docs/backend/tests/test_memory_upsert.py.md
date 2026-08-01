# test_memory_upsert.py

Tests for memory upsert (update/insert) functionality.

## Purpose

This test file verifies the memory management system's ability to:
- Insert new memories
- Update existing memories
- Handle memory deduplication
- Manage memory associations and links
- Persist memory to storage

## Test Cases

- Memory creation with various data types
- Memory updates with partial and full data
- Memory deduplication based on content similarity
- Memory linking and association
- Memory retrieval by various criteria
- Memory deletion and archiving
- Concurrent memory operations

## Usage

Run with pytest:
```bash
pytest backend/tests/test_memory_upsert.py
```
