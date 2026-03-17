# Acadio AI Core — Status, Plan & Deliverables
**Date:** March 11, 2026  
**Prepared for:** Client (Yassa JOB)  
**Prepared by:** Acadio Engineering Team

---

## 1. Current Deliverables — What Is Built and Working

The following is a truthful mapping of what is complete in the codebase today. Completeness is marked at **~95% of specification** across Milestones 1–4 as defined in the original spec documents.

### M1 — Core API + Project Skeleton ✅ Complete
| Deliverable | Status |
|---|---|
| Versioned REST API (FastAPI + Swagger at `/docs`) | ✅ |
| Health check (`GET /health`), echo endpoint | ✅ |
| Full JSON schema contracts (documents, chunks, jobs, search, chat) | ✅ |
| Dockerfile + docker-compose, one-command startup | ✅ |
| Multi-tenant isolation on every endpoint | ✅ |

### M2 — Ingestion Pipeline + Vector Search ✅ Complete
| Deliverable | Status |
|---|---|
| PostgreSQL schema (documents, chunks, ingestion_jobs) with pgvector | ✅ |
| Background ingestion worker (ARQ): PDF / URL / text → chunks → embeddings | ✅ |
| OpenAI `text-embedding-3-small` (1536D) embedding stored per chunk | ✅ |
| `/v1/search`: vector similarity search with tenant + role + tag filters | ✅ |
| Ingestion job status polling (`GET /v1/ingest/status`) | ✅ |

### M3 — RAG Chat ✅ Complete
| Deliverable | Status |
|---|---|
| `/v1/chat`: full RAG pipeline (query → search → context → LLM → citations) | ✅ |
| LLMProvider abstraction (swappable, config-driven) | ✅ |
| Guardrails: no-hallucination system prompt, no-knowledge fallback | ✅ |
| Multi-turn history (stateless — client sends history) | ✅ |
| Structured logging per request (metadata only, no sensitive data) | ✅ |

### M4 — Adaptive Tutor Engine ✅ Built (with known gaps below)
| Deliverable | Status |
|---|---|
| `POST /v1/tutor/start` and `POST /v1/tutor/turn` endpoints | ✅ |
| TutorSession, ObjectiveState, StudentProfile persisted in DB | ✅ |
| LangGraph-based teaching loop (analyze → update → evaluate → plan → generate) | ✅ |
| Objective teaching state machine (NOT_STARTED → MASTERED/ESCALATE) | ✅ |
| Onboarding flow: collects topic, grade, level, language before teaching (Phase A) | ✅ |
| Student behavior classification: focused / guessing / confused (Phase B) | ✅ |
| Grade- and level-aware response generation (Phase B) | ✅ |
| Thinking trace (debug mode) per turn | ✅ |
| Off-topic / small-talk detection and redirect in planning | ✅ |
| Multi-language support (locale stored per session) | ✅ |
| MCQ mode when student is guessing (Phase C) | 🔄 In progress |
| "Two wrong → simplify + different method" and "correct → harder" behaviors (Phase D) | 🔄 In progress |

### Known Gaps (Being Addressed in Plan Below)
| Gap | Impact |
|---|---|
| **Tutor system prompt is not aligned with client's demo prompt** | Tutor feels like a generic chat rather than an adaptive AI teacher |
| **Tutor does not call RAG/search** — context_scopes are stored but unused | Tutor generates answers from LLM general knowledge, not from ingested curriculum content |
| **Documents are not converted into lessons/objectives** — no chapter-wise traversal | Book ingestion and tutoring are disconnected; tutor cannot teach "Chapter 3" from a real book |
| **Objectives are hardcoded for demo** — not pulled from backend | Cannot be used in production; must be supplied externally |
| Student profile aggregation (`updateStudentProfileFromObjectiveState`) not called | Cross-session learning history not updating |

---

## 2. Delivery Plan — Dates and Deliverables

> Format: **On [date] you will receive [Y].**  
> All dates assume no major blockers. Infrastructure (DB, API keys, server) must remain accessible.

---

### Deliverable 1 — Prompt-First Demo: Tutor Behaves Like a Real Adaptive Teacher
**Date: March 14, 2026**

