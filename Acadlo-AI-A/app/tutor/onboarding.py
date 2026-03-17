"""
Onboarding flow: collect topic (if needed), grade, level, language before teaching.

Smart onboarding: only ask what we don't already know.
- Topic: skip when lesson_id + objective_ids are provided by caller.
- Grade / level / language: skip when already in StudentProfile.
"""
import re
import logging
from typing import List, Optional, Dict, Any

from app.db.models import StudentProfile

logger = logging.getLogger(__name__)

QUESTION_KEYS = ["topic", "grade", "level", "language"]

VALID_LEVELS = {"beginner", "intermediate", "advanced"}

LANGUAGE_ALIASES: Dict[str, List[str]] = {
    "en": ["english", "eng"],
    "ar": ["arabic", "عربي", "arabi"],
    "fr": ["french", "français", "francais"],
    "es": ["spanish", "español", "espanol"],
    "ur": ["urdu", "اردو"],
    "hi": ["hindi", "हिन्दी"],
    "de": ["german", "deutsch"],
    "tr": ["turkish", "türkçe", "turkce"],
    "zh": ["chinese", "mandarin", "中文"],
    "ja": ["japanese", "日本語"],
    "ko": ["korean", "한국어"],
    "pt": ["portuguese", "português"],
    "it": ["italian", "italiano"],
    "ru": ["russian", "русский"],
    "nl": ["dutch", "nederlands"],
    "ms": ["malay", "bahasa melayu"],
    "id": ["indonesian", "bahasa indonesia"],
    "bn": ["bangla", "bengali", "বাংলা"],
    "sw": ["swahili", "kiswahili"],
    "th": ["thai", "ไทย"],
}

# Build a fast reverse lookup: alias -> code
_LANG_LOOKUP: Dict[str, str] = {}
for _code, _aliases in LANGUAGE_ALIASES.items():
    _LANG_LOOKUP[_code] = _code
    for _a in _aliases:
        _LANG_LOOKUP[_a.lower()] = _code

ALL_LANGUAGE_NAMES = set(_LANG_LOOKUP.keys())


def get_required_onboarding_questions(
    lesson_id: str,
    objective_ids: List[str],
    profile: Optional[StudentProfile],
) -> List[str]:
    """
    Return the list of question keys we still need answers for.
    - Topic: required only when no lesson/objectives provided (lesson_id is "pending" or empty, or objective_ids empty).
    - Grade: required when profile.grade_band is missing.
    - Level: required when profile.skill_level is missing.
    - Language: required when profile.primary_language is missing.
    """
    required = []
    lesson_id_norm = (lesson_id or "").strip().lower()
    obj_ids = [o for o in (objective_ids or []) if (o or "").strip()]
    obj_ids_normalized = [o.strip().lower() for o in obj_ids]
    # Treat "pending" or empty as no lesson (open-ended session)
    has_lesson = bool(
        lesson_id_norm
        and lesson_id_norm not in ("pending", "")
        and obj_ids
        and not (len(obj_ids_normalized) == 1 and obj_ids_normalized[0] == "pending")
    )

    if not has_lesson:
        required.append("topic")
    if not profile or not (profile.grade_band and profile.grade_band.strip()):
        required.append("grade")
    if not profile or not (profile.skill_level and profile.skill_level.strip()):
        required.append("level")
    if not profile or not (profile.primary_language and profile.primary_language.strip()):
        required.append("language")

    return required


def is_onboarding_complete(
    onboarding_state: Optional[Dict[str, Any]],
    required: List[str],
) -> bool:
    """True if we have answers for every required question."""
    if not required:
        return True
    if not onboarding_state or not onboarding_state.get("answers"):
        return False
    answers = onboarding_state["answers"]
    return all(
        answers.get(key) and str(answers.get(key)).strip()
        for key in required
    )


def get_next_onboarding_question(
    required: List[str],
    answers: Dict[str, str],
) -> Optional[str]:
    """Return the next question key that has no answer, or None if all done."""
    for key in required:
        if not (answers.get(key) and str(answers.get(key)).strip()):
            return key
    return None


