# Spec Implementation Review: Acadio AI Core

This document reviews the implementation against the specification documents, one document at a time.

---

## Document 1: Acadio Doc 1.docx (US-AI-API#1, US-AI-SKELETON#2, US-AI-INGESTION#3, US-AI-SEARCH-CHAT#4)

### What You're Building (Doc 1 Overview)

**Acadlo AI Core** is a standalone AI service that provides:
- **Knowledge ingestion** – Upload documents (policies, guides, curriculum) for RAG
- **Semantic search** – Find relevant chunks across ingested documents using vector similarity
- **Conversational AI (Chat)** – Ask questions and get contextual answers with citations
- **Multi-tenant isolation** – Complete data isolation per tenant (MOE, school, etc.)
- **Role-based visibility** – Control who sees which content (Teacher, Principal, Parent, etc.)

The service is designed to integrate with ABP/Nuxt or other frontends via stable JSON APIs.

---

### US-AI-API#1 – Core API Contracts

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| Versioned API spec (OpenAPI/Swagger or Markdown) | ⚠️ Partial | FastAPI auto-generates OpenAPI at `/docs`, `/openapi.json`. No committed `/docs/ai-core-api.md` or `/api/ai-core-openapi.yaml` as specified. |
| Document JSON schema | ✅ | `DocumentIngestRequest` in `app/models/schemas.py` – id, tenantId, title, language, sourceType, visibility, tags, content |
| Chunk JSON schema | ✅ | Implicit in `SearchResultItem` – chunkId, documentId, text, score, title, tags |
| IngestionJob schema | ✅ | `IngestionJobStatusResponse` – status (pending/processing/completed/failed), timestamps |
| SearchRequest/SearchResponse | ✅ | Full schemas in `schemas.py` |
| ChatRequest/ChatResponse | ✅ | Full schemas with history, citations, meta |
| ErrorResponse | ✅ | `ErrorResponse` with errorCode, message, details, traceId |
| HealthResponse, EchoRequest/EchoResponse | ✅ | Implemented |
| tenantId, userId, roles, language in user-facing schemas | ⚠️ | `userId` is required in SearchRequest/ChatRequest; spec says "optional but present" |
| Endpoints: GET /health, POST /echo, POST /v1/ingest/document, GET /v1/ingest/status, POST /v1/search, POST /v1/chat | ✅ | All implemented |
| Example requests/responses in spec | ✅ | Pydantic `json_schema_extra` examples on all schemas |

**Gap:** Add a committed API spec file (e.g. `docs/ai-core-api.md` or export OpenAPI YAML) and mark as v1.

---

### US-AI-SKELETON#2 – Project Skeleton

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| Project exists (Python + FastAPI) | ✅ | FastAPI app in `app/main.py` |
| Single documented command to start | ✅ | `python -m app.main`, `make dev`, `docker-compose up` |
| GET /health returns 200, status, service, version | ✅ | `app/api/health.py` |
| POST /echo accepts JSON, returns under `echo` key | ⚠️ | Echo expects `{"data": {...}}` – spec says "any valid JSON". Consider accepting raw JSON. |
| Config: HTTP port, DB URL, model API key | ✅ | `app/core/config.py` – HTTP_PORT, DATABASE_URL, OPENAI_API_KEY |
| README with run instructions, curl examples | ✅ | `README.md` |
| Dockerfile | ✅ | `Dockerfile` present |
| Container runs successfully | ✅ | docker-compose includes service |

---

### US-AI-INGESTION#3 – Ingestion Endpoints

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| POST /v1/ingest/document validates schema | ✅ | Pydantic validation |
| Creates IngestionJob (DB, not in-memory) | ✅ | Uses PostgreSQL via `IngestionJobRepository` |
| Returns 202 with jobId, status | ✅ | `IngestionJobResponse` |
| GET /v1/ingest/status by jobId | ✅ | Query param `jobId` |
| Returns 200 with full status JSON | ✅ | `IngestionJobStatusResponse` |
| Returns 404 if job not found | ✅ | `NotFoundError` → 404 |
| Background processing hook | ✅ | ARQ worker `process_ingestion_job` |
| Real extraction, chunking, embedding | ✅ | Beyond M1 – implemented in M2 |
| Invalid → 400, server error → 500 | ✅ | Exception middleware |
| README/API docs with curl examples | ✅ | Swagger UI, README |

**Note:** M1 allowed in-memory store; implementation uses DB (M2) – this is an upgrade.

