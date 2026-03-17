# Acadlo AI Core

> Standalone AI service providing intelligent search and conversational AI capabilities using Retrieval-Augmented Generation (RAG)

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- Docker (optional, for containerized deployment)

### Option 1: Run with Docker (Easiest) ⭐

```bash
# Build the image
docker build -t acadlo-ai-core:latest .

# Run the container
docker run -d \
  --name acadlo-ai-core \
  -p 8000:8000 \
  acadlo-ai-core:latest
```

**That's it!** Service will be available at `http://localhost:8000`

### Option 2: Run with docker-compose

**Important:** You need to set up environment variables first.

```bash
# 1. Set your OpenAI API key (required for embeddings)
export OPENAI_API_KEY=sk-proj-your-key-here

# 2. Start all services (PostgreSQL, Redis, API, Worker)
docker-compose up -d

# 3. Run database migrations
docker-compose exec acadlo-ai-core alembic upgrade head
```

### Option 3: Run Locally (Development)

```bash
# 1. Set up environment variables
export DATABASE_URL=postgresql+asyncpg://acadlo:acadlo_secret@localhost:5432/acadlo_ai
export REDIS_URL=redis://localhost:6379
export OPENAI_API_KEY=sk-proj-your-key-here

# 2. Start PostgreSQL and Redis (if using Docker)
docker-compose up -d postgres redis

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run database migrations
alembic upgrade head

# 5. Run the API service
python -m app.main

# 6. In a separate terminal, run the worker
python -m app.workers.run_worker
```

The service will start on `http://localhost:8000`

---

## ⚙️ Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for embeddings & LLM (required) | `sk-proj-...` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL_NAME` | `text-embedding-3-small` | OpenAI embedding model |
| `LLM_PROVIDER` | `openai` | LLM provider type (openai, selfhosted) |
| `LLM_DEFAULT_CHAT_MODEL` | `gpt-4o-mini` | Default LLM model for chat |
| `LLM_TEMPERATURE` | `0.7` | LLM temperature (0-2) |
| `LLM_MAX_TOKENS` | `1000` | Default max completion tokens |
| `CHUNK_SIZE` | `500` | Document chunk size in characters |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks in characters |
| `CHAT_HISTORY_MAX_TURNS` | `10` | Max conversation turns to include |
| `CHAT_HISTORY_MAX_CHARS_PER_MESSAGE` | `2000` | Max characters per history message |
| `HTTP_PORT` | `8000` | HTTP server port |
| `ENVIRONMENT` | `development` | Environment mode |

