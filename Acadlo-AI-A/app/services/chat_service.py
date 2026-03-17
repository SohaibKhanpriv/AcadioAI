"""Chat service for conversational RAG (Milestone 3-B & 3-C)"""
import logging
import time
import math
from typing import List, Tuple, Dict, Any, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMetadata,
    ChatCitation,
    SearchRequest,
    SearchResultItem,
)
from app.services.search_service import SearchService
from app.repositories.chunk_repo import ChunkRepository
from app.providers.llm import LLMProvider, get_llm_provider
from app.core.config import settings
from app.utils.logger import log_chat_request, log_chat_error, generate_trace_id

# Separate loggers:
# - debug_logger: for step-by-step debug logs (goes to console + app.log)
# - Structured logs via log_chat_request() use "chat_service" logger (goes to chat.log)
debug_logger = logging.getLogger(__name__)  # "app.services.chat_service"


class ChatValidationError(Exception):
    """Raised when chat request validation fails"""
    pass


class LLMProviderError(Exception):
    """Raised when LLM provider call fails"""
    pass


class ChatService:
    """Service for handling chat/conversational requests with RAG"""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.chunk_repo = ChunkRepository(db_session)
    
    async def chat(self, request: ChatRequest, trace_id: Optional[str] = None) -> ChatResponse:
        """
        Handle chat request with full RAG pipeline:
        1. Validate request
        2. Retrieve relevant chunks via search
        3. Select and format context
        4. Construct prompt with system message + history + context
        5. Call LLM
        6. Build response with citations
        
        Args:
            request: ChatRequest with message, tenant, user context
            trace_id: Optional trace ID for request tracking (US-AI-M3-E)
            
        Returns:
            ChatResponse with answer, citations, and metadata
        """
        start_time = time.time()
        trace_id = trace_id or generate_trace_id()
        
        debug_logger.info("=" * 70)
        debug_logger.info("💬 CHAT REQUEST - RAG PIPELINE")
        debug_logger.info("=" * 70)
        debug_logger.info(f"🆔 Trace ID: {trace_id}")
        debug_logger.info(f"👤 Tenant: {request.tenantId}")
        debug_logger.info(f"👤 User: {request.userId}")
        debug_logger.info(f"🎭 Roles: {request.roles}")
        debug_logger.info(f"🔤 Language: {request.language}")
        debug_logger.info(f"📝 Message: {request.message[:100]}...")
        debug_logger.info(f"🔄 History turns: {len(request.history)}")
        debug_logger.info(f"🎬 Scenario: {request.scenario}")
        
        # 1. Validation
        if not request.tenantId or not request.tenantId.strip():
            raise ChatValidationError("tenantId is required")
        if not request.message or not request.message.strip():
            raise ChatValidationError("message is required")
        
        # Ensure sessionId exists
        session_id = request.sessionId or f"sess_{uuid4().hex[:12]}"
        
        # Determine language
        language = request.language if request.language else settings.DEFAULT_LANGUAGE
        
        # 2. Retrieval - search for relevant chunks
        debug_logger.info("🔍 Step 1: RETRIEVAL")
        search_request = SearchRequest(
            tenantId=request.tenantId,
            userId=request.userId,
            roles=request.roles,
            language=language,
            query=request.message,
            topK=settings.CHAT_CONTEXT_TOP_K,
        )
        
        search_service = SearchService(
            db_session=self.db_session,
            chunk_repo=self.chunk_repo
        )
        
        search_response = await search_service.search(search_request)
        retrieved_chunks = search_response.results
        debug_logger.info(f"✅ Retrieved {len(retrieved_chunks)} chunks from search")
        
        # 3. Handle "no knowledge" scenario (zero chunks)
        if len(retrieved_chunks) == 0:
            debug_logger.info("⚠️  NO KNOWLEDGE: Zero chunks retrieved, returning standard message")
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Log structured "no knowledge" event (US-AI-M3-E)
            log_chat_request(
                tenant_id=request.tenantId,
                user_id=request.userId,
                scenario=request.scenario,
                history_turns=len(request.history),
                language=language,
                language_defaulted=(request.language is None),
                retrieved_chunks=0,
                used_chunks=0,
                model=None,
                llm_latency_ms=None,
                total_latency_ms=latency_ms,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                no_knowledge=True,
                http_status=200,
                trace_id=trace_id
            )
            
            return ChatResponse(
                sessionId=session_id,
                answer=settings.CHAT_NO_KNOWLEDGE_MESSAGE,
                language=language,
                citations=[],
                meta=ChatMetadata(
                    model=None,
                    retrievedChunks=0,
                    usedChunks=0,
                    promptTokens=None,
                    completionTokens=None,
                    totalTokens=None,
                    latencyMs=latency_ms,
                    intent=None
                )
            )
        
        # 4. Context selection & formatting
        debug_logger.info("📦 Step 2: CONTEXT SELECTION")
        selected_chunks, used_chunks_count = self._select_chunks(retrieved_chunks)
        context_text = self._format_context(selected_chunks)
        debug_logger.info(f"✅ Selected {used_chunks_count} chunks for context ({len(context_text)} chars)")
        
        # 5. Prompt construction
        debug_logger.info("📝 Step 3: PROMPT CONSTRUCTION")
        messages = self._construct_messages(
            request=request,
            context_text=context_text,
            language=language
        )
        debug_logger.info(f"✅ Constructed {len(messages)} messages for LLM")
        
        # 6. LLM call
        debug_logger.info("🤖 Step 4: LLM GENERATION")
        llm_start = time.time()
        llm_provider = get_llm_provider()
        
        try:
            # Convert dict messages to LLMMessage objects
            from app.providers.llm import LLMMessage
            llm_messages = [
                LLMMessage(role=msg["role"], content=msg["content"])
                for msg in messages
            ]
            
            llm_response = await llm_provider.generate(
                messages=llm_messages,
                model=settings.LLM_DEFAULT_CHAT_MODEL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
            
            llm_latency_ms = int((time.time() - llm_start) * 1000)
            debug_logger.info(f"✅ LLM response received (latency: {llm_latency_ms}ms)")
            if llm_response.usage:
                debug_logger.info(f"📊 Token usage: {llm_response.usage.total_tokens} tokens")
            
        except Exception as e:
            debug_logger.error(f"❌ LLM call failed: {str(e)}")
            raise LLMProviderError(f"LLM generation failed: {str(e)}") from e
        finally:
            await llm_provider.close()
        
        # 7. Build response with citations
        debug_logger.info("📄 Step 5: RESPONSE CONSTRUCTION")
        citations = self._build_citations(selected_chunks)
        
        # Extract usage info
        usage = llm_response.usage
        total_latency_ms = int((time.time() - start_time) * 1000)
        
        response = ChatResponse(
            sessionId=session_id,
            answer=llm_response.content,
            language=language,
            citations=citations,
            meta=ChatMetadata(
                model=settings.LLM_DEFAULT_CHAT_MODEL,
                retrievedChunks=len(retrieved_chunks),
                usedChunks=used_chunks_count,
                promptTokens=usage.prompt_tokens if usage else None,
                completionTokens=usage.completion_tokens if usage else None,
                totalTokens=usage.total_tokens if usage else None,
                latencyMs=total_latency_ms,
                intent=request.scenario if request.scenario != "generic" else None
            )
        )
        
        debug_logger.info(f"✅ Chat response ready (total latency: {total_latency_ms}ms)")
        debug_logger.info(f"📌 Answer preview: {response.answer[:100]}...")
        debug_logger.info("=" * 70)
        
        # Log structured success event (US-AI-M3-E)
        log_chat_request(
            tenant_id=request.tenantId,
            user_id=request.userId,
            scenario=request.scenario,
            history_turns=len(request.history),
            language=language,
            language_defaulted=(request.language is None),
            retrieved_chunks=len(retrieved_chunks),
            used_chunks=used_chunks_count,
            model=settings.LLM_DEFAULT_CHAT_MODEL,
            llm_latency_ms=llm_latency_ms,
            total_latency_ms=total_latency_ms,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            no_knowledge=False,
            http_status=200,
            trace_id=trace_id
        )
        
        return response
    
    def _select_chunks(
        self, 
        retrieved_chunks: List[SearchResultItem]
    ) -> Tuple[List[SearchResultItem], int]:
        """
        Select chunks for context based on:
        - Maximum number of chunks (CHAT_CONTEXT_MAX_CHUNKS)
        - Maximum total characters (CHAT_CONTEXT_MAX_CHARS)
        
        Returns:
            Tuple of (selected_chunks, count)
        """
        selected = []
        total_chars = 0
        
        for chunk in retrieved_chunks[:settings.CHAT_CONTEXT_MAX_CHUNKS]:
            chunk_length = len(chunk.text)
            
            # Check if adding this chunk would exceed char limit
            if total_chars + chunk_length > settings.CHAT_CONTEXT_MAX_CHARS:
                # Try to add truncated version if we have room
                remaining_space = settings.CHAT_CONTEXT_MAX_CHARS - total_chars
                if remaining_space > 100:  # Only add if we have meaningful space
                    # Truncate chunk text
                    truncated_chunk = SearchResultItem(
                        chunkId=chunk.chunkId,
                        documentId=chunk.documentId,
                        text=chunk.text[:remaining_space] + "...",
                        score=chunk.score,
                        title=chunk.title,
                        tags=chunk.tags
                    )
                    selected.append(truncated_chunk)
                    total_chars += len(truncated_chunk.text)
                break
            
            selected.append(chunk)
            total_chars += chunk_length
        
        return selected, len(selected)
    
    def _format_context(self, chunks: List[SearchResultItem]) -> str:
        """
        Format selected chunks into a context string for the LLM.
        
        Each chunk includes:
        - Document title
        - Chunk text
        - Internal reference (for citation tracking)
        """
        if not chunks:
            return ""
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(
                f"[Source {i}: {chunk.title}]\n{chunk.text}\n"
            )
        
        return "\n".join(context_parts)
    
    def _construct_messages(
        self,
        request: ChatRequest,
        context_text: str,
        language: str
    ) -> List[Dict[str, str]]:
        """
        Construct the messages array for LLM:
        1. System message with instructions
        2. History messages (if provided)
        3. Final user message with context
        
        Args:
            request: Original chat request
            context_text: Formatted context from retrieved chunks
            language: Response language
            
        Returns:
            List of message dicts with role and content
        """
        messages = []
        
        # 1. System message
        system_prompt = self._build_system_prompt(language)
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # 2. History messages (if any) - normalized and limited
        if request.history:
            normalized_history = self._normalize_and_limit_history(request.history)
            for hist_msg in normalized_history:
                messages.append({
                    "role": hist_msg.role,
                    "content": hist_msg.content
                })
        
        # 3. Final user message with context
        user_message_with_context = self._build_user_message(
            user_question=request.message,
            context_text=context_text
        )
        messages.append({
            "role": "user",
            "content": user_message_with_context
        })
        
        return messages
    
    def _normalize_and_limit_history(
        self,
        history: List[Any]
    ) -> List[Any]:
        """
        Normalize and limit conversation history (M3-D).
        
        Processing:
        1. Validate and normalize history entries
        2. Limit to last N turns (CHAT_HISTORY_MAX_TURNS)
        3. Truncate individual messages if too long
        
        Args:
            history: Raw history from ChatRequest
            
        Returns:
            Normalized and limited history list
        """
        if not history:
            return []
        
        normalized = []
        
        # 1. Normalize: validate role and content
        for msg in history:
            # Skip invalid entries
            if not hasattr(msg, 'role') or not hasattr(msg, 'content'):
                debug_logger.warning(f"Skipping invalid history entry: {msg}")
                continue
            
            # Validate role
            if msg.role not in ["user", "assistant"]:
                debug_logger.warning(f"Skipping history entry with invalid role: {msg.role}")
                continue
            
            # Ensure content is string
            if not isinstance(msg.content, str):
                debug_logger.warning(f"Skipping history entry with non-string content")
                continue
            
            # Skip empty content
            if not msg.content.strip():
                continue
            
            # Truncate content if too long
            content = msg.content
            if len(content) > settings.CHAT_HISTORY_MAX_CHARS_PER_MESSAGE:
                content = content[:settings.CHAT_HISTORY_MAX_CHARS_PER_MESSAGE] + "..."
                debug_logger.info(
                    f"Truncated history message from {len(msg.content)} to "
                    f"{settings.CHAT_HISTORY_MAX_CHARS_PER_MESSAGE} chars"
                )
            
            normalized.append(type(msg)(role=msg.role, content=content))
        
        # 2. Limit to last N turns
        if len(normalized) > settings.CHAT_HISTORY_MAX_TURNS:
            debug_logger.info(
                f"Limiting history from {len(normalized)} to "
                f"{settings.CHAT_HISTORY_MAX_TURNS} messages"
            )
            normalized = normalized[-settings.CHAT_HISTORY_MAX_TURNS:]
        
        return normalized
    
    def _build_system_prompt(self, language: str) -> str:
        """
        Build the system prompt that instructs the LLM on behavior.
        
        Enhanced with guardrails (M3-C):
        - Strict context-only answers
        - No hallucination of policies/procedures
        - Language control
        - Uncertainty acknowledgment
        - Contradiction handling
        """
        return f"""You are an AI assistant for the Acadlo educational platform, helping users understand school policies, procedures, rules, and educational content.

CRITICAL RULES - CONTEXT-ONLY ANSWERS:
1. Base your answers STRICTLY AND EXCLUSIVELY on the provided context below. Do not use any external knowledge, general information, or assumptions.

2. NEVER invent, guess, or hallucinate information about:
   - School policies or procedures
   - Rules and regulations
   - Administrative processes
   - Specific requirements or deadlines
   - Any institutional guidelines
   
3. If the context does not contain enough information to answer the question fully:
   - State clearly: "I don't have enough information in the available context to answer this question fully."
   - DO NOT fill in gaps with general knowledge or assumptions
   - You may suggest what additional information would be needed

4. If the context is incomplete, ambiguous, or contradictory:
   - Acknowledge the limitation explicitly
   - If contradictory, point out the conflict and explain which source seems most authoritative or recent
   - Do not hide contradictions or uncertainties
   
5. LANGUAGE REQUIREMENT:
   - Answer in: {language}
   - Context may be in a different language - use it for facts but respond in {language}
   - Translate accurately without adding interpretation

6. REFERENCE RESOLUTION:
   - If the user references something ambiguously (e.g., "it", "that policy", "the requirement")
   - Check if the recent conversation history makes it clear
   - If unclear, ask a clarifying question rather than guessing

7. ANSWER STYLE:
   - Be helpful, professional, and concise
   - Structure answers clearly with bullet points or numbers when appropriate
   - Cite which part of the context supports your answer when relevant

REMEMBER: It is better to say "I don't know based on the available information" than to provide incorrect or invented information about policies and procedures.

CONTEXT (your only knowledge base for this conversation):
"""
    
    def _build_user_message(self, user_question: str, context_text: str) -> str:
        """
        Build the final user message that includes both the question and context.
        
        Args:
            user_question: The user's actual question
            context_text: Formatted context from chunks
            
        Returns:
            Combined message string
        """
        return f"""{context_text}

USER QUESTION:
{user_question}"""
    
    def _build_citations(self, chunks: List[SearchResultItem]) -> List[ChatCitation]:
        """
        Build citation objects from selected chunks.
        
        Args:
            chunks: List of chunks that were used in context
            
        Returns:
            List of ChatCitation objects
        """
        citations = []
        seen_docs = set()  # Avoid duplicate citations from same doc
        
        for chunk in chunks:
            # Create citation (one per unique document for simplicity)
            if chunk.documentId not in seen_docs:
                citations.append(ChatCitation(
                    documentId=chunk.documentId,
                    chunkId=chunk.chunkId,
                    title=chunk.title
                ))
                seen_docs.add(chunk.documentId)
        
        return citations