---

### US-AI-SEARCH-CHAT#4 – Search & Chat Stubs

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| POST /v1/search validates SearchRequest | ✅ | Pydantic + tenantId check |
| Returns SearchResponse with results | ✅ | Real vector search (M2-D), not stub |
| Empty query → empty results | ✅ | `search_service.py` line 64–65 |
| POST /v1/chat validates ChatRequest | ✅ | Pydantic |
| Returns ChatResponse with answer, citations | ✅ | Full RAG (M3-B), not stub |
| Invalid → 400 | ✅ | |
| Developer playground | ✅ | `playground.py` – interactive CLI |

**Note:** M1 asked for stubbed/deterministic responses; implementation has real RAG and vector search – beyond M1 scope.

---

## Document 2: Acadio doc 2.docx (US-AI-M2-A through M2-D)

### What You're Building (Doc 2 Overview)

**Milestone 2** upgrades the AI Core with:
- **Persistent storage** – PostgreSQL with documents, chunks, ingestion_jobs
- **Real ingestion pipeline** – Extract text (PDF, URL), chunk, embed, store
- **Embedding provider** – OpenAI text-embedding-3-small (1536D)
- **Vector search** – pgvector similarity search with tenant + role filtering

---

### US-AI-M2-A#5 – Persistent Storage & Schema

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| Relational DB (Postgres) | ✅ | `DATABASE_URL`, asyncpg |
| Migrations for documents, chunks, ingestion_jobs | ✅ | `migrations/versions/20251130_0001_001_initial_schema.py` |
| documents: id, tenant_id, external_id, source_type, title, language, visibility_roles/scopes, tags, content_location_*, metadata, timestamps | ✅ | Schema matches |
| chunks: id, document_id, tenant_id, text, language, embedding, tags | ✅ | Plus start_offset, end_offset |
| ingestion_jobs: id, tenant_id, document_id, status, error_message, timestamps | ✅ | |
| Indexes on tenant_id | ✅ | All three tables |
| pgvector extension, embedding column | ✅ | `Vector(1536)`, HNSW index |
| Repository layer (create/fetch Document, Chunk, IngestionJob) | ✅ | `document_repo`, `chunk_repo`, `job_repo` |
| Endpoints use DB | ✅ | All use async session |

---

### US-AI-M2-B#6 – Real Ingestion Pipeline

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| POST /v1/ingest/document creates Document + IngestionJob | ✅ | `IngestionService.ingest_document` |
| Background processor picks pending jobs | ✅ | ARQ worker |
| Sets processing, loads Document | ✅ | `process_ingestion_job` |
| Content extraction: text, blob/URL, PDF | ✅ | `ContentExtractor` in `app/services/extractor.py` |
| Chunking with configurable strategy | ✅ | `TextChunker` – character-based, overlap |
| Creates Chunk records | ✅ | `chunk_repo.create_chunks_bulk` |
| Inherits visibility, tags from Document | ✅ | |
| start_offset/end_offset | ✅ | Optional per Doc 2 Q&A |
| Job status completed/failed | ✅ | |
| GET /v1/ingest/status from DB | ✅ | |
| Error handling, failed jobs don't block others | ✅ | |
| In-memory store removed | ✅ | DB only |

---

### US-AI-M2-C#7 – Embedding Provider & Chunk Embedding

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| EmbeddingProvider interface | ✅ | `app/providers/embedding.py` – `embed(texts) -> List[List[float]]` |
| Concrete implementation (OpenAI) | ✅ | `OpenAIEmbeddingProvider` |
| Config: EMBEDDING_MODEL_NAME | ✅ | `text-embedding-3-small` |
| Ingestion calls embed(), stores in chunks.embedding | ✅ | `tasks.py` |
| Embedding failure → job failed | ✅ | |
| Fallback if misconfigured | ✅ | Raises ValueError on startup if no API key |
| Provider isolated | ✅ | `get_embedding_provider()` factory |

---

