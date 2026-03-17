"""
LLM Provider Abstraction

Defines the LLMProvider interface and concrete implementations for calling
Large Language Models in a vendor-agnostic way.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    """Represents a single message in a conversation"""
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMUsage:
    """Token usage information from LLM response"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    """Response from LLM provider"""
    content: str
    usage: Optional[LLMUsage] = None
    raw: Optional[Any] = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    This abstraction allows the RAG pipeline to be independent of any specific
    LLM vendor (OpenAI, Azure, self-hosted, etc.)
    """

    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        scenario: Optional[str] = None,
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            messages: List of conversation messages
            model: Model name (uses default if not specified)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens in response
            top_p: Nucleus sampling parameter
            tenant_id: Tenant ID for logging/tracking
            user_id: User ID for logging/tracking
            scenario: Scenario context for logging

        Returns:
            LLMResponse with content, usage, and raw response

        Raises:
            Exception: On API errors, network failures, etc.
        """
        pass
    
    async def close(self) -> None:
        """
        Close the provider and release any resources.
        
        Called after LLM operations are complete to clean up connections.
        """
        pass


class OpenAILLMProvider(LLMProvider):
    """
    OpenAI implementation of LLMProvider.
    
    Uses the OpenAI API for chat completions.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "gpt-4o",
        default_temperature: float = 0.7,
        default_max_tokens: int = 1000,
    ):
        """
        Initialize OpenAI LLM provider.

        Args:
            api_key: OpenAI API key
            default_model: Default model to use
            default_temperature: Default temperature (0-2)
            default_max_tokens: Default max completion tokens
        """
        self.api_key = api_key
        self.default_model = default_model
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

        # Lazy import to avoid loading OpenAI unless needed
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=api_key)
            logger.info(
                f"✅ OpenAI LLM Provider initialized with model: {default_model}"
            )
        except ImportError as e:
            logger.error("Failed to import OpenAI library")
            raise ImportError(
                "openai package is required for OpenAILLMProvider. "
                "Install it with: pip install openai"
            ) from e
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        scenario: Optional[str] = None,
    ) -> LLMResponse:
        """
        Generate a chat completion using OpenAI API.

        See base class for parameter documentation.
        """
        # Use provided values or fall back to defaults
        model = model or self.default_model
        requested_max_tokens = max_tokens
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        # Convert internal message format to OpenAI format
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        logger.info(
            f"🤖 OpenAI LLM request - model: {model}, "
            f"messages: {len(messages)}, tenant: {tenant_id or 'unknown'}, "
            f"scenario: {scenario or 'none'}"
        )

        try:
            # Build request kwargs. Some newer models (e.g., gpt-5 family)
            # require max_completion_tokens instead of max_tokens and may
            # restrict sampling parameters (temperature/top_p).
            request_kwargs = {
                "model": model,
                "messages": openai_messages,
            }
            if model.lower().startswith("gpt-5"):
                # Smart default for GPT-5 reasoning models:
                # if caller didn't set max_tokens explicitly, increase budget.
                if requested_max_tokens is None and max_tokens < 4000:
                    logger.info(
                        f"ℹ️ GPT-5 auto-adjust: max tokens {max_tokens} -> 4000 "
                        "(reasoning-aware default)"
                    )
                    max_tokens = 4000
                elif requested_max_tokens is not None and max_tokens < 1000:
                    logger.warning(
                        f"⚠️ GPT-5 requested with low token budget ({max_tokens}). "
                        "This may produce empty outputs due to reasoning token usage."
                    )

                request_kwargs["max_completion_tokens"] = max_tokens
                # gpt-5 currently supports default temperature behavior only.
                # To avoid unsupported_value errors, do not send temperature/top_p.
            else:
                request_kwargs["max_tokens"] = max_tokens
                request_kwargs["temperature"] = temperature
                request_kwargs["top_p"] = top_p

            # Make API call
            response = await self.client.chat.completions.create(**request_kwargs)

            # Extract response content.
            # Some responses may provide refusal text instead of normal content.
            message = response.choices[0].message
            content = (message.content or "").strip()
            if not content:
                refusal_text = getattr(message, "refusal", None)
                if refusal_text:
                    content = str(refusal_text).strip()

            # Transparent notice when GPT-5 consumes completion budget on reasoning.
            finish_reason = getattr(response.choices[0], "finish_reason", None)
            if (
                not content
                and model.lower().startswith("gpt-5")
                and finish_reason == "length"
            ):
                reasoning_tokens = None
                accepted_prediction_tokens = None
                if response.usage:
                    details = getattr(response.usage, "completion_tokens_details", None)
                    if details:
                        reasoning_tokens = getattr(details, "reasoning_tokens", None)
                        accepted_prediction_tokens = getattr(details, "accepted_prediction_tokens", None)

                suggested_min = (reasoning_tokens + 200) if isinstance(reasoning_tokens, int) else (max_tokens + 400)
                details_suffix = ""
                if isinstance(reasoning_tokens, int):
                    details_suffix += f" Reasoning tokens used: {reasoning_tokens}."
                if isinstance(accepted_prediction_tokens, int):
                    details_suffix += f" Accepted prediction tokens: {accepted_prediction_tokens}."

                content = (
                    f"[GPT-5 Notice] Model used token budget before producing visible text. "
                    f"Current max tokens: {max_tokens}. Suggested minimum: {suggested_min}."
                    f"{details_suffix}"
                )
                logger.warning(content)

            # Extract usage information
            usage = None
            if response.usage:
                usage = LLMUsage(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                )

            logger.info(
                f"✅ OpenAI LLM response - model: {model}, "
                f"usage: {usage.total_tokens if usage else 'unknown'} tokens, "
                f"content_length: {len(content)} chars"
            )

            return LLMResponse(
                content=content,
                usage=usage,
                raw=response.model_dump() if hasattr(response, 'model_dump') else None,
            )

        except Exception as e:
            logger.error(
                f"❌ OpenAI LLM error - model: {model}, "
                f"tenant: {tenant_id or 'unknown'}, error: {str(e)}"
            )
            raise Exception(f"LLM generation failed: {str(e)}") from e
    
    async def close(self) -> None:
        """
        Close the OpenAI client and release resources.
        """
        if hasattr(self, 'client') and self.client:
            await self.client.close()
            logger.debug("✅ OpenAI client closed")


