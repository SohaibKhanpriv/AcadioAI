"""
Topic extraction service for document ingestion.

Uses an LLM to identify distinct topics/sections from ingested document text,
classify each by subject (from SubjectEnum), and generate suggested learning
objectives per topic.  Each topic is then mapped to its matching chunks via
semantic similarity over the chunk embeddings.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.config import settings
from app.providers.llm import get_llm_provider, LLMMessage
from app.providers.embedding import get_embedding_provider
from app.tutor.enums import SubjectEnum

logger = logging.getLogger("ingestion_service")

SUBJECT_VALUES = [e.value for e in SubjectEnum]

_EXTRACTION_PROMPT = """Analyze the following document text and identify all distinct topics or sections.

For EACH topic found, return a JSON object with:
- "subject": one of {subjects}
- "topic_name": short descriptive name (max 60 chars)
- "description": 1-2 sentence summary of this topic section
- "grade_level": estimated school grade as a string (e.g. "4", "7") or null if unclear
- "suggested_objectives": array of 2-5 learning objectives, each as {{"title": "...", "description": "..."}}
- "approximate_text": a short verbatim excerpt (20-40 words) from this section so we can locate it

Return ONLY a valid JSON array. No markdown fences, no explanation.

Document text:
\"\"\"
{text}
\"\"\"
"""

MAX_TEXT_FOR_SINGLE_CALL = 28_000  # chars


def _truncate_for_prompt(text: str, max_chars: int = MAX_TEXT_FOR_SINGLE_CALL) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[... document truncated ...]"


def _validate_subject(raw: str) -> str:
    """Normalise and validate a subject value against SubjectEnum."""
    normalised = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if normalised in SUBJECT_VALUES:
        return normalised
    for s in SUBJECT_VALUES:
        if s in normalised or normalised in s:
            return s
    return SubjectEnum.OTHER.value


def _parse_llm_topics(raw_text: str) -> List[Dict[str, Any]]:
    """Parse the LLM JSON response into a list of topic dicts."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("topics") or data.get("results") or [data]
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")
    return data


async def extract_topics_from_text(
    text: str,
    tenant_id: str,
) -> List[Dict[str, Any]]:
    """
    Call LLM to extract structured topics from document text.

    Returns a list of dicts, each with keys:
        subject, topic_name, description, grade_level,
        suggested_objectives, approximate_text
    """
    prompt_text = _truncate_for_prompt(text)
    prompt = _EXTRACTION_PROMPT.format(
        subjects=", ".join(SUBJECT_VALUES),
        text=prompt_text,
    )

    llm = get_llm_provider()
    try:
        response = await llm.generate(
            messages=[
                LLMMessage(
                    role="system",
                    content="You output only valid JSON arrays. No markdown code fences, no explanation.",
                ),
                LLMMessage(role="user", content=prompt),
            ],
            model=settings.TUTOR_LLM_MODEL,
            temperature=0.3,
            max_tokens=4000,
            tenant_id=tenant_id,
            scenario="topic_extraction",
        )
        raw_topics = _parse_llm_topics(response.content or "[]")
    except Exception as e:
        logger.error(f"LLM topic extraction failed: {e}")
        return []

    validated: List[Dict[str, Any]] = []
    for raw in raw_topics:
        topic_name = (raw.get("topic_name") or "").strip()
        if not topic_name:
            continue
        objectives = raw.get("suggested_objectives") or []
        if not isinstance(objectives, list):
            objectives = []
        clean_objectives = []
        for obj in objectives[:5]:
            title = (obj.get("title") or "").strip()
            if title:
                clean_objectives.append({
                    "title": title,
                    "description": (obj.get("description") or "").strip() or None,
                })
        if not clean_objectives:
            clean_objectives = [
                {"title": f"Introduction to {topic_name}", "description": None},
                {"title": f"Practice {topic_name}", "description": None},
            ]

        validated.append({
            "subject": _validate_subject(raw.get("subject", "other")),
            "topic_name": topic_name[:300],
            "description": (raw.get("description") or "").strip()[:2000],
            "grade_level": (raw.get("grade_level") or None),
            "suggested_objectives": clean_objectives,
            "approximate_text": (raw.get("approximate_text") or "").strip()[:500],
        })

    logger.info(f"Extracted {len(validated)} topics from document text")
    return validated


async def map_topics_to_chunks(
    topics: List[Dict[str, Any]],
    chunk_ids: List[str],
    chunk_embeddings: List[List[float]],
    embedding_provider=None,
    top_n_chunks_per_topic: int = 10,
) -> List[Dict[str, Any]]:
    """
    For each topic, embed its name+description and find the top-N most similar
    chunks from the document. Mutates each topic dict in-place to add
    ``chunk_ids``, ``topic_embedding``.

    Args:
        topics: list of topic dicts from extract_topics_from_text
        chunk_ids: ordered list of chunk UUID strings (parallel to chunk_embeddings)
        chunk_embeddings: ordered list of embedding vectors for each chunk
        embedding_provider: optional; created if not supplied
        top_n_chunks_per_topic: how many chunks to link per topic
    """
    if not topics or not chunk_embeddings:
        return topics

    provider = embedding_provider or get_embedding_provider()
    try:
        topic_texts = [
            f"{t['topic_name']}. {t.get('description', '')}" for t in topics
        ]
        topic_embeds = await provider.embed(topic_texts)
    except Exception as e:
        logger.error(f"Failed to embed topic texts: {e}")
        for t in topics:
            t["chunk_ids"] = []
            t["topic_embedding"] = None
        return topics
    finally:
        if not embedding_provider:
            await provider.close()

    import numpy as np

    chunk_matrix = np.array(chunk_embeddings, dtype=np.float32)
    chunk_norms = np.linalg.norm(chunk_matrix, axis=1, keepdims=True)
    chunk_norms[chunk_norms == 0] = 1.0
    chunk_matrix_normed = chunk_matrix / chunk_norms

    for i, t in enumerate(topics):
        t_embed = np.array(topic_embeds[i], dtype=np.float32)
        t_norm = np.linalg.norm(t_embed)
        if t_norm == 0:
            t["chunk_ids"] = []
            t["topic_embedding"] = topic_embeds[i]
            continue
        t_normed = t_embed / t_norm
        similarities = chunk_matrix_normed @ t_normed
        top_indices = np.argsort(similarities)[::-1][:top_n_chunks_per_topic]
        t["chunk_ids"] = [chunk_ids[idx] for idx in top_indices]
        t["topic_embedding"] = topic_embeds[i]

    return topics