This is the highest priority and addresses the core concern: the tutor must feel and behave like the demo prompt you shared — not like a generic chat.

**You will receive:**
- A tutor that opens every session by asking the 4 required questions: (1) topic, (2) grade, (3) level (Beginner / Intermediate / Advanced), (4) language — and does not teach until all 4 are answered.
- A system prompt aligned with your demo prompt: micro-learning, strict teaching loop (introduce → example → student tries → evaluate → adapt), no full explanations upfront.
- MCQ mode fully wired: when the student is guessing (random answers like 9999, 100), the tutor stops and presents only A/B/C/D options, asks to think before answering, and rejects invalid inputs.
- "Two consecutive wrong answers" behavior: tutor simplifies and switches to a different method.
- "Correct answer" behavior: tutor gives brief reinforcement and increases difficulty slightly.
- Off-topic/small-talk: tutor firmly redirects back to the lesson topic instead of following the student.
- Friendly-but-firm tone: encouraging, not permissive, with occasional light touch.

**Example interaction (what you will see):**
```
Tutor: Hi! Before we start — a few quick questions:
       1. What topic do you want to learn?
       2. What grade are you in?
       3. What is your level? (Beginner / Intermediate / Advanced)
       4. What language would you like to use?

Student: division, grade 4, beginner, English

Tutor: Great! Let's start with something simple.
       If you have 8 apples and want to share them equally between 2 friends,
       how many does each friend get?
       (Take your time and give it a try!)

Student: 99

Tutor: Hmm, let me ask this differently. Choose one:
       A) 2   B) 4   C) 8   D) 16
       Think about it — which one makes sense if you share 8 apples between 2 people?
```

---

### Deliverable 2 — Tutor Uses Ingested Content (RAG Connection)
**Date: March 20, 2026**

The tutor will call the search/RAG pipeline using the session's context_scopes, so explanations and examples are drawn from the actual ingested material (textbook, document, curriculum).

**You will receive:**
- Tutor response generation calls `/v1/search` internally with the current objective as the query, filtered by the session's tenant and context_scopes.
- Retrieved chunks from the ingested document are injected into the tutor's response prompt as reference material.
- If no relevant content is found in the knowledge base, the tutor falls back to general LLM knowledge and marks the answer as not from course material.
- Tutor explanations, examples, and hints will reference actual content from the uploaded document rather than LLM-generated generic examples.

**What changes from your side:** When calling `POST /v1/tutor/start`, you provide `context_scopes` that match the visibility/tags of the ingested book (e.g. `["tenant", "subject:math", "grade:4"]`). This links the session to that book's content.

---

### Deliverable 3 — Documents to Lessons/Objectives: Chapter-Wise Traversal
**Date: March 27, 2026**

When a document (e.g. a math textbook) is ingested, the system will be able to produce a structured set of lessons and objectives from it, enabling chapter-by-chapter tutoring.

**You will receive:**
- An ingestion tagging convention: documents are ingested with `chapter`, `topic`, and `lesson` tags per chunk (e.g. `{"chapter": "3", "topic": "fractions", "lesson": "equivalent_fractions"}`).
- A `POST /v1/lesson/from-document` endpoint that, given a `document_id`, extracts and returns a structured lesson plan: chapter list → lesson list → objective list per lesson (LLM-assisted extraction).
- Tutor can traverse chapter by chapter: when one lesson (chapter) is complete, session automatically advances to the next.
- Tags on chunks align with objective IDs so that the RAG search (Deliverable 2) correctly scopes to only the relevant chapter's content.

**Example output from `POST /v1/lesson/from-document`:**
```json
{
  "document_id": "doc_abc",
  "title": "Grade 4 Math",
  "chapters": [
    {
      "chapter": "1",
      "title": "Addition and Subtraction",
      "lessons": [
        {
          "lesson_id": "lesson_ch1_addition",
          "objectives": ["obj_add_2digit", "obj_add_3digit", "obj_add_word_problems"]
        }
      ]
    },
    {
      "chapter": "2",
      "title": "Multiplication",
      ...
    }
  ]
}
```

---

### Deliverable 4 — Objectives from Backend + Production-Ready End-to-End Demo
**Date: April 3, 2026**

