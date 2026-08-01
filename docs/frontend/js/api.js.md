# Mindbase Frontend - js/api.js

## Overview
Centralized wrapper for all backend API communications. Handles request formatting, error handling, response parsing, and provides a consistent interface for interacting with the Mindbase backend services.

## Responsibilities
- Provide consistent HTTP client for all backend endpoints
- Handle request/response formatting (JSON serialization/deserialization)
- Manage error handling and normalize error responses
- Support authentication headers (if applicable)
- Provide helper methods for common HTTP verbs (GET, POST, PUT, DELETE)
- Handle file uploads and downloads
- Support Server-Sent Events (SSE) for streaming responses
- Provide request cancellation capabilities
- Log API requests/responses for debugging (in development)
- Handle timeout configurations
- Manage base URL and endpoint construction

## Key Features

### HTTP Methods
- `get(url, params, config)`: GET request with query parameters
- `post(url, data, config)`: POST request with JSON body
- `put(url, data, config)`: PUT request with JSON body
- `patch(url, data, config)`: PATCH request with JSON body
- `delete(url, config)`: DELETE request
- `postForm(url, formData, config)`: POST with FormData (file uploads)
- `getStream(url, config)`: GET request returning readable stream
- `postStream(url, data, config)`: POST request returning readable stream

### Specialized Methods
- `chatStream(conversationId, message, config)`: 
  Specialized method for streaming chat responses via SSE
  Returns async generator for consuming response chunks
  
- `researchStream(query, config)`:
  Specialized method for streaming research progress via SSE
  Returns async generator for consuming progress updates
  
- `uploadFile(file, metadata)`:
  Handles file uploads with progress tracking
  Returns promise resolving to upload result
  
- `downloadFile(url, filename)`:
  Handles file downloads
  Creates blob and triggers download

### Configuration Options
All methods accept an optional `config` object:
```javascript
{
  headers: {...},           // Additional headers
  params: {...},            // Query parameters (for GET)
  timeout: 5000,           // Request timeout in ms
  onUploadProgress: fn,    // Progress callback for uploads
  onDownloadProgress: fn,  // Progress callback for downloads
  cancelToken: token,      // Cancellation token
  responseType: 'json'     // Response type (json, text, blob, stream)
}
```

## Error Handling

### Normalized Error Format
All API errors are normalized to a consistent format:
```javascript
{
  success: false,
  error: {
    message: "Human readable error message",
    code: "ERROR_CODE",    // Machine readable error code
    status: 400,           // HTTP status code
    details: {...}         // Additional error details (validation errors, etc.)
  }
}
```

### Error Types Handled
- Network errors (failed to connect, timeout)
- HTTP errors (4xx, 5xx responses)
- Validation errors (422 with field-specific messages)
- Server errors (500+ with error details)
- Aborted requests (cancellation)
- JSON parsing errors
- File upload/download errors

### Error Classification
- `NETWORK_ERROR`: Connection/DNS/timeout issues
- `BAD_REQUEST`: 400 errors (validation, malformed requests)
- `UNAUTHORIZED`: 401 errors (authentication required)
- `FORBIDDEN`: 403 errors (insufficient permissions)
- `NOT_FOUND`: 404 errors (resource not found)
- `CONFLICT`: 409 errors (resource conflicts)
- `UNPROCESSABLE_ENTITY`: 422 errors (validation failures)
- `TOO_MANY_REQUESTS`: 429 errors (rate limiting)
- `INTERNAL_SERVER_ERROR`: 500+ errors (server issues)

## Request/Response Handling

### Automatic JSON Handling
- Request bodies automatically JSON.stringify()'ed
- Response bodies automatically JSON.parse()'ed (when responseType: json)
- Content-Type: application/json header set automatically
- Accept: application/json header set automatically

### Query Parameter Serialization
- Objects converted to query strings
- Arrays handled with repeat keys or bracket notation
- Dates converted to ISO strings
- Booleans converted to true/false strings
- Null/undefined values filtered out

### File Upload Handling
- Uses FormData for multipart/form-data requests
- Automatic content-type setting (multipart/form-data)
- Progress tracking available via onUploadProgress
- File metadata can be included as additional fields

### Streaming Support (SSE)
- Special handling for Server-Sent Events
- Returns async iterable for consuming event stream
- Automatic parsing of data: lines
- Error handling for stream interruptions
- Automatic reconnection logic (configurable)
- Event type detection and routing

## Usage Examples

### Basic GET Request
```javascript
// Get list of conversations
const response = await api.get('/api/chat/conversations');
if (response.success) {
  const conversations = response.data;
} else {
  toast.error(response.error.message);
}
```