**Note:** Logs are automatically stored in `./logs` directory with 30-day retention. See [Logging & Observability](#logging--observability-us-ai-m3-e) section for details.

**Get your OpenAI API key:** https://platform.openai.com/api-keys

### LLM Provider Configuration

The system uses an abstraction layer for LLM (Large Language Model) calls, allowing you to swap providers easily:

**Current Implementation:**
- **OpenAI Provider**: Default implementation using OpenAI's Chat Completion API
- Uses the same API key as embeddings (`OPENAI_API_KEY`)
- Supports all OpenAI chat models (gpt-4o, gpt-4o-mini, gpt-3.5-turbo, etc.)

**Switching Models:**
```bash
# Use a different model per environment
export LLM_DEFAULT_CHAT_MODEL=gpt-4o          # Production (most capable)
export LLM_DEFAULT_CHAT_MODEL=gpt-4o-mini     # Dev/Stage (fast & cheap)
export LLM_DEFAULT_CHAT_MODEL=gpt-3.5-turbo   # Budget option
```

**Provider Architecture:**
- All LLM calls go through the `LLMProvider` abstraction
- No direct API calls in controllers or RAG logic
- Easy to add new providers by implementing the `LLMProvider` interface

---

## 📚 API Documentation

Once the service is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## 🎮 CLI Playground

A developer-friendly CLI tool to test all endpoints without needing a frontend.

```bash
# Interactive mode
python playground.py

# Full demo mode
python playground.py http://localhost:8000 --demo

# Or using Makefile
make playground
make playground-demo
```

The playground provides:
- Interactive menu for testing all endpoints
- Full demo showcasing all features
- Pretty-printed JSON responses
- Friendly result formatting


## 📖 End-to-End Example

Here's a complete example of ingesting a document and performing semantic search:

### Step 1: Ingest a Document

```bash
curl -X POST http://localhost:8000/v1/ingest/document \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "school_123",
    "externalId": "policy_transfer_001",
    "title": "Student Transfer Policy",
    "language": "en",
    "sourceType": "policy",
    "content": {
      "type": "text",
      "value": "Student Transfer Policy: All student transfers between schools must be approved by the principals of both the sending and receiving schools. The student must meet all academic requirements and have no outstanding disciplinary issues. Parents must submit the transfer request form at least 30 days before the desired transfer date. The receiving school will review the student'\''s academic records and conduct an interview before making a decision."
    },
    "visibility": {
      "roles": ["Teacher", "Admin"]
    },
    "tags": {
      "category": "admissions",
      "department": "registrar"
    }
  }'
```

**Response:**
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

### Step 2: Check Ingestion Status

```bash
curl "http://localhost:8000/v1/ingest/status?jobId=550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "tenantId": "school_123",
  "documentId": "660e8400-e29b-41d4-a716-446655440001",
  "externalId": "policy_transfer_001",
  "status": "completed",
  "errorMessage": null,
  "createdAt": "2025-12-07T10:00:00Z",
  "updatedAt": "2025-12-07T10:00:05Z"
}
```

### Step 3: Search for Related Content

```bash
curl -X POST http://localhost:8000/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "school_123",
    "userId": "teacher_456",
    "roles": ["Teacher"],
    "language": "en",
    "query": "How do I transfer a student to another school?",
    "filters": {
      "sourceType": ["policy"]
    },
    "topK": 5
  }'
```

**Response:**
```json
{
  "results": [
    {
      "chunkId": "770e8400-e29b-41d4-a716-446655440002",
      "documentId": "660e8400-e29b-41d4-a716-446655440001",
      "text": "Student Transfer Policy: All student transfers between schools must be approved by the principals of both the sending and receiving schools. The student must meet all academic requirements...",
      "score": 0.92,
      "title": "Student Transfer Policy",
      "tags": {
        "category": "admissions",
        "department": "registrar"
      }
    }
  ]
}
```

**What Happened:**
1. ✅ Document was ingested, chunked, and embedded (background processing)
2. ✅ Search query was embedded using the same model
3. ✅ Vector similarity search found the most relevant chunk
4. ✅ Results filtered by tenant and user roles
5. ✅ Score of 0.92 indicates high semantic similarity

### Step 4: Chat with RAG (Milestone 3-B)

Now use the `/v1/chat` endpoint to get a conversational answer based on the ingested knowledge:

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "school_123",
    "userId": "teacher_456",
    "roles": ["Teacher"],
    "language": "en",
    "message": "How do I transfer a student to another school?",
    "history": []
  }'
```

**Response:**
```json
{
  "sessionId": "sess_abc123def456",
  "answer": "To transfer a student to another school, you must follow these steps:\n\n1. Obtain approval from the principals of both the sending and receiving schools\n2. Ensure the student meets all academic requirements and has no outstanding disciplinary issues\n3. Submit the transfer request form at least 30 days before the desired transfer date\n4. The receiving school will review the student's academic records and conduct an interview before making a final decision\n\nBoth school principals must approve the transfer before it can proceed.",
  "language": "en",
  "citations": [
    {
      "documentId": "660e8400-e29b-41d4-a716-446655440001",
      "chunkId": "770e8400-e29b-41d4-a716-446655440002",
      "title": "Student Transfer Policy"
    }
  ],
  "meta": {
    "model": "gpt-4o-mini",
    "retrievedChunks": 5,
    "usedChunks": 1,
    "promptTokens": 450,
    "completionTokens": 95,
    "totalTokens": 545,
    "latencyMs": 1850
  }
}
```

**What Happened (RAG Pipeline):**
1. ✅ Query was converted to embedding
2. ✅ Top 5 relevant chunks retrieved via vector search
3. ✅ Selected 1 chunk for context (within token limits)
4. ✅ Built prompt with system instructions + context + question
5. ✅ LLM generated answer based ONLY on provided context
6. ✅ Citations provided for transparency
7. ✅ Metadata tracked for observability (tokens, latency, chunks used)

### Step 5: Multi-turn Conversation

Continue the conversation with history:

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "school_123",
    "userId": "teacher_456",
    "roles": ["Teacher"],
    "language": "en",
    "sessionId": "sess_abc123def456",
    "message": "What if the student has disciplinary issues?",
    "history": [
      {
        "role": "user",
        "content": "How do I transfer a student to another school?"
      },
      {
        "role": "assistant",
        "content": "To transfer a student to another school, you must follow these steps: 1. Obtain approval from the principals..."
      }
    ]
  }'
```