### US-AI-M2-D#8 – Real Vector Search

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| POST /v1/search validates SearchRequest | ✅ | |
| tenantId required | ✅ | 400 if missing |
| Query embedding via EmbeddingProvider | ✅ | `get_embedding_provider().embed([query])` |
| Vector similarity search | ✅ | pgvector cosine distance |
| Filter by tenant_id | ✅ | Hard isolation |
| Filter by sourceType | ✅ | |
| Filter by subject, grade, tags | ✅ | |
| Visibility: roles (empty or intersect) | ✅ | `chunk_repo.vector_search` |
| visibility_scopes: stored, not enforced | ✅ | Doc 2 Q&A – documented |
| Order by similarity, topK | ✅ | |
| SearchResponse with chunkId, documentId, text, score, title, tags | ✅ | |
| Empty results → empty array | ✅ | |
| Query embedding failure → 500 | ✅ | |
| Multi-tenant safety | ✅ | tenant_id in WHERE |

---

## Document 2 Q&A: Acadio doc 2 Q:A.docx – Design Clarifications

### Summary of Q&A Decisions

| Topic | Decision | Implementation |
|-------|----------|----------------|
| visibility_roles | Enforce in search | ✅ Role-based filtering in `chunk_repo.vector_search` |
| visibility_scopes | Store, don't enforce in M2 | ✅ Stored, not used in search |
| start_offset/end_offset | Optional, populate when possible | ✅ Chunker populates; nullable in DB |
| Chunk size | ~1200 chars, 200 overlap | ⚠️ Config uses CHUNK_SIZE=500, CHUNK_OVERLAP=50 – below recommended |
| Configurable via env | CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS | ⚠️ Uses CHUNK_SIZE, CHUNK_OVERLAP (different names) |
| Embedding model | text-embedding-3-small, 1536D | ✅ |
| Embedding config | EMBEDDING_MODEL_NAME, EMBEDDING_DIM | ⚠️ EMBEDDING_DIM not in config (uses model mapping) |
| Scope filtering | Not enforced in M2 | ✅ |
| SEARCH_MAX_TOP_K | Cap topK (e.g. 50) | ❌ Not implemented – SearchRequest has `le=100` only |
| MAX_DOCUMENT_CHARS | Cap (e.g. 2–5M chars) | ❌ Not implemented |
| Failed ingestion | No auto-retry, manual re-submit | ✅ |

---

## Issues & Recommendations

### 🔴 Bug to Fix

**Chunk repository – grade filter bug** (`app/repositories/chunk_repo.py` line 262):

```python
# WRONG (copy-paste error):
Chunk.tags['grade'].astext == subject,

# CORRECT:
Chunk.tags['grade'].astext == grade,
```

### ⚠️ Gaps to Address

1. **API spec file** – Add `docs/ai-core-api.md` or export OpenAPI YAML and commit it.
2. **Chunk size** – Align with Doc 2 Q&A: CHUNK_SIZE ~1200, CHUNK_OVERLAP ~200 (or add CHUNK_MAX_CHARS / CHUNK_OVERLAP_CHARS).
3. **SEARCH_MAX_TOP_K** – Add config (e.g. 50) and cap `topK` in search.
4. **MAX_DOCUMENT_CHARS** – Add config (e.g. 2,000,000) and reject/truncate oversized documents.
5. **userId optional** – Make `userId` optional in SearchRequest and ChatRequest (spec: "optional but present").
6. **Security** – Remove hardcoded API key from `config.py` (line 25); use env only.

---

## Summary

| Document | Status | Notes |
|----------|--------|------|
| **Doc 1** | ✅ Mostly complete | API spec file missing; some schema tweaks |
| **Doc 2** | ✅ Mostly complete | Chunk config; safety limits; one bug (fixed) |
| **Doc 2 Q&A** | ⚠️ Partial | Chunk size, SEARCH_MAX_TOP_K, MAX_DOCUMENT_CHARS not fully aligned |

Overall, the implementation covers Doc 1 and Doc 2 well. The main gaps are configuration alignment with the Q&A, safety limits, and a few small fixes.

---

## Document 3: Acadio Doc 3.docx (US-AI-M3-A through M3-E) & Doc 3 Design Decisions

### What You're Building (Doc 3 Overview)

**Milestone 3** upgrades `/v1/chat` from a stub into a **full RAG pipeline** with:
- **LLMProvider abstraction** – decouple chat from a specific LLM vendor
- **RAG chat** – retrieval, context selection, prompt building, LLM call, citations
- **Guardrails & no-knowledge behaviour** – safe responses when there is no relevant context
- **Multi-turn history** – client-provided history, stateless on the server
- **Logging & observability** – structured logs for `/v1/chat`

Implementation lives mainly in:
- `app/providers/llm.py`
- `app/services/chat_service.py`
- `app/api/v1/chat.py`
- `app/utils/logger.py`
- `app/core/config.py`

