# Mindbase Backend - ollama.py

## Overview
Client for communicating with local Ollama instance. Handles all interactions with the Ollama API including model management, text generation, embeddings, and health checking.

## Responsibilities
- Connect to Ollama server running locally
- List available models
- Pull/download new models
- Generate text completions (both streaming and non-streaming)
- Generate text embeddings
- Check server health and model availability
- Manage current model selection

## Key Classes & Methods

### OllamaClient
Main class encapsulating all Ollama interactions.

#### Connection Management
- `__init__(host)`: Initialize client with Ollama host URL
- `check_health()`: Verify Ollama server is reachable and responsive

#### Model Management
- `list_models()`: Get list of all available models
- `pull_model(name)`: Download a model from Ollama library
- `get_model(name=None)`: Get current model or specified model, pulling if necessary
- `set_model(name)`: Switch to a different model for future requests

#### Text Generation
- `generate(model, messages, temperature=0.7)`: Generate non-streaming completion
- `stream_generate(model, messages, temperature=0.7)`: Generate streaming completion (yields chunks)
- Both methods accept message arrays in OpenAI format: `[{"role": "user|assistant|system", "content": "..."}]`

#### Embeddings
- `embed(model, text)`: Generate embedding vector for text input
- Used for memory storage and document processing

## Usage Patterns

### Text Generation
```python
# Non-streaming
response = await ollama_client.generate(
    model="mistral", 
    messages=[{"role": "user", "content": "Hello!"}],
    temperature=0.7
)

# Streaming
async for chunk in ollama_client.stream_generate(
    model="mistral",
    messages=[{"role": "user", "content": "Tell me a story"}],
    temperature=0.8
):
    print(chunk, end="", flush=True)
```

### Embeddings
```python
embedding = await ollama_client.embed("nomic-embed-text", "Text to embed")
# Returns list of floats representing the vector
```

### Model Management
```python
# Check if model is available, pull if not
model = await ollama_client.get_model("mistral")

# Switch models
await ollama_client.set_model("llamav2")
```

## Error Handling
- Raises `OllamaError` exception on API failures
- Connection errors handled gracefully with informative messages
- Streaming methods yield error markers in the stream rather than raising (to avoid breaking generators)
- All methods are async and should be awaited

## Initialization & Lifecycle
- Single instance created in module scope: `ollama_client = OllamaClient(host)`
- Shared instance used throughout application
- HTTP client properly closed on shutdown via lifespan event
- Background task created during startup to ensure embedding model is available

## Configuration
- Host URL loaded from `config.OLLAMA_HOST` (default: `http://localhost:11434`)
- Timeout values built into requests for reliability
- Uses HTTP keep-alive for efficient repeated requests

## Security
- Only communicates with locally configured Ollama instance
- No authentication required for local Ollama (by design)
- Sensitive data never sent to external services