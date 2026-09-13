# `backend/tests/test_email_query_regression.py`

Regression tests for natural-language local email search.

## Covered behavior

- Plural search terms such as `invoices` find singular terms in stored email bodies.
- Short follow-up queries such as `or google?` remain classified as email queries when conversation history establishes the context.
- Matching sender information is included in the retrieved email context.

The module skips when ChromaDB is unavailable because the imported application services require it.
