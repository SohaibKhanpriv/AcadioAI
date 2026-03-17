# Adaptive AI Tutor — Progress Report

This document summarizes what has been delivered in **Phase A** and **Phase B**, what is in progress in **Phase C and D**, and a brief overview of all phases in the adaptive tutor roadmap.

---

## Completed Work

### Phase A — Conversation Start (Onboarding)

**Status: Complete**

Before teaching anything, the tutor now collects the four required pieces of information from the student and does not start the lesson until they are provided.

**What was implemented:**

- **Onboarding flow in the tutor graph:** After loading the session, the graph checks onboarding status. If the student has not yet provided grade, level, language (and optionally topic), the tutor asks for them in order: (1) grade, (2) level (Beginner / Intermediate / Advanced), (3) language for the conversation, and (4) topic — only when the session was started without a lesson (e.g. `lesson_id = "pending"`).
- **Persistence:** Onboarding state (status, current step, collected answers) is stored in session metadata so it survives across turns. When onboarding is complete, the collected values are written to the student’s profile.
- **Student profile fields:** The profile stores `grade_band`, `skill_level` (beginner / intermediate / advanced), and `primary_language`. These are updated when the student answers the onboarding questions and are used in all later teaching turns.
- **Lesson resolution from topic:** When the client does not send a lesson (e.g. open-ended “I want to learn X”), the tutor uses the collected topic (and grade/level) to generate learning objectives and a lesson plan via an LLM, then continues into the normal teaching flow.
- **Returning students:** If the profile already has grade, level, and language, the tutor can show a short confirmation step (“Here’s what I have… Ready to start?”) before teaching.

The tutor does not teach content until the required onboarding answers are collected and (when applicable) the lesson is resolved.

---

### Phase B — Student Modeling and Grade/Level in Teaching

**Status: Complete**

The tutor now classifies each answer with a **behavior** (focused / guessing / confused), uses **grade** and **skill level** in every response, and prepares the pipeline for Phase C (MCQ when guessing).

**What was implemented:**

- **Behavior classification:** Every student answer is classified by the turn-analysis LLM with a `behavior` value: **focused** (on-task, real attempt), **guessing** (random or implausible answers, e.g. 9999, 100), or **confused** (trying but clearly mixed up). A separate flag `likely_guessing` is set when the answer looks like a non-serious guess so planning can react (e.g. Phase C: switch to MCQ).
- **Grade- and level-aware prompts:** Response generation receives the student’s `grade_band` and `skill_level` from the profile. The system prompt instructs the tutor to use “simple language appropriate for grade X” and to “adjust difficulty and scaffolding to the student’s level: Beginner / Intermediate / Advanced.” User prompts also pass grade and level so every reply is conditioned on them.
- **Planning readiness for guessing:** Planning has an early branch: when `behavior == guessing` or `likely_guessing` is true, it returns a “redirect guessing” plan (ask the student to think before answering). Phase C replaces this with full MCQ mode; Phase B only wires the data and this placeholder behavior.
- **Optional use of level in planning:** The planning function receives `student_skill_level` so future rules can adjust difficulty or support by level (e.g. more scaffolding for beginners).
- **Safe defaults:** If grade or skill level is missing (e.g. legacy profile), prompts use safe defaults (“age-appropriate language”, “moderate difficulty”) and the system does not break.

After Phase B, the tutor has richer student modeling and consistent use of grade and level in teaching; Phase C builds on behavior/likely_guessing to add the full MCQ flow.

---

## In Progress

### Phase C — Guessing and MCQ Behavior

**Status: In progress**

When the student appears to be guessing (random or implausible answers), the tutor will stop the normal flow and switch to **multiple-choice questions (MCQ)** with options A/B/C/D, ask the student to think before answering, and reject invalid answers until they choose a valid option or answer correctly.

**What we are building:**