### POST Request with Data
```javascript
// Create a new task
const taskData = {
  title: "Complete project proposal",
  description: "Finish the Q3 project proposal document",
  priority: 2,
  due_date: "2026-08-01T10:00:00Z",
  tags: ["work", "deadline"]
};

const response = await api.post('/api/tasks', taskData);
if (response.success) {
  const newTask = response.data;
  // Handle successful creation
} else {
  // Handle validation errors
  if (response.error.code === 'VALIDATION_ERROR') {
    // Show field-specific errors
    form.setErrors(response.error.details);
  }
}
```

### File Upload
```javascript
// Upload a document
const fileInput = document.getElementById('file-input');
const file = fileInput.files[0];

const response = await api.uploadFile(file, {
  description: "Project specifications",
  tags: ["specification", "project"]
});

if (response.success) {
  const document = response.data;
  // Handle successful upload
} else {
  toast.error(`Upload failed: ${response.error.message}`);
}
```

### Streaming Chat Response
```javascript
// Send a message and stream the response
const messageInput = document.getElementById('message-input');
const message = messageInput.value;

try {
  const stream = await api.chatStream(conversationId, message);
  
  // Process streaming response
  let fullResponse = '';
  for await const chunk of stream) {
    if (chunk.type === 'content') {
      fullResponse += chunk.content;
      // Update UI with accumulated response
      updateChatMessage(fullResponse);
    } else if (chunk.type === 'meta') {
      // Handle metadata (intent, context sources, etc.)
      updateMetadata(chunk.meta);
    } else if (chunk.type === 'done') {
      // Stream completed
      handleStreamComplete(chunk.messageId);
    }
  }
} catch (error) {
  toast.error(`Failed to send message: ${error.message}`);
}
```

### Research Progress Streaming
```javascript
// Start research and stream progress
const researchQuery = document.getElementById('research-input').value;

try {
  const stream = await api.researchStream(researchQuery);
  
  // Process research progress updates
  for await const update of stream) {
    switch (update.type) {
      case 'planning':
        updateStatus(`Planning: ${update.step}`);
        break;
      case 'executing':
        updateProgress(update.step, update.total, update.message);
        break;
      case 'synthesizing':
        updateStatus(`Synthesizing: ${update.message}`);
        break;
      case 'report':
        // Research completed, show report
        showResearchReport(update.report);
        break;
      case 'error':
        toast.error(update.message);
        break;
      case 'complete':
        hideResearchLoader();
        break;
    }
  }
} catch (error) {
  toast.error(`Research failed: ${error.message}`);
}
```

### Request Cancellation
```javascript
// Create cancellation token source
const controller = new AbortController();

// Pass cancellation token to request
const response = await api.get('/api/documents', {
  signal: controller.signal
});

// Later, cancel the request
controller.abort();

// Or with timeout
const timeoutResponse = await api.get('/api/documents', {
  timeout: 5000 // 5 second timeout
});
```

## Authentication (Placeholder)
Currently no authentication is implemented as the application is local-first.
Future enhancements might include:
- Token-based authentication
- Refresh token handling
- Automatic token renewal
- Logout/session clearing

## Configuration

### Base URL
- Automatically determined from window.location
- Falls back to defaults:
  - Development: http://localhost:8000
  - Production: same origin as frontend
- Can be overridden via configuration

### Default Settings
- Timeout: 10000ms (10 seconds)
- Retry attempts: 0 (no automatic retries)
- Retry delay: 1000ms
- Retry on: network errors, 5xx errors
- Headers: 
  - Accept: application/json
  - Content-Type: application/json (for JSON requests)

## Error Handling Details

### Network Errors
- Timeout: Request exceeds timeout threshold
- Failed to connect: Cannot reach backend server
- DNS resolution
- DNS failure: Cannot resolve backend hostname
- Connection refused: Backend not running or wrong port
- Offline: No network connectivity

### HTTP Error Mapping
- 400: Bad Request - Malformed request or validation error
- 401: Unauthorized - Authentication required
- 403: Forbidden - Insufficient permissions
- 404: Not Found - Requested resource doesn't exist
- 409: Conflict - Resource conflict (duplicate, etc.)
- 422: Unprocessable Entity - Validation failure
- 429: Too Many Requests - Rate limiting
- 500: Internal Server Error - Unexpected server condition
- 502: Bad Gateway - Invalid response from upstream server
- 503: Service Unavailable - Server temporarily unavailable
- 504: Gateway Timeout - Upstream server timeout

### Validation Errors
When status is 422, error details typically include:
```javascript
{
  message: "Validation failed",
  code: "VALIDATION_ERROR",
  status: 422,
  details: {
    field1: ["Error message for field1"],
    field2: ["Error message for field2"],
    // ...
  }
}
```

## Security Considerations