The system will understand "the student" refers to the student being transferred from the previous context.

---

## 🔄 Multi-Turn Conversations (Milestone 3-D)

The `/v1/chat` endpoint supports **stateless multi-turn conversations** by accepting conversation history in each request.

### How It Works

**Client Responsibility:**
- Client (frontend/app) manages conversation state
- For each turn, client sends complete history of previous turns
- API processes history + new question → returns answer
- Client appends new Q&A to history for next turn

**Server-Side Processing:**
- **Normalization**: Validates role and content of each history message
- **Limiting**: Keeps only last `CHAT_HISTORY_MAX_TURNS` (default: 10 messages = 5 Q&A pairs)
- **Truncation**: Individual messages limited to `CHAT_HISTORY_MAX_CHARS_PER_MESSAGE` (default: 2000 chars)
- **Integration**: History injected between system prompt and final user question

### Configuration

```bash
# Environment Variables
CHAT_HISTORY_MAX_TURNS=10           # Max history messages to include
CHAT_HISTORY_MAX_CHARS_PER_MESSAGE=2000  # Max chars per message
```

### Example: Building a Conversation

#### Turn 1: First Question (No History)

```json
{
  "tenantId": "school_123",
  "userId": "teacher_456",
  "roles": ["Teacher"],
  "language": "en",
  "message": "What is the attendance requirement?",
  "history": []
}
```

**Response:**
```json
{
  "sessionId": "sess_abc123",
  "answer": "Students must attend at least 90% of scheduled classes...",
  "language": "en",
  "citations": [...]
}
```

#### Turn 2: Follow-up (With History)

```json
{
  "tenantId": "school_123",
  "userId": "teacher_456",
  "roles": ["Teacher"],
  "language": "en",
  "sessionId": "sess_abc123",
  "message": "What happens if they miss too many classes?",
  "history": [
    {
      "role": "user",
      "content": "What is the attendance requirement?"
    },
    {
      "role": "assistant",
      "content": "Students must attend at least 90% of scheduled classes..."
    }
  ]
}
```

**Response:**
```json
{
  "sessionId": "sess_abc123",
  "answer": "If students miss too many classes and fall below 90% attendance, three unexcused absences will result in a parent-teacher conference...",
  "language": "en",
  "citations": [...]
}
```

#### Turn 3: Continue Conversation

```json
{
  "tenantId": "school_123",
  "userId": "teacher_456",
  "roles": ["Teacher"],
  "language": "en",
  "sessionId": "sess_abc123",
  "message": "And what about medical absences?",
  "history": [
    {
      "role": "user",
      "content": "What is the attendance requirement?"
    },
    {
      "role": "assistant",
      "content": "Students must attend at least 90% of scheduled classes..."
    },
    {
      "role": "user",
      "content": "What happens if they miss too many classes?"
    },
    {
      "role": "assistant",
      "content": "If students miss too many classes and fall below 90% attendance, three unexcused absences will result in a parent-teacher conference..."
    }
  ]
}
```

### Best Practices

**For Client Developers:**
1. ✅ **Always append** new Q&A pair to history after each turn
2. ✅ **Use same sessionId** across all turns in a conversation
3. ✅ **Store history** in client state (React state, Vuex, etc.)
4. ✅ **Handle errors** - if request fails, don't add to history
5. ✅ **Let server limit** - send full history, server will truncate if needed
6. ⚠️ **Don't truncate manually** - server handles limits automatically
7. ⚠️ **New conversation?** - Start with empty `history: []` and new/no sessionId