---

### US-AI-M3-A#17 – LLMProvider Abstraction & Default Implementation

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| Define LLMProvider interface with `generate()` | ✅ | `LLMProvider` in `app/providers/llm.py` with `generate(messages, model, temperature, max_tokens, top_p, tenant_id, user_id, scenario)` returning `LLMResponse`. |
| Messages as array of `{role, content}` | ✅ | `LLMMessage` dataclass; converted to OpenAI format inside provider. |
| Usage info (promptTokens, completionTokens, totalTokens) | ✅ | `LLMUsage`; populated from OpenAI `response.usage`. |
| Concrete implementation (OpenAiLLMProvider) via env config | ✅ | `OpenAILLMProvider` reads defaults from `settings` via `get_llm_provider()` and `create_llm_provider()`. |
| Config-driven: API key, model name, temperature, max tokens | ✅ | `settings.LLM_PROVIDER`, `settings.get_llm_api_key()`, `LLM_DEFAULT_CHAT_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`. |
| Error handling and logging without sensitive content | ✅ | Logs model, tenant, scenario, and error string; does not log full prompts. |
| All LLM calls go through LLMProvider | ✅ | `/v1/chat`, tutor, analysis all call `llm_provider.generate`; no direct OpenAI calls elsewhere. |

---

### US-AI-M3-B#18 – Base RAG Pipeline for /v1/chat

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| `/v1/chat` validates `tenantId` & `message` | ✅ | `ChatService.chat` raises `ChatValidationError` for missing `tenantId`/`message`; caught in API layer and mapped to 400. |
| Builds SearchRequest from ChatRequest | ✅ | `search_request = SearchRequest(tenantId, userId, roles, language, query=message, topK=CHAT_CONTEXT_TOP_K)`. |
| Uses existing search (M2) with tenant + role filtering | ✅ | `SearchService` + `ChunkRepository.vector_search`. |
| Context selection up to `CHAT_CONTEXT_MAX_CHUNKS` and `CHAT_CONTEXT_MAX_CHARS` | ✅ | `_select_chunks` enforces both limits and truncates last chunk if needed. |
| Context formatting includes title + text + simple source tag | ✅ | `_format_context` builds `[Source i: title]\\nchunk`. |
| System prompt: context-only, no hallucinations, language control, Acadlo identity | ✅ | `_build_system_prompt` encodes all guardrails and language enforcement. |
| Messages: system + limited history + final user message with context | ✅ | `_construct_messages` calls `_normalize_and_limit_history` then `_build_user_message`. |
| LLM call via LLMProvider.generate with config model/params | ✅ | Uses `get_llm_provider()` with `settings.LLM_DEFAULT_CHAT_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`. |
| Response: ChatResponse with answer, citations, meta (model, chunks, tokens, latency) | ✅ | `ChatResponse` + `ChatMetadata` filled from search results and `LLMResponse.usage`. |
| M1 stub fully replaced by RAG | ✅ | No stub/echo path left; handler is full RAG. |

---

### US-AI-M3-C#19 – Guardrails & “No Knowledge” Behaviour

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| No-knowledge: zero chunks → no LLM call | ✅ | If `len(retrieved_chunks) == 0`, returns fixed `settings.CHAT_NO_KNOWLEDGE_MESSAGE` without LLM call. |
| No-knowledge answer is configurable and returns empty citations | ✅ | `CHAT_NO_KNOWLEDGE_MESSAGE` in config; `citations = []`, `retrievedChunks=0`, `usedChunks=0`. |
| System prompt enforces context-only answers, no hallucinated policies | ✅ | Guardrail rules 1–4 in `_build_system_prompt`. |
| Language control: answer in requested language or default | ✅ | Language = `request.language` or `settings.DEFAULT_LANGUAGE`; prompt uses that language explicitly. |
| Context size limits: `CHAT_CONTEXT_MAX_CHUNKS`, `CHAT_CONTEXT_MAX_CHARS`, completion tokens | ✅ | Enforced in `_select_chunks` and via `settings.LLM_MAX_TOKENS`. |
| Error handling: LLMProvider errors → 502; other errors → 500 | ✅ | Handled in `app/api/v1/chat.py` using `LLMProviderError` and generic `Exception`, returning structured `ErrorResponse`. |
| Logging avoids sensitive content | ✅ | `log_chat_request` / `log_chat_error` log metadata only; no full messages or chunk texts. |

