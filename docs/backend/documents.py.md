# Mindbase Backend - documents.py

## Overview
Document processing and Q&A system that handles file uploads, text extraction, chunking, embedding generation, vector storage, and question answering using local LLMs.

## Responsibilities
- Accept and process various file formats (PDF, TXT, MD, etc.)
- Extract text content from uploaded documents
- Split documents into semantically meaningful chunks
- Generate vector embeddings for each chunk using local Ollama model
- Store document chunks and embeddings in ChromaDB for similarity search
- Provide question-answering capabilities over processed documents
- Generate document summaries using LLM
- Manage document lifecycle (upload, list, delete)
- Synchronize document content with memory system when appropriate

## Key Classes & Methods

### DocumentManager
Main class handling all document operations.

#### Initialization
- `__init__()`: Sets up ChromaDB collections for documents
- Collections: "documents" (for chunks), optionally others for metadata
- Persistent storage in `data/chroma/` alongside memories

#### Document Lifecycle
- `upload_document(filename, content)`: 
  Main entry point - processes file, extracts text, chunks, embeds, stores
  Returns document metadata including ID and chunk count
- `list_documents()`: Get metadata for all uploaded documents
- `get_document(document_id)`: Get specific document details
- `delete_document(document_id)`: Remove document and all associated chunks

#### Processing Pipeline
- `_extract_text(filename, content)`: 
  Extract text based on file extension (PDF->PyPDF2, TXT/MD->direct)
- `_chunk_text(text)`: 
  Split text into overlapping chunks (default: 500 chars with 50 overlap)
  Respects paragraph and sentence boundaries when possible
- `_embed_chunks(chunks)`: 
  Generate embeddings for all chunks using nomic-embed-text
- `_store_document_chunks(document_id, chunks, embeddings)`: 
  Store in ChromaDB with metadata

#### Query Operations
- `ask_document(query, document_id)`:
  Search for relevant chunks, construct context, query LLM for answer
  Returns answer with source citations
- `summarize_document(document_id)`:
  Generate summary using map-reduce or stuff approach based on length
  Returns concise summary of document content

#### Helper Methods
- `_get_embedding(text)`: Generate single embedding via Ollama
- `_search_relevant_chunks(query, document_id, limit)`: 
  Vector search for chunks relevant to query
- `_build_qa_prompt(query, context_chunks)`: 
  Construct prompt for document Q&A
- `_build_summary_prompt(chunks)`: 
  Construct prompt for summarization

## Supported File Formats
- **Text**: `.txt`, `.md`, `.py`, `.js`, `.html`, `.css`, `.json`, `.csv`
- **PDF**: `.pdf` (requires PyPDF2 or similar)
- **Future**: Potential for DOCX, PPTX, etc. with additional dependencies

## Data Structure

### Document Metadata
Each document stores:
- `id`: Unique identifier (UUID)
- `filename`: Original filename
- `upload_timestamp`: When document was added
- `chunk_count`: Number of text chunks created
- `processing_status`: Success/error status
- `file_size`: Size in bytes

### Chunk Storage
Each chunk stored in ChromaDB includes:
- `id`: Unique chunk identifier
- `document_id`: Parent document reference
- `content`: The text chunk
- `chunk_index`: Position within document
- `embedding`: Vector representation (stored implicitly in ChromaDB)
- `metadata`: 
  - `filename`: Source document name
  - `chunk_index`: Sequential index
  - `upload_timestamp`: When processed
  - `page_number`: For paginated formats (PDF)

## Usage Patterns

### Uploading Documents
```python
# Process an uploaded file
result = await document_manager.upload_document(
    filename="research_paper.pdf",
    content=file_bytes
)
# Returns: {"id": "doc_123", "filename": "research_paper.pdf", 
#          "chunk_count": 42, "status": "processed"}
```

### Querying Documents
```python
# Ask a question about a specific document
answer = await document_manager.ask_document(
    document_id="doc_123",
    query="What is the main hypothesis of this paper?"
)
# Returns: {"answer": "...", "sources": [{"chunk": "...", "score": 0.85}]}

# Get document summary
summary = await document_manager.summarize_document(document_id="doc_123")
# Returns: {"summary": "Concise summary of the document..."}
```

### Listing Documents
```python
docs = await document_manager.list_documents()
# Returns: {"documents": [{"id": "...", "filename": "...", ...}], "count": N}
```

