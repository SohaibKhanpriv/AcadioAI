# Tutor Implementation Review: Doc 4 & Doc 4B

This document reviews the **Adaptive Tutor** implementation against:
- **Spec docs/Acadio doc 4 tutor.docx** (US-AI-M4-A, M4-B, M4-C)
- **Spec docs/Acadio doc 4B tutor next.docx** (US-AI-M4-E, M4-F, M4-G, M4-ADDENDUM)

It explains how the tutor is built, component by component, and how decision paths flow through the system.

---

## 1. What You're Building (High-Level)

The **Tutor Runtime Engine** is an adaptive, multi-turn tutoring system that:

1. **Starts a session** for a student on a lesson with one or more learning objectives.
2. **On each turn:** analyzes the student’s message, updates performance and teaching state, plans the next pedagogical action, and generates a natural-language tutor reply.
3. **Progresses through objectives** using a **teaching state machine** (diagnosing → exposing → guided practice → independent practice → checking → consolidating → mastered / escalate).
4. **Persists** sessions, objective states, and student profiles in the DB; exposes **POST /v1/tutor/start** and **POST /v1/tutor/turn** for Nuxt/ABP.

The flow is **stateless at the API**: the client sends the latest student message; the server loads session/profile from DB, runs the graph, saves, and returns the tutor reply.

**Related:** How lessons/objectives are created, how they relate to ingested documents (e.g. a book), and how the tutor could reference a knowledge base are described in [Lessons, Objectives, and Ingested Documents — Flow and Gaps](lessons-objectives-and-ingested-documents-flow.md).

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  HTTP API (app/api/v1/tutor.py)                                              │
│  POST /v1/tutor/start   POST /v1/tutor/turn                                  │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Runner (app/tutor/runner.py)                                                │
│  run_tutor_start(params, session, locale, include_thinking_trace)            │
│  run_tutor_turn(params, session, include_thinking_trace)                     │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LangGraph (app/tutor/graph.py)  build_tutor_graph() → tutor_app             │
│  State: TutorGraphContext                                                    │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐   ┌───────────────────────┐   ┌───────────────────────────┐
│ load_session  │   │ select_current_       │   │ route_by_objective_state   │
│ _and_profile  │──►│ objective             │──►│ (conditional)              │
└───────────────┘   └───────────────────────┘   └───────────┬───────────────┘
                                                             │
              ┌──────────────────────────────────────────────┼────────────────────┐
              ▼                                              ▼                    ▼
   ┌──────────────────────┐                    ┌─────────────────────┐  ┌──────────────┐
   │ thinking_loop        │                    │ lesson_complete      │  │ select_      │
   │ (see below)          │                    │                     │  │ current_     │
   └──────────┬───────────┘                    └──────────┬──────────┘  │ objective    │
              │                                            │             └──────┬───────┘
              │                                            │                    │
              └────────────────────┬───────────────────────┘                    │
                                   ▼                                             │
                        ┌──────────────────────┐                                 │
                        │ save_session_and_    │◄────────────────────────────────┘
                        │ profile              │
                        └──────────┬──────────┘
                                   ▼
                                  END
```

**Thinking loop** (when the current objective is not MASTERED/ESCALATE):

```
analyze_student_turn → update_performance_and_state → evaluate_progress
    → plan_tutor_action → generate_tutor_response → save_session_and_profile