def parse_onboarding_response(
    message: str,
    required: List[str],
    locale: str = "en",
    current_question: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Extract onboarding answers from a student message.

    Context-aware: when *current_question* is set (the question we just asked),
    an ambiguous single-word answer is assigned to that question.

    Also supports comma-separated multi-answers like
    "division, grade 4, beginner, English".
    """
    if not message or not message.strip():
        return {k: None for k in required}

    text = message.strip()
    lower = text.lower()
    extracted: Dict[str, Optional[str]] = {k: None for k in required}

    parts = re.split(r"[,/]|\s+and\s+", lower, flags=re.I)
    parts = [p.strip() for p in parts if p.strip()]

    # Original-cased parts (for preserving topic casing)
    orig_parts = re.split(r"[,/]|\s+and\s+", text, flags=re.I)
    orig_parts = [x.strip() for x in orig_parts if x.strip()]

    # ---- Structured extraction (multi-part answers) ----

    # Grade: "grade 4", "4th grade", "1st grade", plain digit, "g4"
    for p in parts:
        if "grade" in p:
            num = re.search(r"\d+", p)
            if num:
                extracted["grade"] = num.group(0)
                break
        grade_match = re.match(r"^(\d{1,2})\s*(st|nd|rd|th)?\s*grade$", p)
        if grade_match:
            extracted["grade"] = grade_match.group(1)
            break
        if re.match(r"^g\d+$", p):
            extracted["grade"] = p[1:]
            break

    # Level: beginner, intermediate, advanced
    for p in parts:
        for level in VALID_LEVELS:
            if level in p:
                extracted["level"] = level
                break
        if extracted.get("level"):
            break

    # Language: use the reverse lookup
    for p in parts:
        code = _LANG_LOOKUP.get(p)
        if code:
            extracted["language"] = code
            break

    # Topic: parts that aren't grade/level/language
    if "topic" in required and len(parts) > 1:
        for i, p in enumerate(parts):
            if p == extracted.get("grade") or ("grade" in p and re.search(r"\d", p)):
                continue
            if p in VALID_LEVELS:
                continue
            if p in ALL_LANGUAGE_NAMES:
                continue
            if p.isdigit() or re.match(r"^g\d+$", p):
                continue
            # Use original casing
            extracted["topic"] = orig_parts[i] if i < len(orig_parts) else p
            break

    # ---- Single-part / ambiguous answer: use current_question context ----
    if len(parts) == 1 and current_question:
        word = parts[0]
        already_matched = any(v is not None for v in extracted.values())
        if not already_matched:
            # Assign the answer to the question we just asked
            if current_question == "topic":
                extracted["topic"] = text  # preserve original casing
            elif current_question == "grade":
                num = re.search(r"\d+", word)
                extracted["grade"] = num.group(0) if num else word
            elif current_question == "level":
                for lvl in VALID_LEVELS:
                    if lvl in word:
                        extracted["level"] = lvl
                        break
                if not extracted["level"]:
                    extracted["level"] = word
            elif current_question == "language":
                code = _LANG_LOOKUP.get(word)
                extracted["language"] = code if code else word
        elif current_question == "language" and not extracted.get("language"):
            # Grade/level may have matched, but if the question was about
            # language, a remaining unmatched single word IS the language.
            code = _LANG_LOOKUP.get(word)
            extracted["language"] = code if code else word
        elif current_question == "topic" and not extracted.get("topic"):
            extracted["topic"] = text

    # ---- Fallback for multi-part: if only topic is unmatched and there's a leftover ----
    if "topic" in required and not extracted.get("topic") and len(parts) > 1:
        for i, p in enumerate(parts):
            if p != extracted.get("grade") and p not in VALID_LEVELS and p not in ALL_LANGUAGE_NAMES:
                extracted["topic"] = orig_parts[i] if i < len(orig_parts) else p
                break

    return extracted


def merge_onboarding_answers(
    current: Dict[str, str],
    new: Dict[str, Optional[str]],
) -> Dict[str, str]:
    """
    Merge new extractions into current answers.
    Only fills in fields that are STILL EMPTY; never overwrites an existing answer.
    """
    out = dict(current)
    for k, v in new.items():
        if v and str(v).strip() and not (out.get(k) and str(out[k]).strip()):
            out[k] = str(v).strip()
    return out


def get_onboarding_question_prompt(
    question_key: str,
    locale: str,
    question_index: int,
    total_questions: int,
) -> str:
    """Return the tutor message that asks for this onboarding question."""
    lang = locale.split("-")[0].lower() if locale else "en"
    if question_key == "topic":
        if lang == "ar":
            return "قبل ما نبلش — شو الموضوع اللي حاب تتعلمه؟"
        return "Before we start — what topic do you want to learn?"
    if question_key == "grade":
        if lang == "ar":
            return "في أي صف أنت؟"
        return "What grade are you in?"
    if question_key == "level":
        if lang == "ar":
            return "ما مستواك؟ (مبتدئ / متوسط / متقدم)"
        return "What is your level? (Beginner / Intermediate / Advanced)"
    if question_key == "language":
        if lang == "ar":
            return "بأي لغة تحب نكمل؟"
        return "What language would you like to use?"
    return "?"


def get_full_onboarding_prompt(locale: str) -> str:
    """Return the full 4-question block when we need to ask everything (e.g. first turn, no lesson)."""
    lang = locale.split("-")[0].lower() if locale else "en"
    if lang == "ar":
        return (
            "مرحبا! قبل ما نبلش — عندي أسئلة بسيطة:\n"
            "١. شو الموضوع اللي حاب تتعلمه؟\n"
            "٢. في أي صف أنت؟\n"
            "٣. ما مستواك؟ (مبتدئ / متوسط / متقدم)\n"
            "٤. بأي لغة تحب نكمل؟"
        )
    return (
        "Hi! Before we start — a few quick questions:\n"
        "1. What topic do you want to learn?\n"
        "2. What grade are you in?\n"
        "3. What is your level? (Beginner / Intermediate / Advanced)\n"
        "4. What language would you like to use?"
    )


def get_redirect_to_question_message(question_key: str, locale: str) -> str:
    """When the student chats instead of answering, redirect to the current question."""
    q = get_onboarding_question_prompt(question_key, locale, 1, 1)
    lang = locale.split("-")[0].lower() if locale else "en"
    if lang == "ar":
        return f"خلينا نكمّل هالسؤال الأول: {q}"
    return f"Let's answer this first: {q}"