## Integration Points

### Called From
- `main.py`: In document endpoints (`/api/documents/*`)
- Other services that need document processing capabilities

### Dependencies
- `ollama.py`: For text generation (Q&A, summarization) and embeddings
- `memory.py`: Optional synchronization of document insights to long-term memory
- `database.py`: For storing document metadata (though primary metadata in ChromaDB)
- External libraries: PyPDF2 for PDF processing, potentially others

### Related Modules
- Works with `intelligence.py` to provide document context in chats
- Can synchronize important document facts to `memory.py`
- Used by `research.py` for source material

## Processing Pipeline

### 1. Upload & Validation
- Receive file via FastAPI UploadFile
- Validate file type and size
- Generate document ID
- Store original in `uploads/` directory (gitignored)

### 2. Text Extraction
- **PDF**: Use PyPDF2 to extract text page-by-page
- **Text/Markup**: Direct decoding (UTF-8 assumed)
- **Code**: Treat as plain text, preserve syntax
- **Fallback**: Binary files rejected or treated as unknown format

### 3. Chunking Strategy
- Split text into chunks of target size (default 500 characters)
- Include overlap (default 50 characters) to preserve context
- Attempt to break on paragraph boundaries (\n\n)
- Fall back to sentence boundaries (. ! ?)
- Last resort: break on word boundaries
- Track chunk index for reassembly/citation

### 4. Embedding Generation
- Use `nomic-embed-text` model via Ollama
- Generate embedding for each chunk
- Batch processing for efficiency when possible
- Handle embedding failures gracefully (skip chunk with warning)

### 5. Vector Storage
- Store each chunk in ChromaDB "documents" collection
- Metadata includes source document and position
- Enables efficient similarity search later
- Persistent across application restarts

### 6. Query Processing
- For questions: embed query, search top-K similar chunks
- Construct prompt with retrieved chunks as context
- Query LLM for answer based on context
- Provide citations showing which chunks contributed
- For summaries: map-reduce or stuff approach based on total length

## Special Features

### Overlapping Chunks
- Improves retrieval accuracy by preserving context
- Prevents splitting sentences or phrases across chunks
- Overlap size configurable (default 10% of chunk size)

### Metadata Preservation
- Source filename tracked with each chunk
- Chunk position enables recombination if needed
- Upload timestamp allows for sorting and filtering
- Page numbers preserved for PDF documents

### Error Resilience
- Partial processing: if some chunks fail, document still usable
- Failed embeddings logged but don't halt processing
- Corrupted files handled gracefully with informative errors
- Storage failures trigger cleanup of partial uploads

### Memory Integration
- Optional automatic extraction of key facts from documents
- Similar to chat extraction but for document content
- Configurable sensitivity to avoid memory overload
- Tags documents with source filename for traceability

## Performance Considerations

### Processing Time
- Text extraction: Fast for text files, slower for PDFs (~1-2 sec/page)
- Chunking: Linear with document size
- Embedding generation: Bottleneck (~100-300ms per chunk)
- Typical 10-page PDF: 10-30 seconds processing
- Caching: Re-processing same file uses cached embeddings if unchanged

### Storage Efficiency
- ChromaDB optimized for vector storage
- Metadata overhead minimal
- Uploads directory stores originals (can be cleaned separately)
- ChromaDB data persists across restarts

### Query Speed
- Vector search: Typically <500ms for relevant chunks
- Context construction: Linear with chunk count
- LLM query: Depends on model and context size (main delay)
- Caching: Frequent queries benefit from OS file caching

## Error Handling

### Upload Errors
- Invalid file type: Clear error message
- Empty file: Rejected with explanation
- Storage failure: Cleanup of partial uploads
- Processing failure: Document marked as error state

### Query Errors
- Document not found: 404 error
- Processing failed: Indicates document unusable
- No relevant chunks: Returns "I couldn't find relevant information"
- LLM failure: Fallback to extractive summary or error message

### Dependency Errors
- Missing Ollama: Graceful degradation with clear messages
- Embedding model missing: Auto-trigger pull attempt
- ChromaDB failure: Fallback to disabled document features

## Security & Privacy
- All processing occurs locally on user's machine
- No document content sent to external services
- Embedding generation via local Ollama instance
- Original files stored in `uploads/` (gitignored by default)
- User controls document retention through delete operations
- Documents can be removed completely from system