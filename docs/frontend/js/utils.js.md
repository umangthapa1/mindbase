# utils.js

Frontend utility functions for common tasks and helper methods.

## Purpose

This file contains reusable utility functions used throughout the frontend application, including:
- DOM manipulation helpers
- String formatting and parsing
- Date and time utilities
- Storage helpers (localStorage, sessionStorage)
- Event handling utilities
- Miscellaneous helper functions

## Contents

- DOM helpers (e.g., creating elements, toggling classes)
- String utilities (e.g., truncating, formatting)
- Date/time utilities (e.g., formatting dates, calculating durations)
- Storage helpers (e.g., getting, setting, removing items)
- Event utilities (e.g., debouncing, throttling)
- Network helpers (e.g., building URLs, handling API responses)
- Miscellaneous (e.g., unique ID generation, deep cloning)

## Usage

Import or use the utility functions directly in other JavaScript files:
```javascript
import { formatDate, debounce } from './utils.js';
// or if using global:
// utils.formatDate(date);
```