**You will receive:**
- Objectives are no longer hardcoded; they are passed by the calling backend (Acadio/Nuxt) on session start, as per the original spec design.
- A complete end-to-end demo: upload a document → system extracts lessons/objectives → start tutor session with real lesson → student chats → tutor teaches chapter by chapter using RAG-backed content → session completes.
- Student profile aggregation (cross-session stats) completed: long-term student progress tracking works correctly.
- Minor spec gaps resolved: `SEARCH_MAX_TOP_K` cap, `MAX_DOCUMENT_CHARS` safety limit, grade filter bug fix.

---

## 3. Client Questions — Direct Answers

**Q: "It is a basic chat. If I connect a private LLM locally and statically provide the prompt, I get the same result. What is the difference?"**

You are correct and we agree. The core issue is that the rich infrastructure (state machine, planning, session, DB, RAG pipeline) is all in place, but the **final system prompt passed to the LLM** during response generation has not yet incorporated your demo prompt's quality. The system has been treating the LLM call as a structural output step rather than the primary teaching voice. Deliverable 1 (March 14) directly fixes this — your prompt philosophy becomes the driving system prompt.

**Q: "The student can get off-topic easily, and a totally irrelevant topic can be started."**

This is handled in planning logic today (there is an OFF_TOPIC detection branch), but it is not enforced firmly enough at the response generation level. Deliverable 1 includes explicit off-topic enforcement: the tutor refuses to follow off-topic threads and redirects with a firm but friendly message back to the current lesson objective.

**Q: "The persona of the tutor needs enhancement."**

Agreed. The current persona is mechanical. Deliverable 1 restructures the tutor system prompt to match your demo prompt's character: decisive, interactive, micro-step teaching, strict about answer quality, friendly-but-firm tone, and with light humor.

**Q: "The objectives are hardcoded for demo. In the real app they should be pulled from BE."**

Correct — this is a known demo limitation. The architecture already supports receiving objectives from the caller on `POST /v1/tutor/start`. Deliverable 4 removes all hardcoding, and by Deliverable 3 the document-to-lesson API will let the backend pull real objectives from ingested content.

**Q: "The overall prompt passed to LLM should be enhanced (use the one I shared)."**

The client's prompt is taken as the primary specification for Deliverable 1. Every element of that prompt — the 4 opening questions, the strict teaching loop, MCQ on guessing, two-wrong behavior, correct-answer behavior, interaction modes, and tone — will be implemented as the tutor's system-level instruction set.

**Q: "If I use the given prompt in ChatGPT it works better than this — so [I'm] seeing no big difference."**

The reason ChatGPT with your prompt works better: ChatGPT receives the full prompt as a single system instruction and executes it directly as a conversational agent. Our system currently builds the prompt programmatically from structured state (action plan, objective state, behavior classification) and the final LLM instruction does not convey the same richness. The fix is to combine both: keep the structured state for adaptive logic, but express the system prompt in the natural, directive language of your demo prompt rather than structured output instructions.

**Q: "Ingestion / doc-chapter structure is a secondary concern. First target: simple demo where tutor behavior is like the use case from the demo prompt."**

Understood and prioritized. Deliverable 1 (March 14) is exclusively focused on this. Deliverables 2–4 address the structural connections.

---

## 4. Example Dataset — Queries, Expected Behavior, and Completion Criteria

The following scenarios will be used to verify each deliverable is working correctly.

### 4.1 Onboarding (Deliverable 1 — must pass before teaching begins)

| # | Student Input | Expected Tutor Behavior |
|---|---|---|
| 1 | *(Session starts)* | Tutor asks all 4 questions: topic, grade, level, language. Does NOT start teaching. |
| 2 | "division, grade 4, beginner, English" | Tutor confirms and begins with the first micro-step of division. Does NOT dump full explanation. |
| 3 | Student tries to chat before answering questions | Tutor politely refuses and redirects to the unanswered question. |

### 4.2 Micro-Teaching Loop (Deliverable 1 — strict loop)