**Example Client Pattern (React):**
```javascript
const [history, setHistory] = useState([]);
const [sessionId, setSessionId] = useState(null);

async function sendMessage(userMessage) {
  const response = await fetch('/v1/chat', {
    method: 'POST',
    body: JSON.stringify({
      tenantId: 'school_123',
      userId: 'teacher_456',
      roles: ['Teacher'],
      language: 'en',
      sessionId: sessionId,
      message: userMessage,
      history: history
    })
  });
  
  const data = await response.json();
  
  // Update session ID
  if (!sessionId) setSessionId(data.sessionId);
  
  // Append to history
  setHistory([
    ...history,
    { role: 'user', content: userMessage },
    { role: 'assistant', content: data.answer }
  ]);
  
  return data;
}
```

### History Limits & Behavior

| Scenario | Behavior |
|----------|----------|
| History empty | Chat works as single-turn Q&A |
| History < 10 messages | All history included in prompt |
| History > 10 messages | Only last 10 messages used (oldest dropped) |
| Message > 2000 chars | Truncated to 2000 chars + "..." |
| Invalid role | Message skipped with warning in logs |
| Non-string content | Message skipped with warning in logs |

---

## 🛡️ Guardrails & Safety (Milestone 3-C)

The `/v1/chat` endpoint implements several guardrails to ensure safe, reliable, and accurate responses:

### Context-Only Answers

The AI is instructed to **strictly base answers on the provided context** and will:
- ✅ Never invent or guess information about policies, procedures, or rules
- ✅ Explicitly state when information is insufficient
- ✅ Acknowledge uncertainties rather than filling gaps with assumptions
- ✅ Point out contradictions in source materials

### "No Knowledge" Behavior

When the search returns **zero relevant chunks**, the system:
- ❌ **Skips the LLM call entirely** (cost savings + safety)
- ✅ Returns a standard "no knowledge" message
- ✅ Sets `retrievedChunks = 0`, `usedChunks = 0`
- ✅ Prevents hallucinations on topics outside the knowledge base

**Example:**
```json
{
  "answer": "I couldn't find any relevant information in the current knowledge base to answer your question.",
  "citations": [],
  "meta": {
    "retrievedChunks": 0,
    "usedChunks": 0,
    "model": null,
    "totalTokens": null
  }
}
```

### Context Limits

To balance answer quality with latency and cost:
- **Retrieval**: Up to `CHAT_CONTEXT_TOP_K` (default: 8) chunks from vector search
- **Selection**: Up to `CHAT_CONTEXT_MAX_CHUNKS` (default: 6) chunks included in prompt
- **Character Limit**: Maximum `CHAT_CONTEXT_MAX_CHARS` (default: 6000 ~1500 tokens)
- **Generation**: Maximum `LLM_MAX_TOKENS` (default: 1000) for completion

Chunks are automatically truncated if they exceed limits.

### Language Control

- If `language` is provided in the request, the AI answers in that language
- If missing, defaults to `DEFAULT_LANGUAGE` (default: "en")
- Cross-language support: Arabic context → English answer, and vice versa
- Response includes actual language used

### Error Handling

Proper HTTP status codes for different error scenarios:

| Status | Scenario | Response |
|--------|----------|----------|
| `200` | Success | ChatResponse with answer and citations |
| `400` | Validation error | Missing tenantId or message |
| `502` | LLM provider failure | AI service unavailable (network, API errors) |
| `500` | Internal error | Database or unexpected errors |

**Example Error Response:**
```json
{
  "errorCode": "LLM_PROVIDER_ERROR",
  "message": "Failed to generate response from AI provider. Please try again.",
  "details": {
    "provider": "openai"
  }
}
```

### Logging & Observability (US-AI-M3-E)

The system implements **structured JSON logging** with date-based rotation for comprehensive observability, debugging, and cost tracking.

#### Log Location & Structure

Logs are stored in the `./logs` directory (mounted from Docker containers):

```
logs/
├── chat/
│   ├── chat.2026-01-01.log      # All /v1/chat activity for Jan 1
│   ├── chat.2026-01-02.log      # Jan 2
│   └── chat.2026-01-03.log
├── ingestion/
│   ├── ingestion.2026-01-01.log # All ingestion jobs
│   └── ingestion.2026-01-02.log
├── errors/
│   ├── errors.2026-01-01.log    # Critical errors only
│   └── errors.2026-01-02.log
└── app.log                       # General application logs (rolling)
```

#### Accessing Logs

**On Windows:**
```powershell
# View today's chat logs
notepad logs\chat\chat.2026-01-01.log

# View day before yesterday's logs
notepad logs\chat\chat.2025-12-30.log

# List all available logs
dir logs\chat\
```