def create_llm_provider(
    provider_type: str,
    api_key: str,
    default_model: str,
    default_temperature: float = 0.7,
    default_max_tokens: int = 1000,
) -> LLMProvider:
    """
    Factory function to create LLM provider instances.

    Args:
        provider_type: Type of provider ("openai", "selfhosted", etc.)
        api_key: API key for the provider
        default_model: Default model name
        default_temperature: Default temperature
        default_max_tokens: Default max tokens

    Returns:
        Concrete LLMProvider instance

    Raises:
        ValueError: If provider_type is not supported
    """
    provider_type = provider_type.lower()

    if provider_type == "openai":
        return OpenAILLMProvider(
            api_key=api_key,
            default_model=default_model,
            default_temperature=default_temperature,
            default_max_tokens=default_max_tokens,
        )
    else:
        raise ValueError(
            f"Unsupported LLM provider: {provider_type}. "
            f"Supported providers: openai"
        )


def get_llm_provider() -> LLMProvider:
    """
    Factory function to get the configured LLM provider from settings.
    
    Returns:
        Configured LLMProvider instance based on app settings
        
    Raises:
        ValueError: If provider type is not supported
    """
    from app.core.config import settings
    
    return create_llm_provider(
        provider_type=settings.LLM_PROVIDER,
        api_key=settings.get_llm_api_key(),
        default_model=settings.LLM_DEFAULT_CHAT_MODEL,
        default_temperature=settings.LLM_TEMPERATURE,
        default_max_tokens=settings.LLM_MAX_TOKENS,
    )

