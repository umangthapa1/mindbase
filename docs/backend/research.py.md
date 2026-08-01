# Mindbase Backend - research.py

## Overview
Offline research agent that performs multi-step research processes on local data and general knowledge (via LLM) to answer complex questions, generate reports, and synthesize information without requiring internet access.

## Responsibilities
- Conduct iterative research processes using local LLM
- Break down complex questions into sub-questions
- Generate research plans and execute them sequentially
- Synthesize findings from multiple sources into coherent reports
- Save research results as notes in the notebook system
- Provide progress updates via Server-Sent Events (SSE)
- Utilize tools like document search, memory retrieval, and logical reasoning
- Handle research workflow management and state tracking
- Allow saving and resumption of research sessions

## Key Classes & Methods

### ResearchAgent
Main class handling research operations.

#### Initialization
- `__init__()`: Sets up research agent with required dependencies
- Dependencies: Ollama client, memory manager, document manager

#### Main Research Function
- `research(query)`: 
  Main entry point - conducts research on given query
  Returns asynchronous generator yielding progress updates
  Research process: planning → execution → synthesis → reporting

#### Research Process Steps
1. **Planning Phase**: 
   - Analyze research query
   - Break into manageable sub-questions
   - Determine required tools and data sources
   - Create research plan with estimated steps

2. **Execution Phase**: 
   - Execute each step in plan
   - For each sub-question:
     * Gather context from memory, documents, and general knowledge
     * Use LLM to analyze and synthesize information
     * Record findings and sources
     * Determine if follow-up questions needed

3. **Synthesis Phase**: 
   - Combine findings from all steps
   - Identify patterns, contradictions, and insights
   - Create structured outline for final report
   - Ensure logical flow and completeness

4. **Reporting Phase**: 
   - Generate comprehensive report
   - Include executive summary, detailed findings, sources
   - Format for readability and actionability
   - Prepare for saving as note

#### Progress Reporting
- Yields dictionaries with update information:
  - `{"type": "planning", "step": "Analyzing query..."}`
  - `{"type": "executing", "step": 2, "total": 5, "message": "Researching sub-question..."}`
  - `{"type": "synthesizing", "message": "Combining findings..."}`
  - `{"type": "report", "report": {...}, "note_id": 123}`
  - `{"type": "complete"}`

#### Report Saving
- `save_report_to_note(report, db)`: 
  Save research report as a note in the notebook system
  Returns note ID for later retrieval
  Handles note creation with appropriate title and tags

#### Helper Methods
- `_safe_generate(prompt, temperature, timeout)`: 
  Wrapper for LLM generation with timeout protection
- `_extract_key_points(text)`: 
  Identify important facts and concepts from text
- `_assess_source_reliability(source)`: 
  Evaluate trustworthiness of information source
- `_format_citation(source)`: 
  Create proper citation for source attribution
- `_identify_research_gaps(findings)`: 
  Determine what information is still needed

## Research Workflow

### Input Processing
- Accepts natural language research query
- Examples: 
  - "What are the renewable energy trends in 2026?"
  - "Compare different machine learning approaches for NLP"
  - "Summarize the key findings of my documents about climate change"
  - "What should I know before starting a small business?"

### Planning Strategy
- Query decomposition techniques:
  - Factorial: Break into constituent aspects (who, what, when, where, why, how)
  - Comparative: Identify comparison points if applicable
  - Temporal: Consider historical, current, and future aspects
  - Stakeholder: Different perspectives if relevant
  - Hierarchical: Top-down breakdown of complex topics

### Source Utilization
Research agent can consult:
1. **Long-term Memory**: User's stored facts, preferences, experiences
2. **Document Collection**: User's uploaded documents and notes
3. **General Knowledge**: LLM's training knowledge (via Ollama)
4. **Logical Reasoning**: Deduction, inference, and synthesis capabilities
5. **Previous Research Findings**: Results from earlier steps in same research

### Quality Controls
- Source triangulation: Verify facts across multiple sources
- Uncertainty marking: Flag information with low confidence
- Bias detection: Identify potential LLM or training data biases
- Recency preference: Favor more recent information when relevant
- Specificity preference: Prefer concrete facts over vague statements

### Output Formats
Research reports include:
- Executive summary (2-3 sentences)
- Detailed findings organized by topic
- Supporting evidence and reasoning
- Limitations and open questions
- Actionable recommendations (when applicable)
- Proper citations and source attribution
- Visual structure with headings and bullet points

## Integration Points

### Called From
- `main.py`: In `/api/research` endpoint (SSE)
- `main.py`: In `/api/research/save` endpoint for saving reports
- Manual invocation for testing or background research

### Dependencies
- `ollama.py`: For LLM interactions (generation, planning, synthesis)
- `memory.py`: For accessing user's long-term knowledge
- `documents.py`: For searching user's document collection
- `database.py`: For saving research results as notes
- `intelligence.py`: Potentially for additional context gathering

