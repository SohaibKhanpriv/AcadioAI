"""Text chunking service for document processing"""
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)


class TextChunker:
    """
    Splits text into chunks for embedding and retrieval.
    
    Uses character-based chunking with configurable size and overlap.
    Attempts to break at sentence/paragraph boundaries when possible.
    """
    
    # Sentence-ending punctuation
    SENTENCE_ENDINGS = {'.', '!', '?', '。', '؟', '!'}
    
    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        """
        Initialize chunker with configurable parameters.
        
        Args:
            chunk_size: Target chunk size in characters (default from settings)
            chunk_overlap: Overlap between chunks in characters (default from settings)
        """
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        
        logger.debug(f"TextChunker initialized: size={self.chunk_size}, overlap={self.chunk_overlap}")
    
    def chunk(
        self,
        text: str,
        document_id: UUID,
        tenant_id: str,
        language: str,
        visibility_roles: List[str],
        visibility_scopes: List[str],
        tags: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Split text into chunks and prepare chunk data for database insertion.
        
        Args:
            text: Full text content to chunk
            document_id: Parent document UUID
            tenant_id: Tenant identifier
            language: Language code
            visibility_roles: Access control roles (inherited from document)
            visibility_scopes: Access control scopes (inherited from document)
            tags: Metadata tags (inherited from document)
            
        Returns:
            List of chunk data dictionaries ready for database insertion
        """
        if not text or not text.strip():
            return []
        
        # Split text into chunks
        chunk_texts = self._split_text(text)
        
        if not chunk_texts:
            return []
        
        logger.info(f"Split text into {len(chunk_texts)} chunks")
        
        # Prepare chunk data for database insertion
        chunks_data = []
        offset = 0
        
        for i, chunk_text in enumerate(chunk_texts):
            # Find the actual position of this chunk in the original text
            start_offset = text.find(chunk_text, offset)
            if start_offset == -1:
                start_offset = offset
            end_offset = start_offset + len(chunk_text)
            
            chunk_data = {
                "document_id": document_id,
                "tenant_id": tenant_id,
                "text": chunk_text,
                "language": language,
                "visibility_roles": visibility_roles,
                "visibility_scopes": visibility_scopes,
                "tags": tags or {},
                "start_offset": start_offset,
                "end_offset": end_offset,
                "embedding": None,  # Will be populated by embedding provider in PR#3
            }
            chunks_data.append(chunk_data)
            
            # Move offset forward for next search (accounting for overlap)
            offset = max(offset, end_offset - self.chunk_overlap)
        
        return chunks_data
    
    def _split_text(self, text: str) -> List[str]:
        """
        Split text into chunks of approximately chunk_size characters.
        
        Tries to break at sentence boundaries when possible.
        
        Args:
            text: Text to split
            
        Returns:
            List of text chunks
        """
        if len(text) <= self.chunk_size:
            return [text.strip()] if text.strip() else []
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Determine end position
            end = min(start + self.chunk_size, len(text))
            
            # If we're not at the end, try to find a good break point
            if end < len(text):
                # Look for paragraph break (double newline) first
                paragraph_break = text.rfind('\n\n', start, end)
                if paragraph_break > start + self.chunk_size // 2:
                    end = paragraph_break
                else:
                    # Look for single newline
                    newline_break = text.rfind('\n', start, end)
                    if newline_break > start + self.chunk_size // 2:
                        end = newline_break
                    else:
                        # Look for sentence ending
                        sentence_end = self._find_sentence_end(text, start, end)
                        if sentence_end > start + self.chunk_size // 2:
                            end = sentence_end + 1  # Include the punctuation
                        else:
                            # Look for space (word boundary)
                            space_break = text.rfind(' ', start, end)
                            if space_break > start + self.chunk_size // 2:
                                end = space_break
            
            # Extract chunk
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                chunks.append(chunk_text)
            
            # Move start position forward, accounting for overlap
            if end >= len(text):
                break
            
            # Calculate next start position
            start = end - self.chunk_overlap
            if start <= 0 or (chunks and start < len(text) - len(chunks[-1])):
                start = end  # Prevent infinite loop
        
        return chunks
    
    def _find_sentence_end(self, text: str, start: int, end: int) -> int:
        """
        Find the position of the last sentence ending in the range.
        
        Args:
            text: Full text
            start: Start position to search from
            end: End position to search to
            
        Returns:
            Position of last sentence ending, or start-1 if none found
        """
        best_pos = start - 1
        
        for pos in range(end - 1, start + self.chunk_size // 2 - 1, -1):
            if pos < len(text) and text[pos] in self.SENTENCE_ENDINGS:
                # Check if this looks like a sentence ending (not abbreviation)
                if pos + 1 >= len(text):
                    return pos
                next_char = text[pos + 1] if pos + 1 < len(text) else ' '
                if next_char in ' \n\t':
                    return pos
        
        return best_pos