- **MCQ mode in planning:** On detecting guessing (using Phase B’s `behavior` and `likely_guessing`), planning will return an **ASK_MCQ** action and set a session-level “MCQ mode” flag. While in MCQ mode, the tutor presents only A/B/C/D questions, reinforces “think before answering,” and on correct MCQ answer exits MCQ and returns to normal questions; on wrong MCQ answer stays in MCQ with a simpler question.
- **Persistence of MCQ mode:** The `mcq_mode` flag is stored in session metadata so that across turns the tutor stays in (or exits) MCQ consistently.
- **Response guidance for MCQ:** New intents (`switch_to_mcq`, `mcq_retry`, `reinforce_exit_mcq`) with clear instructions: present exactly four options, ask for A/B/C/D and a brief reason, and reject non-A/B/C/D answers by asking the student to choose one of the options.

---

### Phase D — “Two Wrong” and “Correct” Adaptive Behaviors

**Status: In progress** (combined with Phase C in the same implementation pass)

Two rule-based behaviors are being added so the tutor adapts clearly after repeated errors and after correct answers.

**What we are building:**

- **Two consecutive wrong answers:** When the student has two or more consecutive incorrect answers (and we are not in MCQ mode), planning returns a “simplify + different method” plan. Response guidance tells the tutor to change approach completely (e.g. switch from one analogy to another, or from explanation to a concrete example) and to simplify before asking an easier version of the question.
- **Correct answer while advancing:** When the student answers correctly and progress is “advancing,” planning returns a “reinforce briefly then harder” plan. Response guidance tells the tutor to give one specific sentence of reinforcement, then to ask a slightly harder question on the same concept without over-praising.

These are implemented as new planning priorities and intent-specific guidance in the response generator, with no change to the existing state machine or lesson flow.

---

## All Phases — Brief Overview

| Phase | Name | Description (3–4 lines) |
|-------|------|------------------------|
| **A** | **Conversation start (onboarding)** | **Done.** Before teaching, the tutor asks for topic (if no lesson provided), grade, level (Beginner/Intermediate/Advanced), and language. Answers are stored in the student profile and in session metadata. The tutor does not teach until onboarding is complete. When the client omits a lesson, the tutor can generate a lesson from the collected topic. |
| **B** | **Student modeling and grade/level** | **Done.** Every answer is classified with a behavior (focused / guessing / confused) and an optional “likely guessing” flag. Grade and skill level from the profile are passed into response generation and planning so the tutor uses age-appropriate language and level-appropriate difficulty. Prepares the pipeline for Phase C (MCQ on guessing). |
| **C** | **Guessing and MCQ** | **In progress.** When the student is classified as guessing, the tutor switches to multiple-choice mode (A/B/C/D only), asks the student to think before answering, and rejects invalid answers. MCQ mode is persisted per session; the tutor exits MCQ after a correct MCQ answer and returns to normal questions. |
| **D** | **“Two wrong” and “correct” behaviors** | **In progress.** After two consecutive wrong answers, the tutor simplifies and uses a different method (e.g. different analogy or example). After a correct answer when the student is advancing, the tutor gives brief specific reinforcement then a slightly harder question. |
| **E** | **Teaching flow and rules** | Optional tightening of the teaching loop (e.g. one idea → one example → one try → evaluate → adapt) and explicit prompt rules: do not advance without understanding; if the answer is unclear, ask the student to clarify before evaluating. |
| **F** | **Interaction modes and tone** | Formalize “correction” and “challenge” as named modes (e.g. after wrong vs after correct). Add prompt lines for tone: friendly but firm, encouraging but not permissive, occasional light humor. |
| **G** | **Profile and API alignment** | Ensure grade/level (and any new fields) are written from onboarding to the profile and exposed where needed. Optionally complete the “TODO” to update the student profile with aggregated stats from completed objectives for long-term adaptation. |

---

## Summary for Client

- **Phase A and B are complete.** The tutor now collects topic, grade, level, and language before teaching; persists them to the student profile; uses grade and level in every reply; and classifies each answer as focused, guessing, or confused (with a “likely guessing” flag for Phase C).
- **Phase C and D are in progress.** We are adding full MCQ mode when the student is guessing (with session-persistent MCQ state and clear response rules) and the two adaptive behaviors: “two wrong → simplify and change method” and “correct + advancing → reinforce briefly then harder.”
- **Phases E, F, and G** are planned as follow-ups for teaching-flow clarity, interaction modes/tone, and profile/API alignment.