**On Linux/Mac:**
```bash
# View logs
cat logs/chat/chat.2026-01-01.log

# Tail live logs
tail -f logs/chat/chat.2026-01-01.log

# Search for specific tenant
grep "tenant-123" logs/chat/chat.2025-12-30.log
```

#### What's Logged

For every `/v1/chat` request, the system logs structured metadata:

```json
{
  "timestamp": "2026-01-01T10:30:45.123Z",
  "level": "INFO",
  "logger": "chat_service",
  "endpoint": "/v1/chat",
  "tenantId": "tenant-123",
  "userId": "user-456",
  "scenario": "support",
  "historyTurns": 2,
  "language": "en",
  "languageDefaulted": false,
  "retrievedChunks": 5,
  "usedChunks": 3,
  "model": "gpt-4o-mini",
  "llmLatencyMs": 1234.56,
  "totalLatencyMs": 1500.23,
  "promptTokens": 450,
  "completionTokens": 150,
  "totalTokens": 600,
  "noKnowledge": false,
  "httpStatus": 200,
  "traceId": "a5d4095e-c720-4291-8e16-e4ccc7d468e8"
}
```

**Error Logging:**

When errors occur, detailed error logs are created:

```json
{
  "timestamp": "2026-01-01T10:30:45.123Z",
  "level": "ERROR",
  "logger": "error",
  "errorType": "llm_failure",
  "errorMessage": "LLM provider failed to generate response",
  "tenantId": "tenant-123",
  "userId": "user-456",
  "scenario": "support",
  "traceId": "abc-123",
  "exceptionType": "LLMProviderError",
  "exceptionDetails": "Connection timeout",
  "stackTrace": "..."
}
```

#### Privacy & Security

The system logs **metadata only** and **never logs**:
- ❌ Full user messages (only first 100 chars in debug logs)
- ❌ Full AI responses (only first 100 chars in debug logs)
- ❌ Conversation history content
- ❌ Retrieved chunk texts
- ❌ Sensitive user data

Logs include **only**:
- ✅ Metadata (tenantId, userId, scenario, language)
- ✅ Metrics (chunk counts, token usage, latency)
- ✅ Error types and codes
- ✅ Performance data
- ✅ Trace IDs for request tracking

#### Log Retention

- **Rotation**: New log file created daily at midnight
- **Retention**: Last 30 days (configurable)
- **Cleanup**: Automatic deletion of old logs
- **Storage**: ~5MB per 10,000 chat requests/day (~150MB for 30 days)

#### Use Cases

| Scenario | How to Handle |
|----------|---------------|
| Debug slow requests | Open `logs/chat/chat.YYYY-MM-DD.log`, search for high `totalLatencyMs` |
| Track token usage per tenant | `grep "tenant-123" logs/chat/*.log \| jq .totalTokens` |
| Find errors from yesterday | Open `logs/errors/errors.2025-12-31.log` |
| Monitor "no knowledge" events | Search for `"noKnowledge": true` in chat logs |
| Export logs for analysis | Copy entire `logs/` folder or specific log files |
| Trace a specific request | Use the `traceId` returned in error responses |

---

## 🔌 API Endpoints

### Health & System

#### GET `/health`

Check if the service is running.

**Example:**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "acadlo-ai-core",
  "version": "0.1.0"
}
```

#### POST `/echo`

Echo back any JSON payload (for testing).

**Example:**
```bash
curl -X POST http://localhost:8000/echo \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "message": "Hello, World!",
      "timestamp": "2025-11-22T10:00:00Z"
    }
  }'
```

**Response:**
```json
{
  "echo": {
    "message": "Hello, World!",
    "timestamp": "2025-11-22T10:00:00Z"
  }
}
```

---

### Document Ingestion

#### POST `/v1/ingest/document`

Submit a document for ingestion and processing.

**Example:**
```bash
curl -X POST http://localhost:8000/v1/ingest/document \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "t_abc",
    "externalId": "Policy:42",
    "title": "Transfer Policy",
    "language": "ar-JO",
    "sourceType": "policy",
    "visibility": {
      "roles": ["Principal", "Admin"],
      "scopes": ["School:123"]
    },
    "tags": {
      "stage": "Primary",
      "year": "2025"
    },
    "content": {
      "type": "text",
      "value": "Full text content of the transfer policy document..."
    },
    "metadata": {
      "uploadedBy": "u_999",
      "sourceName": "policy-2025.pdf"
    }
  }'