### Related Modules
- Works with `documents.py` to analyze user-uploaded research material
- Saves results via `memory.py` notebook system
- Can be triggered from chat interface for deep dives
- Results can inform future conversations and task planning

## Special Features

### Iterative Deepening
- Can recursively research sub-questions
- Depth controlled by complexity assessment
- Prevents infinite recursion through depth limits and convergence detection
- Each level builds on findings from previous level

### Confidence Scoring
- Assigns confidence levels to findings (high/medium/low)
- Based on source agreement, specificity, and recency
- Reported in final output to inform user interpretation
- Guides where additional research might be needed

### Source Management
- Tracks all consulted sources during research
- Provides proper attribution in final report
- Distinguishes between user data, general knowledge, and reasoning
- Enables user to verify and explore sources further

### Progress Transparency
- Real-time updates via SSE keep user informed
- Shows current step, estimated progress, and activity
- Allows user to understand what the agent is doing
- Reduces perception of system being "stuck" during long research

### Adaptive Planning
- Research plan can evolve based on intermediate findings
- New sub-questions added if gaps discovered
- Unproductive paths abandoned early
- Focus shifts to promising areas as research progresses

## Research Techniques Employed

### Knowledge Synthesis
- Combine information from multiple sources
- Identify consensus and contradictions
- Extract principles from examples
- Apply analogies from known domains

### Gap Analysis
- Determine what information is missing to fully answer query
- Identify specific questions that need answers
- Prioritize gaps by importance to final answer

### Reasoning Methods
- Deductive: Apply general principles to specific cases
- Inductive: Generalize from specific observations
- Abductive: Infer best explanation from available facts
- Analogical: Apply knowledge from similar situations

### Information Filtering
- Relevance scoring: How pertinent is information to query?
- Credibility assessment: How trustworthy is the source?
- Redundancy elimination: Avoid repeating same information
- Novelty detection: Identify truly new insights

## Performance Considerations

### Time Management
- Research sessions can take from seconds to several minutes
- Progress updates prevent timeout perceptions
- Configurable time limits per research step (default: 60 seconds)
- Early termination if sufficient answer found quickly

### Resource Usage
- LLM calls: Primary resource consumer
- Memory/document searches: Secondary but important
- Context window management: Critical for coherent reasoning
- Embedding generation: For memory/document searches

### Optimization Strategies
- Parallel search: Check memory and documents simultaneously when possible
- Context pruning: Remove irrelevant information from prompts
- Prompt templating: Reuse effective prompt structures
- Result caching: Avoid re-processing same information

## Error Handling

### Research Failures
- Query too vague: Asks for clarification through intermediate steps
- No relevant information: Reports inability to find sufficient data
- Contradictory sources: Presents conflicting viewpoints with analysis
- LLM failure: Retries with exponential backoff, then reports error
- Timeout: Returns partial findings with warning

### Data Issues
- Corrupted memory: Continues with available data, logs warning
- Missing documents: Proceeds with other sources, notes absence
- Embedding failures: Skips affected chunks, continues search
- Database errors: Falls back to in-memory where possible

### User Experience
- Clear progress indicators prevent frustration
- Ability to save partial research if interrupted
- Transparent about limitations and uncertainties
- Option to continue research from saved point (future enhancement)

## Integration with AI Features

### Context Awareness
- Research considers user's personal knowledge from memory
- Results can be personalized based on user history
- Avoids re-researching what user already knows
- Builds upon existing user expertise

### Learning from Research
- Important findings can be automatically saved to long-term memory
- User can choose to save entire research report as note
- Research process improves agent's understanding of user interests
- Future research sessions can be more targeted

### Task Association
- Research can automatically suggest follow-up tasks
- Example: Research on "best hiking gear" might suggest task "Buy hiking boots"
- Tasks created include research citations for reference
- Connects knowledge acquisition to action items

## Usage Examples

### Simple Research
```
Query: "What are the health benefits of green tea?"
Process: 
1. Check memory for user's existing knowledge
2. Search documents for any user-uploaded tea research
3. Query LLM for general knowledge about green tea
4. Synthesize: antioxidants, metabolism, brain function
5. Report: Summary with bullet points and sources
```

### Complex Research
```
Query: "How should I invest my savings for retirement considering inflation?"
Process:
1. Break into: inflation basics, investment options, risk assessment, retirement planning
2. Research each sub-topic using available sources
3. Consider user's risk profile from memory (if available)
4. Synthesize: Create asset allocation strategy
5. Report: Detailed recommendations with considerations and disclaimers
```

### Document-Based Research
```
Query: "What are the main conclusions from my uploaded climate reports?"
Process:
1. List user's uploaded documents with "climate" or similar in name/tags
2. Extract text from relevant documents
3. Search within documents for conclusion sections
4. Identify common themes across reports
5. Report: Summary of findings with document citations
```