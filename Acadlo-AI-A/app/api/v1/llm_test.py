"""
LLM Provider Test Endpoint

Simple endpoint to test LLM provider functionality without full RAG pipeline.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.core.config import settings
from app.providers.llm import create_llm_provider, LLMMessage
from app.models.schemas import ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class LLMTestRequest(BaseModel):
    """Request for testing LLM provider"""
    message: str = Field(..., description="Test message to send to LLM", min_length=1)
    temperature: Optional[float] = Field(None, description="Temperature (0-2)", ge=0, le=2)
    max_tokens: Optional[int] = Field(None, description="Max completion tokens", ge=1, le=4000)
    model: Optional[str] = Field(None, description="Override default model")
    system_prompt: Optional[str] = Field(
        None,
        description="Custom system prompt (uses default if not provided)"
    )


class LLMTestResponse(BaseModel):
    """Response from LLM provider test"""
    success: bool = Field(..., description="Whether the test was successful")
    response: str = Field(..., description="LLM response content")
    model_used: str = Field(..., description="Model that was used")
    usage: dict = Field(..., description="Token usage information")
    config: dict = Field(..., description="Configuration used for the test")


@router.post(
    "/test",
    response_model=LLMTestResponse,
    responses={
        200: {"description": "LLM test successful"},
        500: {"model": ErrorResponse, "description": "LLM provider error"},
    },
    summary="Test LLM Provider",
    description="Simple endpoint to test LLM provider configuration and functionality. "
                "Useful for verifying API keys, model access, and provider setup."
)
async def test_llm(request: LLMTestRequest) -> LLMTestResponse:
    """
    Test the LLM provider with a simple message.
    
    This endpoint allows you to verify:
    - LLM provider is properly configured
    - API key is valid and working
    - Model access is available
    - Response format is correct
    """
    logger.info(f"🧪 LLM Test request - message length: {len(request.message)} chars")
    
    try:
        # Get API key
        api_key = settings.get_llm_api_key()
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="LLM API key not configured. Set OPENAI_API_KEY or LLM_API_KEY."
            )
        
        # Create provider
        provider = create_llm_provider(
            provider_type=settings.LLM_PROVIDER,
            api_key=api_key,
            default_model=settings.LLM_DEFAULT_CHAT_MODEL,
            default_temperature=settings.LLM_TEMPERATURE,
            default_max_tokens=settings.LLM_MAX_TOKENS,
        )
        
        # Prepare messages
        system_prompt = request.system_prompt or (
            "You are a helpful AI assistant for the Acadlo platform. "
            "Provide clear, concise, and accurate responses."
        )
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=request.message),
        ]
        
        # Determine model to use
        model_to_use = request.model or settings.LLM_DEFAULT_CHAT_MODEL
        
        # Call LLM
        response = await provider.generate(
            messages=messages,
            model=model_to_use,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tenant_id="test",
            user_id="test_user",
            scenario="llm_test",
        )
        
        # Build response
        usage_dict = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        
        config_dict = {
            "provider": settings.LLM_PROVIDER,
            "model": model_to_use,
            "temperature": request.temperature or settings.LLM_TEMPERATURE,
            "max_tokens": request.max_tokens or settings.LLM_MAX_TOKENS,
        }
        
        logger.info(
            f"✅ LLM Test successful - tokens: {usage_dict['total_tokens']}, "
            f"response length: {len(response.content)} chars"
        )
        
        return LLMTestResponse(
            success=True,
            response=response.content,
            model_used=model_to_use,
            usage=usage_dict,
            config=config_dict,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ LLM Test failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"LLM test failed: {str(e)}"
        )


@router.get(
    "/config",
    response_model=dict,
    summary="Get LLM Configuration",
    description="Returns the current LLM provider configuration (without sensitive data)"
)
async def get_llm_config() -> dict:
    """
    Get current LLM provider configuration.
    
    Useful for debugging and verifying settings.
    """
    api_key = settings.get_llm_api_key()
    
    return {
        "provider": settings.LLM_PROVIDER,
        "default_model": settings.LLM_DEFAULT_CHAT_MODEL,
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "api_key_configured": bool(api_key),
        "api_key_last_4": api_key[-4:] if api_key else None,
    }