```

**Response (202 Accepted):**
```json
{
  "jobId": "job_abc123",
  "status": "pending"
}
```

#### GET `/v1/ingest/status`

Check the status of an ingestion job.

**Example:**
```bash
curl "http://localhost:8000/v1/ingest/status?jobId=job_abc123"
```

**Response:**
```json
{
  "jobId": "job_abc123",
  "tenantId": "t_abc",
  "documentId": "doc_xyz789",
  "externalId": "Policy:42",
  "status": "completed",
  "errorMessage": null,
  "createdAt": "2025-11-22T10:00:00Z",
  "updatedAt": "2025-11-22T10:00:05Z"
}
```

**Note:** You can also fetch documents by `externalId` in future versions. The `externalId` is stored and indexed for quick lookups.

---

### Search

#### POST `/v1/search`

Perform semantic vector search across ingested documents using pgvector similarity.

**How it works:**
1. Generates embedding for the query using OpenAI
2. Performs vector similarity search (cosine distance)
3. Applies multi-tenant isolation
4. Applies role-based visibility filtering
5. Returns top-K most similar chunks with scores

**Example:**
```bash
curl -X POST http://localhost:8000/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "t_abc",
    "userId": "u_999",
    "roles": ["Teacher"],
    "language": "en",
    "query": "what is the policy for student transfers?",
    "filters": {
      "sourceType": ["policy"],
      "tags": {"stage": "Primary", "year": "2024"}
    },
    "topK": 8
  }'
```

**Response:**
```json
{
  "results": [
    {
      "chunkId": "chunk_987",
      "documentId": "doc_123",
      "text": "The policy for student transfers requires approval from both the sending and receiving school principals. Students must meet academic requirements...",
      "score": 0.89,
      "title": "Transfer Policy",
      "tags": {
        "sourceType": "policy",
        "stage": "Primary"
      }
    }
  ]
}
```

**Key Features:**
- ✅ **Multi-tenant isolation**: Only searches within your tenant's data
- ✅ **Role-based filtering**: Respects visibility roles
- ✅ **Semantic search**: Finds conceptually similar content, not just keywords
- ✅ **Ranked results**: Ordered by similarity score (0-1, higher is better)
- ✅ **Optional filters**: Filter by sourceType, subject, grade, and tags (case-insensitive, must match all key-value pairs)

**Notes:**
- `tenantId` is **required** (HTTP 400 if missing)
- Empty query returns empty results (not an error)
- `visibility_scopes` filtering is not yet implemented (reserved for future)

---

### Chat

#### POST `/v1/chat`

Send a message to the AI assistant for conversational RAG.

**Example:**
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "t_abc",
    "userId": "u_999",
    "roles": ["Owner"],
    "language": "ar-JO",
    "scenario": "generic",
    "sessionId": "sess_123",
    "message": "How do I transfer a student?",
    "history": [
      {
        "role": "user",
        "content": "Tell me about school policies"
      },
      {
        "role": "assistant",
        "content": "Our school has several important policies..."
      }
    ],
    "uiContext": {
      "page": "policy-center"
    }
  }'
```

**Response:**
```json
{
  "sessionId": "sess_123",
  "answer": "لنقل الطالب من صف إلى آخر، يجب اتباع الخطوات التالية...",
  "language": "ar-JO",
  "citations": [
    {
      "documentId": "doc_123",
      "chunkId": "chunk_987",
      "title": "Student Transfer Policy"
    }
  ],
  "meta": {
    "intent": "Policy_QA",
    "tokens": 1234,
    "latencyMs": 2300
  }
}
```

**Milestone 1 Note:** Currently returns echo responses. Real LLM integration coming in future milestones.

---