```

---

## 3. Data Layer (M4-A)

### 3.1 TutorSession

| Spec (M4-A) | Implementation |
|-------------|----------------|
| id, tenantId, ouId, studentId, regionId, programId, lessonId, objectiveIds | ✅ `app/db/models.py` – TutorSession with all these fields |
| contextScopes | ✅ `context_scopes` (JSONB list) |
| status (active, completed, aborted) | ✅ `status` string; `TutorSessionStatus` enum in `app/tutor/enums.py` |
| currentObjectiveId, metadata | ✅ `current_objective_id`, `session_metadata` (JSONB: locale, chat_history, last_tutor_message, no_answer_streak, objective_labels) |
| startedAt, endedAt, createdAt, updatedAt | ✅ |
| Indexes (tenant+student, tenant+lesson, tenant+ou, tenant+status) | ✅ `__table_args__` |

**Repository:** `TutorSessionRepository` – create_session, get_session_by_id, update_session. Tenant-scoped.

### 3.2 ObjectiveState

| Spec (M4-A) | Implementation |
|-------------|----------------|
| id, tenantId, sessionId, objectiveId | ✅ |
| state (enum) | ✅ `state` string; `ObjectiveTeachingState` in `app/tutor/enums.py` |
| questionsAsked, questionsCorrect, questionsIncorrect | ✅ |
| lastErrorTypes, masteryEstimate | ✅ `last_error_types` (JSONB), `mastery_estimate` |
| startedAt, masteredAt, createdAt, updatedAt, extra | ✅ |

**Repository:** `ObjectiveStateRepository` – create_objective_state, get_objective_states_for_session, get_objective_state, save_objective_state.

### 3.3 StudentProfile

| Spec (M4-A) | Implementation |
|-------------|----------------|
| tenantId, studentId, primaryOuId, ouMemberships | ✅ `app/db/models.py` – StudentProfile |
| objectiveStats, paceEstimate, engagementEstimate, etc. | ✅ `objective_stats` (JSONB), `pace_estimate`, `engagement_estimate` |
| getOrCreateStudentProfile, updateStudentProfileFromObjectiveState | ✅ StudentProfileRepository |

**Note:** Aggregation from ObjectiveState into StudentProfile (updateStudentProfileFromObjectiveState) is referenced in code as TODO in `graph_nodes.save_session_and_profile`.

---

## 4. Objective Teaching State Machine (M4-B)

### 4.1 States

Defined in `app/tutor/enums.py` as `ObjectiveTeachingState`:

- NOT_STARTED → DIAGNOSING (or EXPOSING if skip_diagnosing)
- DIAGNOSING → EXPOSING / GUIDED_PRACTICE / INDEPENDENT_PRACTICE (by initial accuracy)
- EXPOSING → GUIDED_PRACTICE
- **SUPPORTING** (extra scaffolding when stuck – implementation addition)
- GUIDED_PRACTICE ↔ INDEPENDENT_PRACTICE (by accuracy / min_practice_questions)
- INDEPENDENT_PRACTICE → CHECKING (when criteria met)
- CHECKING → CONSOLIDATING → MASTERED, or back to GUIDED/INDEPENDENT
- MASTERED, ESCALATE = terminal

Spec mentions “diagnosing, exposing, guided_practice, independent_practice, checking, consolidating, mastered, escalate”. The code adds **SUPPORTING** (e.g. when `no_answer_streak >= 2` in `thinking_loop_nodes.node_update_performance_and_state`).

### 4.2 Config

- **ObjectiveTeachingConfig** (`app/tutor/types.py`): min_practice_questions, practice_accuracy_threshold, min_check_questions, check_accuracy_threshold, max_total_attempts_before_escalate, max_consecutive_errors_before_escalate, skip_diagnosing, skip_consolidating.
- **LessonTeachingConfig**: lesson_id + dict of objective_id → ObjectiveTeachingConfig; `get_config(objective_id)` with default.

### 4.3 Transition Logic

- **Pure function:** `compute_objective_state_transition(input) -> ObjectiveStateTransitionOutput` in `app/tutor/state_machine.py`.
- No DB/LLM; input = current_state, objective_config, performance (ObjectivePerformanceSnapshot).
- Output = next_state, mastery_estimate, escalate_flag, reasoning.
- Escalation: `_should_escalate(perf, config)` (max total attempts, max consecutive errors).

### 4.4 Persistence Integration

- **apply_objective_state_transition(repo, args)** in `app/tutor/state_machine_integration.py`: loads ObjectiveState, calls `compute_objective_state_transition`, updates ORM (state, mastery_estimate, counters, last_error_types, mastered_at, started_at), saves.

---

## 5. LangGraph Skeleton & Context (M4-C)

### 5.1 TutorGraphContext

Defined in `app/tutor/graph_context.py`. Holds:

- **Identity:** tenant_id, session_id, ou_id, context_scopes, program_id, lesson_id, objective_ids, objective_labels, current_objective_id, student_id, region_id.
- **Loaded models:** session, objectives (dict objective_id → ObjectiveState), student_profile.
- **Config:** lesson_config, objective_config.
- **Turn I/O:** student_message, last_tutor_message, chat_history.
- **Thinking loop:** last_analysis, tutor_action_plan, current_performance_snapshot, progress_evaluation, tutor_message, **thinking_trace** (list of TutorThinkingStep).
- **Output:** tutor_reply, lesson_complete.
- **Internal:** is_new_session, low_confidence, no_answer_streak, locale_hint, db_session.

Matches spec; adds progress_evaluation, objective_labels, no_answer_streak, low_confidence, locale_hint.

### 5.2 Nodes (Graph Structure)

| Node | Spec | Implementation |
|------|------|----------------|
| load_session_and_profile | Load or create session; load/create profile; populate context | ✅ `graph_nodes.load_session_and_profile` – create vs load by session_id; stores locale in session_metadata |
| select_current_objective | Pick first non-MASTERED/ESCALATE; set objective_config | ✅ `graph_nodes.select_current_objective` |
| route_by_objective_state | Branch: turn vs lesson_complete vs select_next | ✅ `graph.route_by_objective_state_updated` – returns "thinking_loop" \| "lesson_complete" \| "select_current_objective" |
| tutor_turn_placeholder | Stub in M4-C | ✅ Still present in `graph_nodes` but **not used** in compiled graph; graph uses thinking loop instead |
| lesson_complete | Set lesson_complete, placeholder message | ✅ `graph_nodes.lesson_complete` |
| save_session_and_profile | Persist session, objective states, profile | ✅ `graph_nodes.save_session_and_profile` – updates session (current_objective_id, status, ended_at, session_metadata including chat_history, last_tutor_message, no_answer_streak) |

### 5.3 Runners

- **run_tutor_start(params, session, locale, include_thinking_trace)** – builds TutorGraphContext with session_id=None, locale_hint, invokes `tutor_app.ainvoke`, returns TutorTurnResult (with optional thinking_trace).
- **run_tutor_turn(params, session, include_thinking_trace)** – context with session_id and student_message; graph loads session; returns TutorTurnResult.

---

## 6. Tutor Planning & Action Schema (M4-E)

### 6.1 TutorActionKind & TutorActionPlan

- **action_schema.py:** TutorActionKind (ASK_QUESTION, GIVE_HINT, EXPLAIN_CONCEPT, BREAKDOWN_STEP, ENCOURAGE, META_COACHING, ADJUST_DIFFICULTY, CHECK_UNDERSTANDING, SWITCH_OBJECTIVE, ESCALATE, END_LESSON), DifficultyAdjustment (EASIER, SAME, HARDER).
- **TutorActionPlan:** kind, target_objective_id, difficulty_adjustment, intent_label, include_encouragement, escalation_reason, metadata. JSON-serializable.

### 6.2 plan_next_tutor_action

- **planning.py:** Pure, rule-based.
- **Priority 1:** REQUEST → immediate action (explain/example/step_by_step/repeat) per request_type.
- **Priority 1.5:** OFF_TOPIC / SMALL_TALK → redirect (EXPLAIN_CONCEPT, redirect_off_topic).
- **Priority 1.6:** QUESTION → answer (EXPLAIN_CONCEPT, answer_student_question).
- **Priority 2:** low_confidence or no_answer_streak >= 2 → _auto_decide_support (streak 4+ pure teach, streak 3 empathy_first_then_teach, else by help_preference / progress_evaluation / error_category / affect).
- **Priority 3:** progress_evaluation not ADVANCING → _adapt_for_progress (stalled/regressing).
- **Priority 4:** State-specific: _plan_for_not_started, _plan_for_diagnosing, _plan_for_exposing, _plan_for_supporting, _plan_for_guided_practice, _plan_for_independent_practice, _plan_for_checking, _plan_for_consolidating, _plan_for_mastered, _plan_for_escalate.
- Encouragement: _should_encourage can set include_encouragement on the plan.

### 6.3 plan_for_current_turn

- **planning_integration.py:** Reads teaching_state from state.objectives[current_objective_id], config from lesson_config/objective_config, calls plan_next_tutor_action with no_answer_streak, low_confidence, progress_evaluation. Used by node_plan_tutor_action.

---

## 7. Thinking Loop & Response Generation (M4-F)

### 7.1 Thinking Loop Nodes

| Node | Responsibility |
|------|----------------|
| **node_analyze_student_turn** | If no student_message → default analysis (OTHER, NOT_APPLICABLE). Else calls `analyze_student_turn(...)` (LLM). Sets last_analysis, low_confidence, no_answer_streak. Normalizes non-attempt (“I don’t know”) to NOT_APPLICABLE. Appends thinking_trace (stage=analysis). |
| **node_update_performance_and_state** | Builds snapshot from current ObjectiveState; `update_performance_snapshot(previous, analysis)`; persists to ObjectiveState; `apply_objective_state_transition`; if no_answer_streak >= 2 forces state to SUPPORTING. Appends thinking_trace (performance_update). |
| **node_evaluate_progress** | `evaluate_progress(performance, analysis, chat_history)` → ProgressEvaluation (signal, recommended_approach). Stored in state.progress_evaluation; appends thinking_trace (progress_evaluation). |
| **node_plan_tutor_action** | `plan_for_current_turn(state, performance, analysis)` → TutorActionPlan; fallback to get_default_start_plan on MissingContextError. Appends thinking_trace (planning). |
| **node_generate_tutor_response** | `generate_tutor_response(tenant_id, locale, action_plan, lesson_context, objective_context, student_analysis, chat_history, progress_evaluation, student_message, last_tutor_message)` → TutorMessage. Sets state.tutor_message and state.tutor_reply; appends thinking_trace (response_generation). |

### 7.2 Student Turn Analysis (M4-D)

- **turn_analysis_types.py:** TurnKind (ANSWER, REQUEST, QUESTION, META, OFF_TOPIC, SMALL_TALK, OTHER), AnswerCorrectness, ErrorCategory, ConfidenceLevel, HelpPreference, RequestType, StudentTurnAnalysis.
- **turn_analysis_service.analyze_student_turn:** LLM-based classifier; returns StudentTurnAnalysis. Used by node_analyze_student_turn.

### 7.3 Performance Snapshot

- **performance_snapshot.py:** update_performance_snapshot(previous, analysis, max_recent) updates counts and recent_answers from analysis.
- **turn_analysis_integration:** build_snapshot_from_objective_state, persist_snapshot_to_state.

### 7.4 Response Generation

- **response_generation.generate_tutor_response:** Builds prompt from action_plan, lesson/objective context, student_analysis, chat_history, progress_evaluation; calls LLM; returns TutorMessage (text, debug_notes, suggestions, metadata). Locale-aware; fallback message on LLM failure.

### 7.5 TutorMessage

- **tutor_message.py:** text, debug_notes, suggestions, metadata. Matches spec.

---

## 8. HTTP API (M4-G)

### 8.1 Endpoints

- **POST /v1/tutor/start** – StartTutorSessionRequest (tenant_id, student_id, lesson_id, objective_ids or objectives, ou_id, region_id, program_id, context_scopes, locale, initial_student_message, lesson_config, include_thinking_trace). Returns TutorTurnResponse.
- **POST /v1/tutor/turn** – ContinueTutorSessionRequest (tenant_id, session_id, student_message, include_thinking_trace). Returns TutorTurnResponse.

### 8.2 Request/Response

- Start: objectives can be plain-English list; converted to objective_ids via _resolve_objectives (slugified). Locale default ar-JO.
- Response: tenant_id, session_id, lesson_id, current_objective_id, tutor_reply, lesson_complete; optional debug.thinking_trace when include_thinking_trace=True.

### 8.3 Error Handling

- 400 validation (e.g. missing objectives or student_message).
- 404 session not found (ObjectiveStateNotFoundError).
- 403 tenant mismatch (ValueError message).
- 409 session terminal (lesson complete).
- 500 TutorRuntimeError / generic.

Logging: request_id, tenant_id, session_id, endpoint, status, lesson_complete.

---

## 9. Thinking Trace & Multi-Language (M4-ADDENDUM)

### 9.1 Thinking Trace

- **TutorThinkingStep** (`thinking_trace.py`): stage (analysis | performance_update | planning | response_generation | progress_evaluation), summary, data (sanitized).
- Each thinking loop node appends a step to state.thinking_trace.
- **include_thinking_trace** on start/turn → response.debug["thinking_trace"] = serialized steps. Implemented in runner and tutor API.

### 9.2 Multi-Language

- Locale stored in session_metadata on start; read from session on turn. Used in analyze_student_turn and generate_tutor_response. BCP-47 (ar-JO, en-US, etc.); no hard-coding to Arabic/English only.

---

## 10. Decision Paths (Summary)

1. **Session start vs continue**  
   - session_id None → load_session_and_profile creates TutorSession and ObjectiveStates (NOT_STARTED); locale in session_metadata.  
   - session_id set → load existing session; tenant and terminal checks.

2. **Which objective**  
   - select_current_objective: keep current if not MASTERED/ESCALATE; else first non-terminal in objective_ids.

3. **Route after select**  
   - No current objective → lesson_complete.  
   - Current MASTERED/ESCALATE and others remain → select_current_objective.  
   - All terminal → lesson_complete.  
   - Else → thinking_loop.

4. **Within thinking loop**  
   - **Analyze:** LLM classifies turn (ANSWER/REQUEST/QUESTION/META/etc.), correctness, error_category, affect, help_preference; “I don’t know” normalized; no_answer_streak and low_confidence set.  
   - **Update:** Snapshot updated from analysis; state machine transition applied; optional force to SUPPORTING on no_answer_streak >= 2.  
   - **Evaluate:** Progress signal (e.g. advancing/stalled/regressing) and recommended_approach.  
   - **Plan:** REQUEST/QUESTION/OFF_TOPIC/SMALL_TALK handled first; then stuck/auto-support; then progress-based adaptation; then state-specific rules.  
   - **Generate:** LLM turns TutorActionPlan + context into TutorMessage in locale.

5. **State machine**  
   - From NOT_STARTED: skip_diagnosing → EXPOSING else DIAGNOSING.  
   - DIAGNOSING: by initial accuracy → EXPOSING / GUIDED_PRACTICE / INDEPENDENT_PRACTICE.  
   - EXPOSING/SUPPORTING → GUIDED_PRACTICE.  
   - GUIDED_PRACTICE ↔ INDEPENDENT_PRACTICE by min_practice_questions and practice_accuracy_threshold.  
   - INDEPENDENT_PRACTICE → CHECKING when criteria met.  
   - CHECKING → CONSOLIDATING → MASTERED or back to practice; escalation by max attempts/consecutive errors.  
   - MASTERED/ESCALATE terminal.

---

## 11. Spec vs Implementation Checklist

| Story | Status | Notes |
|-------|--------|-------|
| **M4-A** TutorSession, ObjectiveState, StudentProfile | ✅ | Models, repos, indexes; session_metadata holds locale, chat_history, etc. Profile aggregation from objectives is TODO in save node. |
| **M4-B** State machine | ✅ | All states including SUPPORTING; config; pure transition; apply_objective_state_transition. |
| **M4-C** Graph skeleton | ✅ | Context, nodes, conditional routing; stub placeholder exists but graph uses full thinking loop. |
| **M4-D** Turn analysis | ✅ | analyze_student_turn (LLM), StudentTurnAnalysis types, integration in thinking loop. |
| **M4-E** Planning & action schema | ✅ | TutorActionPlan, plan_next_tutor_action (state + request/affect/progress), plan_for_current_turn. |
| **M4-F** Thinking loop & response | ✅ | Full loop (analyze → update → evaluate → plan → generate); generate_tutor_response; TutorMessage. |
| **M4-G** HTTP API | ✅ | /start, /turn; DTOs; errors; locale; include_thinking_trace. |
| **M4-ADDENDUM** Thinking trace, multi-language | ✅ | TutorThinkingStep; nodes append trace; debug.thinking_trace; locale generic. |

---

## 12. File Reference

| Component | Main files |
|-----------|------------|
| API | `app/api/v1/tutor.py` |
| Runner | `app/tutor/runner.py` |
| Graph | `app/tutor/graph.py` |
| Context | `app/tutor/graph_context.py` |
| Session/objective/profile nodes | `app/tutor/graph_nodes.py` |
| Thinking loop nodes | `app/tutor/thinking_loop_nodes.py` |
| State machine | `app/tutor/state_machine.py`, `app/tutor/state_machine_integration.py` |
| Planning | `app/tutor/planning.py`, `app/tutor/planning_integration.py` |
| Action schema | `app/tutor/action_schema.py` |
| Turn analysis | `app/tutor/turn_analysis_types.py`, `app/tutor/turn_analysis_service.py`, `app/tutor/turn_analysis_integration.py` |
| Performance snapshot | `app/tutor/performance_snapshot.py` |
| Progress evaluator | `app/tutor/progress_evaluator.py` |
| Response generation | `app/tutor/response_generation.py` |
| Tutor message / thinking trace | `app/tutor/tutor_message.py`, `app/tutor/thinking_trace.py` |
| Types & enums | `app/tutor/types.py`, `app/tutor/enums.py` |
| DB models | `app/db/models.py` (TutorSession, ObjectiveState, StudentProfile) |
| Repositories | `app/repositories/tutor_session_repo.py`, `objective_state_repo`, `student_profile_repo` |

This is how the tutor is built end-to-end and how each component and decision path is implemented against Doc 4 and Doc 4B.

---

## 13. Doc 5 M4 Clarifications – Compliance

**Spec:** *Spec docs/Acadio doc 5 M4 clarifications.docx*

Cross-check of each clarification against the current implementation.

| # | Clarification | Decision for v1 | Where we are | Status |
|---|----------------|-----------------|--------------|--------|
| **1** | TutorSession.objective_ids & context_scopes | Caller supplies both; AI Core does not call BE to resolve. | `StartTutorSessionRequest` requires `objective_ids` or `objectives` and accepts `context_scopes`; no backend call in tutor code. | ✅ Aligned |
| **2** | StudentProfile.objectiveStats growth | Unbounded OK for v1; one entry per objective; no turn history in objectiveStats. | `StudentProfile.objective_stats` is JSONB keyed by objective_id; repo updates aggregates only (no turn history). | ✅ Aligned |
| **3** | When to call updateStudentProfileFromObjectiveState() | Call whenever we update ObjectiveState in node_update_performance_and_state; idempotent upsert per (student_id, objective_id). | **Not called** from any graph node. `update_student_profile_from_objective_state` exists in `student_profile_repo` but is never invoked. Docstring says "when objective reaches terminal state" and implementation **increments** total_sessions – clarification wants **idempotent** merge (attempt counts, last state, mastery, last_seen_at) on every update. | ❌ Gap |
| **4** | ObjectiveTeachingConfig source | Built-in defaults in AI Core + optional caller override; no external config DB. | Defaults in `ObjectiveTeachingConfig(objective_id=...)`; caller can pass `lesson_config` on /start; `_get_objective_config` returns `lesson_config.get_config(obj_id)` or default. No grade/subject keyed static store. | ⚠️ Mostly aligned (no grade/subject keyed store) |
| **5** | EXPOSING → GUIDED_PRACTICE | Use **explanations_shown** and **modelled_examples_shown** on ObjectiveState; transition when explanations_shown ≥ 1 AND modelled_examples_shown ≥ 1 (or 2 per config). | **Not implemented.** ObjectiveState has no `explanations_shown` or `modelled_examples_shown`. `_from_exposing` uses `perf.total_attempts >= 1` only. No counter-based rule. | ❌ Gap |
| **6** | AffectSignal | Primary: AI Core infers from text via analyze_student_turn. Optional: frontend_affect override. affect never null (default NEUTRAL). | LLM infers affect; `StudentTurnAnalysis.affect` defaults to NEUTRAL. **No `frontend_affect`** parameter in `analyze_student_turn` or in API/context. | ⚠️ Partial (no frontend override) |
| **7** | TutorGraphContext – DTO vs ORM | Do **not** store ORM in context; use DTOs; load ORM → map to DTO → run graph → map back → persist. | Context holds **ORM**: `session: TutorSession`, `objectives: Dict[str, ObjectiveState]`, `student_profile: StudentProfile` and `db_session`. Not DTOs. | ❌ Gap |
| **8** | DB sessions inside LangGraph | Prefer graph **pure and DB-free**; no long-lived session in context; DB at boundary only. | **db_session** is passed in `TutorGraphContext` and used inside nodes (load_session_and_profile, apply_objective_state_transition, save_session_and_profile). Graph is not DB-free. | ❌ Gap |
| **9** | Node failures mid-execution | Fail fast for non-transient errors; return structured ErrorResponse; LLM may have local retry/fallback. | API returns 4xx/5xx with structured detail on validation/session/tenant errors. Analysis and response generation use **fallback** on LLM failure (default analysis, safe message). No retry. | ✅ Aligned |
| **10** | Objective selection order | Use **original objective_ids** order; first non-MASTERED/ESCALATE; no priority field. | `select_current_objective` iterates `state.objective_ids` in order; picks first whose state is not MASTERED/ESCALATE. Order comes from session (set on create). | ✅ Aligned |

---

### Summary: Where We Are vs Doc 5

- **Fully aligned (4):** 1 (caller supplies objectives/scopes), 2 (objectiveStats growth), 9 (fail fast + LLM fallback), 10 (objective order).
- **Partial / minor (2):** 4 (config: defaults + override yes, no grade/subject store), 6 (affect from LLM + default NEUTRAL, no frontend_affect).
- **Gaps (4):**
  - **3** – Call `update_student_profile_from_objective_state` (or equivalent idempotent profile update) whenever ObjectiveState is updated in the turn (e.g. from `node_update_performance_and_state` or after save), and make the update idempotent (merge counts/state, not increment total_sessions per call).
  - **5** – Add `explanations_shown` and `modelled_examples_shown` to ObjectiveState (and migration), update them when action is EXPLAIN_CONCEPT/BREAKDOWN_STEP or modelled example, and change EXPOSING → GUIDED_PRACTICE to use these counters (e.g. explanations_shown ≥ 1 and modelled_examples_shown ≥ 1 or 2).
  - **7** – Use DTOs in TutorGraphContext instead of ORM models; map ORM → DTO at graph entry and DTO → ORM at exit.
  - **8** – Remove db_session from context; perform all DB work at the boundary (before/after graph invoke); or document why v1 keeps session-in-context and plan migration for a later milestone.

Implementing 3, 5, 7, and 8 (and the small 4/6 tweaks if desired) would bring the implementation in line with Doc 5 M4 clarifications.