### CSRF Protection
- Relies on SameSite cookies and same-origin policy
- No custom CSRF tokens implemented as API is same-origin
- Future enhancement: implement CSRF tokens if needed

### Input Sanitization
- API layer does not perform input sanitization
- Sanitization expected at backend level
- Frontend should sanitize user input before sending

### Output Encoding
- API returns raw data from backend
- Frontend responsible for proper encoding when displaying
- XSS prevention handled in view layer, not API layer

## Performance Features

### Request Deduplication
- Optional request deduplication for identical requests
- Prevents redundant API calls
- Configurable per request

### Caching
- Simple GET request caching available
- Cache- control headers respected
- Stale-while-revalidate pattern supported
- Configurable TTL per request

### Batch Requests
- Helper for sending multiple related requests
- Reduces round trips
- Transactional behavior options

### Connection Pooling
- Uses browser's built-in connection pooling
- Keep-alive connections enabled by default
- No manual connection management needed

## Implementation Details

### XMLHttpRequest vs Fetch API
- Built on top of fetch API for modern browser support
- Falls back to XMLHttpRequest for older browsers if needed
- Consistent promise-based interface
- Better streaming support with fetch

### AbortController Integration
- Native abort controller support for request cancellation
- Integrates with browser's native cancellation mechanisms
- Works with fetch API natively

### Progress Events
- Supports upload/download progress tracking
- Uses native progress events from XMLHttpRequest/fetch
- Provides percentage and transferred/total bytes

### Header Management
- Automatic header merging (defaults + config + auth)
- Prevents accidental header overwrites
- Case-insensitive header handling

### URL Building
- Properly handles base URLs with/without trailing slashes
- Correctly joins paths and query parameters
- Encodes special characters appropriately
- Handles relative and absolute URLs

## Usage Guidelines

### When to Use api.js
- All backend communications should go through this module
- Direct fetch/XMLHttpRequest usage discouraged
- Ensures consistent error handling and formatting
- Provides centralized place for auth/header injection
- Enables easy switching of HTTP libraries if needed

### Error Handling Patterns
1. **Simple handling**: Check response.success and show toast
2. **Field-specific handling**: Check for VALIDATION_ERROR and show form errors
3. **Redirect handling**: Handle 401/403 by redirecting to login
4. **Retry logic**: Implement exponential backoff for transient errors
5. **User feedback**: Show loading states, disable buttons during requests
6. **Logging**: Log errors to monitoring service in production

### Response Data Handling
- Assume response.data contains the payload for successful requests
- For list endpoints: response.data is typically an array
- For item endpoints: response.data is typically an object
- Check API documentation for specific endpoint response shapes
- Defensive programming: check for existence of expected fields

### Request Data Handling
- Convert internal data structures to API-expected format
- Handle undefined/null values appropriately (usually omit)
- Serialize dates to ISO strings unless otherwise specified
- Convert internal enums/booleans to API-expected strings/numbers

### Testing
- Mock api.js methods in unit tests
- Test success and error paths
- Test timeout and cancellation behavior
- Validate request/response formatting
- Test progress callbacks and streaming behavior

## Dependencies
- Native browser APIs: fetch, AbortController, FormData, Blob
- No external dependencies
- Designed to work in modern browsers
- Polyfill strategy for older browsers if needed

## Configuration and Extension

### Creating Custom Instances
```javascript
// Create a customized API instance with different base url
const customApi = createApiClient({
  baseUrl: 'http://localhost:3000/api',
  timeout: 15000,
  headers: {
    'X-Custom-Header': 'value'
  }
});

// Use the custom instance
const response = await customApi.get('/custom-endpoint');
```

### Adding Interceptors
- Request interceptors for logging/auth
- Response interceptors for error normalization
- Currently implemented internally, could be exposed

### Mocking for Development
- Could be extended to support mock mode
- Useful for frontend development without backend
- Would return simulated responses based on configuration

## Browser Support
- Targets modern browsers (Chrome, Firefox, Safari, Edge)
- Requires support for:
  - fetch API
  - AbortController
  - Promise
  - FormData
  - Blob
- IE11 would require polyfills
- Mobile browsers fully supported

## Future Enhancements

### Advanced Features
- Automatic request retry with exponential backoff
- Request queuing and prioritization
- Offline request persistence and sync
- Request batching for related operations
- GraphQL adapter option
- WebSocket integration for real-time updates
- Request/response transformation pipelines
- Comprehensive request/response logging
- Performance monitoring and metrics
- Integration with service workers for offline caching

### Developer Experience
- Request/response logging in development
- cURL command generation for debugging
- Request tracing and timing
- Mock server integration for testing
- OpenAPI/Swagger client generation
- TypeScript definitions (if migrating to TS)