---

### US-AI-M3-D#20 – Multi-turn History Handling (Stateless)

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| Support `ChatRequest.history` as `{role, content}` list | ✅ | History is a list of `ChatHistoryMessage` objects in schema. |
| Normalise history, skip invalid entries | ✅ | `_normalize_and_limit_history` validates role, content type, non-empty strings. |
| Limit to last `CHAT_HISTORY_MAX_TURNS` messages | ✅ | Slices to last N in `_normalize_and_limit_history`. |
| Truncate per-message using `CHAT_HISTORY_MAX_CHARS_PER_MESSAGE` | ✅ | Truncates long messages and logs once. |
| Inject history into LLM messages in order | ✅ | Normalised history appended as `user`/`assistant` messages before final user message. |
| Stateless: server does not persist history | ✅ | No DB/session state; client must send history each call; documented in `/v1/chat` docstring and README. |
| API compatibility with M1 (no breaking fields) | ✅ | ChatRequest/Response fields preserved; history is optional. |

---

### US-AI-M3-E#21 – Logging & Observability for /v1/chat

| Requirement | Status | Implementation Notes |
|-------------|--------|---------------------|
| Log structured record per `/v1/chat` request | ✅ | `log_chat_request` called for success and no-knowledge paths with all required metadata. |
| Logged fields: tenantId, userId, scenario, historyTurns, language, retrieved/used chunks, model, latencies, tokens, noKnowledge, httpStatus, traceId | ✅ | All present in `log_chat_request` signature and usage. |
| Avoid logging full messages / responses / chunks | ✅ | Docs and code only log metrics and identifiers; content is not logged. |
| Error logging with type, tenant, user, scenario, traceId, stack trace | ✅ | `log_chat_error` used for validation, config, LLM, and unexpected errors. |
| Log levels: INFO for success, WARNING for 4xx, ERROR for 5xx | ✅ | Implemented inside `log_chat_request`. |
| README/docs mention logging strategy | ✅ | README has a section on logging & observability (M3-E). |

---

### Doc 3 Design Decisions – Alignment Summary

| Topic | Decision | Implementation |
|-------|----------|----------------|
| Single active LLM provider per env | One provider per env, behind LLMProvider | ✅ `get_llm_provider()` uses `settings.LLM_PROVIDER`; only OpenAI supported for now. |
| Approximate tokens via chars/4 | Use char limits + heuristic | ✅ Context capped by `CHAT_CONTEXT_MAX_CHARS` (~1500 tokens); comments and README describe char→token mapping. |
| Over-long prompt: trim history then context, else error | Trim strategy | ✅ History and context are trimmed; explicit 4xx error for too-large conversation is not yet implemented separately (but overall limits prevent runaway prompts). |
| No-knowledge = zero chunks, skip LLM | Strict v1 rule | ✅ Implemented exactly in `ChatService.chat`. |
| Partial answers with low-quality context | Proceed with RAG if ≥1 chunk | ✅ Any non-empty result list triggers RAG; prompt encourages honesty about uncertainty. |
| No hallucination post-processing | Prompt + retrieval guardrails only | ✅ No second-pass validators; only prompt-level constraints. |
| Contradictory context | Let LLM handle, but point out contradictions | ✅ System prompt instructs model to surface conflicts; chunk selection is similarity-based. |
| Cross-language Q/A | Use multilingual embeddings; answer in user language | ✅ Embeddings are multilingual; system prompt and `language` enforce answer language. |
| Follow-ups with pronouns | Use history; ask for clarification if unclear | ✅ System prompt explicitly instructs clarification. |
| Per-tenant rate limiting | Not inside AI Core in M3 | ✅ Only per-request limits + logging; no internal rate limiter. |
| Prompt logging | Metadata-only; optional snippets in dev | ✅ Current code logs only metadata; snippet-logging flag not yet implemented but behaviour matches “no full prompts” rule. |
| Token usage aggregation | Log per-request, no billing yet | ✅ `LLMUsage` logged with tenantId; no aggregation table. |
| Different models per env | Config-driven per environment | ✅ `LLM_DEFAULT_CHAT_MODEL` and `LLM_PROVIDER` taken from env/config. |

Overall, the M3 implementation (LLMProvider, RAG chat, guardrails, history, logging) closely matches Doc 3 and the design decisions, with only minor optional enhancements left (e.g. more explicit “prompt too large” error and optional prompt-snippet logging).