| # | Student Input | Expected Tutor Behavior |
|---|---|---|
| 1 | Correct answer (e.g. "4") to a division question | Tutor gives one brief reinforcement sentence, then asks a slightly harder question. |
| 2 | Wrong answer once (e.g. "5") | Tutor does not explain everything — gives a small hint, asks to try again. |
| 3 | Wrong answer twice in a row | Tutor switches method completely (e.g. switches from numeric to visual/counting). |
| 4 | Random/implausible answer (e.g. "9999", "banana") | Tutor stops normal flow. Presents MCQ: A/B/C/D only. Asks student to think. Rejects non-A/B/C/D responses. |
| 5 | Student answers MCQ correctly | Tutor exits MCQ mode, gives brief praise, returns to normal questions. |

### 4.3 Off-Topic and Engagement (Deliverable 1)

| # | Student Input | Expected Tutor Behavior |
|---|---|---|
| 1 | "What is the capital of France?" (during a math lesson) | Tutor declines to answer, references current lesson topic, redirects firmly. |
| 2 | "I'm bored" | Tutor acknowledges with light humor, encourages re-engagement, does not proceed until student responds. |
| 3 | "I don't know" | Tutor does NOT move on. Gives a hint or asks a simpler version of the same question. |

### 4.4 RAG-Backed Content (Deliverable 2 — tutor uses document)

| # | Scenario | Expected Behavior |
|---|---|---|
| 1 | Book chapter on "Equivalent Fractions" ingested with tag `chapter:3` | When teaching objective `obj_equivalent_fractions`, tutor's examples and explanations match the book's wording and examples. |
| 2 | Student asks for a hint | Tutor retrieves a relevant passage from the book chunk and paraphrases it — does not invent from scratch. |
| 3 | Topic not covered in ingested book | Tutor responds with "this is not in your course material" rather than hallucinating. |

### 4.5 Document → Lesson Structure (Deliverable 3)

| # | Input | Expected Output |
|---|---|---|
| 1 | Ingest a 5-chapter math PDF | `POST /v1/lesson/from-document` returns a structured JSON with 5 chapters, each with lesson titles and 2–5 objectives. |
| 2 | Start tutor session for Chapter 1, complete all objectives | System auto-advances to Chapter 2 objectives without manual re-configuration. |
| 3 | RAG search during Chapter 3 lesson | Only chunks tagged `chapter:3` are returned; no content leakage from other chapters. |

### 4.6 End-to-End Demo (Deliverable 4 — completion gate)

A complete session from zero to lesson completion must pass all of the following:
1. Tutor asks 4 onboarding questions and does not teach until answered.
2. Tutor teaches using micro-steps, not full explanations.
3. Tutor detects guessing and enforces MCQ.
4. Tutor switches method after 2 consecutive wrong answers.
5. Tutor references ingested book content in at least 2 out of 5 explanations.
6. Tutor does not go off-topic when the student tries to derail.
7. After all objectives in a lesson are mastered, session completes gracefully.
8. Objectives were passed from the backend, not hardcoded.

---

## 5. Why the Gap Exists — Technical Root Cause

To give full transparency on why the tutor feels like a "basic chat" despite significant backend infrastructure being built:

The system is architecturally complete: sessions, state machine, planning logic, LangGraph pipeline, DB persistence, LLM abstraction, and RAG search are all working. The gap is **at the last mile** — the final LLM call in `response_generation.py`.

Currently, the system prompt passed to the LLM during that call is structured around the *teaching state* (action plan type, objective state, behavior category) but does not carry the *teaching persona voice* from your demo prompt. In effect: the infrastructure correctly decides *what* to do (e.g. "ask a guided question, MCQ mode, difficulty=easier") but the LLM instruction describing *how to speak* is generic.

Additionally: the tutor and the RAG pipeline are two separate subsystems. The tutor generates its responses purely from LLM general knowledge + the action plan. The ingested documents live in a separate pipeline (`/v1/search`, `/v1/chat`) and were never wired back into the tutor's response generation — this was by spec design for v1 (Doc 5 explicitly deferred this) but it is the next critical integration point.

Both issues are fixable and the foundation is ready. Deliverable 1 fixes the prompt/persona gap in 3 days. Deliverables 2–3 connect the document pipeline to the tutor.

---

*This document supersedes all previous status notes and represents the current committed plan as of March 11, 2026.*