## 🗂️ Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py              # Health & echo endpoints
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── ingestion.py       # Document ingestion endpoints
│   │       ├── search.py          # Search endpoint
│   │       └── chat.py            # Chat endpoint
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Application configuration
│   │   └── exceptions.py          # Custom exceptions
│   ├── middlewares/
│   │   ├── __init__.py
│   │   └── exception_middleware.py # Error handling
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py             # Pydantic models for all requests/responses
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── in_memory_store.py     # In-memory storage (Milestone 1)
│   └── services/
│       ├── __init__.py
│       ├── ingestion_service.py   # Ingestion business logic
│       ├── search_service.py      # Search business logic
│       └── chat_service.py        # Chat business logic
├── playground.py                   # CLI testing tool
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Docker image definition
├── docker-compose.yml              # Docker Compose configuration
├── Makefile                        # Development commands
├── .env.example                    # Environment variables template
└── README.md                       # This file
```

---

## ⚙️ Configuration

Configuration is managed through environment variables. Copy `.env.example` to `.env` and customize:

```bash
# Service Configuration
SERVICE_NAME=acadlo-ai-core
SERVICE_VERSION=0.1.0
HTTP_PORT=8000
ENVIRONMENT=development

# Database (unused in Milestone 1)
DATABASE_URL=postgresql://user:password@localhost:5432/acadlo_ai

# AI Model Provider (unused in Milestone 1)
MODEL_PROVIDER_API_KEY=your-api-key-here
MODEL_PROVIDER=openai

# CORS
CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]
```

---

## 🧪 Testing Examples

### Quick Health Check

```bash
make test-health
```

### Quick Echo Test

```bash
make test-echo
```

### Full Workflow Test

```bash
# 1. Start the service
make dev

# 2. In another terminal, run the playground
make playground

# 3. Choose option 6 for full demo
```

### Using curl for Complete Workflow

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. Ingest a document
curl -X POST http://localhost:8000/v1/ingest/document \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "t_test",
    "externalId": "TEST:001",
    "title": "Test Policy",
    "language": "en-US",
    "sourceType": "policy",
    "visibility": {"roles": ["Admin"], "scopes": ["School:1"]},
    "tags": {"test": "true"},
    "content": {"type": "text", "value": "This is a test document."},
    "metadata": {"uploadedBy": "u_test"}
  }'

# Save the jobId from response, then:

# 3. Check status
curl "http://localhost:8000/v1/ingest/status?jobId=JOB_ID_HERE"

# 4. Search
curl -X POST http://localhost:8000/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "t_test",
    "userId": "u_test",
    "roles": ["Admin"],
    "language": "en-US",
    "query": "test policy",
    "topK": 5
  }'

# 5. Chat
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "t_test",
    "userId": "u_test",
    "roles": ["Admin"],
    "language": "en-US",
    "message": "Tell me about the test policy",
    "history": []
  }'
```

---

## 🐳 Docker Commands

```bash
# Build image
docker build -t acadlo-ai-core:latest .

# Run container
docker run -d --name acadlo-ai-core -p 8000:8000 acadlo-ai-core:latest

# View logs
docker logs -f acadlo-ai-core

# Stop container
docker stop acadlo-ai-core
docker rm acadlo-ai-core

# Using docker-compose
docker-compose up -d      # Start
docker-compose down       # Stop
```

---

## 📊 API Contract Highlights

### Key Features

1. **Multi-tenancy**: Every request includes `tenantId` for complete data isolation
2. **Role-based Access**: Documents have visibility rules with `roles` and `scopes`
3. **External ID Support**: Documents can have `externalId` for integration with ABP or other systems
4. **Language Support**: Arabic (`ar-JO`) and English (`en-US`) throughout
5. **Job Tracking**: Async ingestion with job status polling
6. **Structured Errors**: Consistent `ErrorResponse` format across all endpoints

### Common Types

All endpoints use consistent data structures:

- **Visibility**: `{ "roles": [...], "scopes": [...] }`
- **ErrorResponse**: `{ "errorCode": "...", "message": "...", "details": {...}, "traceId": "..." }`
- **Content**: `{ "type": "text|url", "value": "..." }`

---

## 🔧 Development

### Adding New Endpoints

1. Create/update schema in `app/models/schemas.py`
2. Create service in `app/services/`
3. Create router in `app/api/v1/`
4. Register router in `app/main.py`

---

## 📝 Error Handling

All errors follow a consistent format:

```json
{
  "errorCode": "VALIDATION_ERROR",
  "message": "Human readable error message",
  "details": {
    "fieldErrors": {
      "fieldName": "error description"
    }
  },
  "traceId": "unique-trace-id"
}
```
