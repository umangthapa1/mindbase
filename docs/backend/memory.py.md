# Mindbase Backend - memory.py

## Overview
Long-term memory management module using ChromaDB for vector storage. Handles memory creation, storage, retrieval, search, and synchronization with notes and other entities.

## Responsibilities
- Store and retrieve long-term memories using vector embeddings
- Manage ChromaDB client and collection lifecycle
- Provide memory search functionality with similarity scoring
- Synchronize memories with notes, conversations, and other entities
- Extract and store memories from chat conversations automatically
- Handle memory metadata including tags, types, and timestamps
- Provide memory persistence across application restarts

## Key Classes & Methods

### MemoryManager
Main class handling all memory operations.

#### Initialization
- `__init__()`: Sets up ChromaDB client and collection
- Collection name: "memories"
- Persistent storage in `data/chroma/`

#### Memory Operations
- `create_memory(content, type, tags)`: Store new memory with embedding
- `get_all_memories()`: Retrieve all memories (with pagination support)
- `get_memories_by_type(type)`: Filter memories by type
- `search_memories(query, type, limit)`: Vector similarity search
- `update_memory(memory_id, content, tags, metadata)`: Modify existing memory
- `delete_memory(memory_id)`: Remove memory from storage

#### Memory Extraction
- `auto_extract_memory_from_chat(conversation_id, recent_messages)`: 
  Automatically identify and store important information from conversations
- Uses heuristics to determine what constitutes "memorable" information
- Extracts entities, facts, preferences, and procedures from chat

#### Synchronization Functions
- `upsert_note_memory(note_id, title, content, tags)`: 
  Create or update memory from note (called when notes change)
- `delete_note_memory(note_id)`: Remove note-associated memory
- Similar functions for other entity types as needed

#### Utility Methods
- `_get_embedding(text)`: Generate vector embedding for text
- `_prepare_metadata(...)`: Format metadata for ChromaDB storage
- `_parse_chroma_result(...)`: Convert ChromaDB results to application format

## Data Structure

### Memory Format
Each memory consists of:
- `id`: Unique identifier (UUID)
- `content`: The actual memory text
- `type`: Category (e.g., "preference", "fact", "procedure", "personal")
- `tags`: List of string tags for categorization
- `metadata`: Additional JSON-serializable data
- `created_at`: Timestamp
- `updated_at`: Timestamp for updates

### Storage Details
- **Vector Store**: ChromaDB collection named "memories"
- **Embedding Model**: Uses `nomic-embed-text` via Ollama for vector generation
- **Persistence**: Data stored in `data/chroma/` directory
- **Metadata**: Stored alongside vectors in ChromaDB for filtering

## Usage Patterns

### Storing Memories
```python
# Store a user preference
memory = await memory_manager.create_memory(
    content="User prefers dark mode interfaces",
    type="preference",
    tags=["ui", "preference", "display"]
)

# Store a fact learned from conversation
memory = await memory_manager.create_memory(
    content="User's cat is named Whiskers and is a Siamese breed",
    type="fact",
    tags=["personal", "pet", "cat"]
)
```

### Searching Memories
```python
# Search for memories about user preferences
memories = await memory_manager.search_memories(
    query="interface preferences",
    type="preference",
    limit=5
)

# Get all memories of a specific type
facts = await memory_manager.get_memories_by_type("fact")
```

### Automatic Extraction
Called automatically from chat endpoint:
```python
# After each conversation turn, extract memorable information
await memory_manager.auto_extract_memory_from_chat(
    conversation_id="conv_123",
    recent_messages=[
        {"role": "user", "content": "I hate when websites use tiny fonts"},
        {"role": "assistant", "content": "I understand that small text can be frustrating..."}
    ]
)
# Might create a memory: "User dislikes small font sizes on websites"
```

## Integration Points

### Called From
- `main.py`: In chat endpoint for auto-extraction after responses
- `main.py`: In note endpoints for synchronizing notes with memories
- Other services that want to store long-term information

### Dependencies
- `ollama.py`: For generating text embeddings (`nomic-embed-text` model)
- `database.py`: For accessing conversation history during extraction
- `config.py`: For path constants (though chroma path is hardcoded to `data/chroma/`)

### Related Modules
- Works closely with `documents.py` for document-based memories
- `notes.py`: Bidirectional synchronization (notes → memories)
- `tasks_service.py`: Optional synchronization for important tasks

## Special Features

### Memory Types
Predefined types help organize memories:
- `fact`: Objective information
- `preference`: User likes/dislikes
- `procedure`: How-to knowledge
- `personal`: Personal information about user
- `work`: Job-related information
- `idea`: Creative concepts or plans
- Custom types can be used as needed

### Tagging System
- Flexible tagging for additional categorization
- Tags stored as list of strings
- Used for filtering and organization
- Can be modified during memory updates

### Similarity Search
- Uses cosine similarity on vector embeddings
- Returns memories most semantically similar to query
- Configurable result count (default: 10)
- Combined with type filtering when specified

### Automatic Extraction Heuristics
The auto-extraction looks for:
- Expressed preferences ("I like/dislike...")
- Personal facts ("My name is...", "I have...")
- Repeated topics or entities
- Action items or commitments
- Emotional reactions to specific topics
- Information likely to be useful in future conversations

## Persistence & Storage

### Storage Location
- Primary: `data/chroma/` directory (ChromaDB persistent storage)
- Falls back to in-memory if directory unavailable (with warning)
- Directory created automatically on initialization

### Backup & Portability
- ChromaDB data can be backed up by copying the `data/chroma/` directory
- Compatible across ChromaDB versions with same embedding model
- Embedding model must be available (`nomic-embed-text` via Ollama)

### Performance
- Vector operations handled efficiently by ChromaDB
- Search results typically returned in milliseconds
- Memory creation involves embedding generation (slower, ~100-500ms)
- Concurrent access handled safely by ChromaDB

## Error Handling
- ChromaDB connection errors logged but don't crash application
- Fallback to disabled memory functionality if ChromaDB unavailable
- Individual operation failures return None or empty results with logging
- Embedding generation failures fall back to text-only storage (with warning)

## Security & Privacy
- All memory data stored locally on user's machine
- No external transmission of memory content
- Embedding generation happens locally via Ollama
- User can clear all memories through application interface
- Memory data included in application backups if user chooses