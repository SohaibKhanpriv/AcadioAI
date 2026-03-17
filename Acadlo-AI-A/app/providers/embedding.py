"""
Embedding provider abstraction and implementations.
"""

from abc import ABC, abstractmethod
from typing import List
import logging
import httpx
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.
    Allows easy swapping between different embedding services (OpenAI, Azure, self-hosted, etc.)
    """

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (each vector is a list of floats)
            
        Raises:
            Exception: If embedding generation fails
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors produced by this provider.
        
        Returns:
            Integer dimension (e.g., 1536 for OpenAI ada-002)
        """
        pass


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI embedding provider implementation.
    Uses OpenAI's embedding API (e.g., text-embedding-3-small, text-embedding-ada-002).
    """

    # Model dimensions mapping
    MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        api_key: str = None,
        model_name: str = None,
        timeout: float = 60.0,
        max_retries: int = 3
    ):
        """
        Initialize OpenAI embedding provider.
        
        Args:
            api_key: OpenAI API key (defaults to settings.OPENAI_API_KEY)
            model_name: Model name (defaults to settings.EMBEDDING_MODEL_NAME)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.timeout = timeout
        self.max_retries = max_retries

        # Log API key status (masked for security)
        if not self.api_key:
            logger.error("❌ OpenAI API key is not set!")
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment variable."
            )
        
        # Mask API key for logging (show first 7 chars and last 4 chars)
        masked_key = f"{self.api_key[:7]}...{self.api_key[-4:]}" if len(self.api_key) > 11 else "***"
        logger.info(f"✅ OpenAI API key loaded: {masked_key}")
        logger.info(f"📊 Using embedding model: {self.model_name}")
        logger.info(f"📐 Expected embedding dimension: {self.get_dimension()}")

        # Initialize async OpenAI client
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            timeout=httpx.Timeout(timeout, connect=10.0),
            max_retries=max_retries
        )
        
        logger.info(f"🔧 OpenAI client initialized (timeout={timeout}s, max_retries={max_retries})")

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using OpenAI API.
        
        Supports batch processing (up to 2048 texts per request as per OpenAI limits).
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            ValueError: If texts list is empty
            Exception: If API call fails after retries
        """
        if not texts:
            logger.error("❌ Cannot generate embeddings: empty text list")
            raise ValueError("Cannot generate embeddings for empty text list")

        # Remove empty strings and strip whitespace
        cleaned_texts = [text.strip() for text in texts if text and text.strip()]
        
        if not cleaned_texts:
            logger.error("❌ All provided texts are empty after cleaning")
            raise ValueError("All provided texts are empty after cleaning")

        logger.info(f"🚀 Starting embedding generation for {len(cleaned_texts)} texts")
        logger.debug(f"   Model: {self.model_name}")
        logger.debug(f"   First text preview: {cleaned_texts[0][:100]}...")

        try:
            # OpenAI API supports up to 2048 texts per request
            # For larger batches, we'd need to chunk the request
            if len(cleaned_texts) > 2048:
                logger.error(f"❌ Too many texts: {len(cleaned_texts)} (max 2048)")
                raise ValueError(
                    f"Too many texts ({len(cleaned_texts)}). "
                    "OpenAI supports max 2048 texts per request."
                )

            # Call OpenAI embedding API
            logger.info(f"📡 Calling OpenAI API... (model={self.model_name})")
            response = await self.client.embeddings.create(
                model=self.model_name,
                input=cleaned_texts,
                encoding_format="float"  # Returns list of floats (not base64)
            )

            # Extract embeddings from response
            # Response data is sorted by index, so order is preserved
            embeddings = [item.embedding for item in response.data]
            
            logger.info(f"✅ Successfully generated {len(embeddings)} embeddings")
            logger.info(f"   Embedding dimension: {len(embeddings[0]) if embeddings else 0}")
            logger.info(f"   Total tokens used: {response.usage.total_tokens if hasattr(response, 'usage') else 'N/A'}")

            return embeddings

        except Exception as e:
            logger.error(f"❌ OpenAI embedding generation failed: {str(e)}")
            logger.error(f"   Model: {self.model_name}")
            logger.error(f"   Texts count: {len(cleaned_texts)}")
            # Re-raise with more context
            raise Exception(
                f"OpenAI embedding generation failed for model '{self.model_name}': {str(e)}"
            ) from e

    def get_dimension(self) -> int:
        """
        Get the embedding dimension for the configured model.
        
        Returns:
            Integer dimension (e.g., 1536)
        """
        return self.MODEL_DIMENSIONS.get(self.model_name, 1536)

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.close()


def get_embedding_provider() -> EmbeddingProvider:
    """
    Factory function to get the configured embedding provider.
    
    Returns:
        Configured EmbeddingProvider instance
    """
    # For now, we only support OpenAI
    # In the future, this could check config and return different providers
    return OpenAIEmbeddingProvider()

