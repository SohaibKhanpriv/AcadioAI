"""Content extraction service for document processing."""
import asyncio
import base64
import json
import logging
import os
import re
import time
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)


class ContentExtractor:
    """
    Extracts text content from various sources.
    
    Supported content types:
    - text: Plain text content (returned as-is)
    - blob/url: Downloads file and extracts text (supports PDF via PyMuPDF)
    """
    
    # Supported file extensions for PDF extraction
    PDF_EXTENSIONS = {'.pdf'}
    
    # Timeout for HTTP requests (seconds)
    HTTP_TIMEOUT = 60
    
    # Maximum file size to download (120MB)
    MAX_FILE_SIZE = 120 * 1024 * 1024
    
    def __init__(self):
        from app.core.config import settings
        self.settings = settings

    async def extract(
        self,
        content_type: str,
        content_value: str,
        language: Optional[str] = None,
    ) -> str:
        """
        Extract text content from the given source.
        
        Args:
            content_type: Type of content ("text" or "blob"/"url")
            content_value: The content itself or URL to download
            
        Returns:
            Extracted text content
            
        Raises:
            ValueError: If content type is unsupported or extraction fails
        """
        if content_type == "text":
            return self._extract_text(content_value)
        elif content_type in ("blob", "url"):
            return await self._extract_from_url(content_value, language=language)
        else:
            raise ValueError(f"Unsupported content type: {content_type}")
    
    def _extract_text(self, content: str) -> str:
        """
        Extract text from plain text content.
        Simply returns the content after basic normalization.
        """
        if not content:
            return ""
        
        # Basic normalization
        text = content.strip()
        
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove excessive whitespace while preserving paragraph structure
        lines = text.split('\n')
        normalized_lines = []
        for line in lines:
            # Collapse multiple spaces within a line
            normalized_line = ' '.join(line.split())
            normalized_lines.append(normalized_line)
        
        # Remove more than 2 consecutive empty lines
        result = []
        empty_count = 0
        for line in normalized_lines:
            if line == '':
                empty_count += 1
                if empty_count <= 2:
                    result.append(line)
            else:
                empty_count = 0
                result.append(line)
        
        return '\n'.join(result)
    
    async def _extract_from_url(self, url: str, language: Optional[str] = None) -> str:
        """
        Download file from URL and extract text content.
        
        Currently supports:
        - PDF files (via PyMuPDF)
        - Plain text files
        """
        logger.info(f"Downloading content from: {url}")
        
        # Download the file
        file_content, content_type = await self._download_file(url)
        
        # Determine file type from URL
        file_ext = self._get_file_extension(url)
        
        is_pdf_by_content_type = bool(content_type and "application/pdf" in content_type.lower())
        if file_ext in self.PDF_EXTENSIONS or is_pdf_by_content_type:
            return await self._extract_pdf(file_content, language=language)
        else:
            # Try to decode as text
            try:
                return self._extract_text(file_content.decode('utf-8'))
            except UnicodeDecodeError:
                # Try other encodings
                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        return self._extract_text(file_content.decode(encoding))
                    except UnicodeDecodeError:
                        continue
                raise ValueError(f"Unable to decode file content from {url}")
    
    async def _download_file(self, url: str) -> Tuple[bytes, str]:
        """
        Download a file from the given URL.
        
        Args:
            url: URL to download from
            
        Returns:
            (File content as bytes, response content-type)
            
        Raises:
            ValueError: If download fails or file is too large
        """
        try:
            return await self._download_file_once(url)
        except ValueError as first_error:
            # Common containerized case:
            # API stores upload URL as localhost, but worker runs in another container.
            fallback_url = self._build_container_fallback_url(url)
            if fallback_url and fallback_url != url:
                logger.warning(
                    f"Primary download failed for {url}; retrying via container host {fallback_url}"
                )
                try:
                    return await self._download_file_once(fallback_url)
                except ValueError:
                    pass
            raise first_error

    async def _download_file_once(self, url: str) -> Tuple[bytes, str]:
        """Download file once, without fallback retries."""
        try:
            async with httpx.AsyncClient(timeout=self.HTTP_TIMEOUT) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                
                # Check content length
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > self.MAX_FILE_SIZE:
                    raise ValueError(f"File too large: {content_length} bytes")
                
                content = response.content
                
                if len(content) > self.MAX_FILE_SIZE:
                    raise ValueError(f"File too large: {len(content)} bytes")
                
                logger.info(f"Downloaded {len(content)} bytes from {url}")
                return content, response.headers.get("content-type", "")
                
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to download file from {url}: {str(e)}")

    def _build_container_fallback_url(self, url: str) -> Optional[str]:
        """
        Build a Docker-network fallback URL for localhost-based addresses.
        Example: http://localhost:8000/uploads/x.pdf -> http://acadlo-ai-core:8000/uploads/x.pdf
        """
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            if host not in {"localhost", "127.0.0.1"}:
                return None

            netloc = "acadlo-ai-core"
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            fallback = parsed._replace(netloc=netloc)
            return urlunparse(fallback)
        except Exception:
            return None
    
    def _get_file_extension(self, url: str) -> str:
        """Extract file extension from URL."""
        from urllib.parse import urlparse
        path = urlparse(url).path
        ext = os.path.splitext(path)[1].lower()
        return ext
    
    async def _extract_pdf(self, content: bytes, language: Optional[str] = None) -> str:
        """
        Extract text from PDF content using PyMuPDF.
        For pages with visuals, optionally enrich with vision-based notes.
        
        Args:
            content: PDF file content as bytes
            
        Returns:
            Extracted text
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ValueError("PyMuPDF (fitz) is required for PDF extraction")
        
        logger.info("Extracting text from PDF with page-wise processing")
        doc = fitz.open(stream=content, filetype="pdf")
        text_parts = []

        try:
            page_count = len(doc)
            # Always extract text from all pages so retrieval coverage is complete.
            # Limit only the expensive vision enrichment pass.
            max_vision_pages = max(0, int(self.settings.MULTIMODAL_MAX_PDF_PAGES))
            if max_vision_pages and page_count > max_vision_pages:
                logger.warning(
                    f"PDF has {page_count} pages; vision enrichment limited to first "
                    f"{max_vision_pages} pages (MULTIMODAL_MAX_PDF_PAGES). "
                    "Text extraction will still run for all pages."
                )

            # Throttle vision calls to avoid per-minute rate limit bursts.
            pages_per_minute = max(1, int(self.settings.MULTIMODAL_VISION_PAGES_PER_MINUTE))
            vision_calls_in_window = 0
            vision_window_started_at = time.monotonic()

            for page_idx in range(page_count):
                page = doc[page_idx]
                page_no = page_idx + 1
                page_text = page.get_text("text").strip()
                page_text = self._extract_text(page_text) if page_text else ""

                page_block = [f"[PAGE {page_no}]"]
                if page_text:
                    page_block.append(page_text)

                can_run_vision_for_page = (
                    self.settings.MULTIMODAL_INGESTION_ENABLED
                    and self._page_has_images(page)
                    and (max_vision_pages == 0 or page_no <= max_vision_pages)
                )
                if can_run_vision_for_page:
                    if vision_calls_in_window >= pages_per_minute:
                        elapsed = time.monotonic() - vision_window_started_at
                        wait_seconds = max(0.0, 60.0 - elapsed)
                        if wait_seconds > 0:
                            logger.info(
                                f"Vision pacing: processed {vision_calls_in_window} pages in current minute; "
                                f"waiting {wait_seconds:.1f}s before continuing"
                            )
                            await asyncio.sleep(wait_seconds)
                        vision_calls_in_window = 0
                        vision_window_started_at = time.monotonic()

                    visual_note = await self._analyze_page_visuals(
                        page=page,
                        page_number=page_no,
                        language=language or "en-US",
                        page_text=page_text,
                    )
                    vision_calls_in_window += 1
                    if visual_note:
                        page_block.append(visual_note)

                text_parts.append("\n".join(page_block).strip())
                logger.debug(f"Page {page_no}: base_text={len(page_text)} chars")

            full_text = "\n\n".join([p for p in text_parts if p])
            logger.info(f"Extracted {len(full_text)} characters from {len(text_parts)} pages")
            return self._extract_text(full_text)
        finally:
            doc.close()

    def _page_has_images(self, page) -> bool:
        """Return True if a PDF page contains embedded images."""
        try:
            return len(page.get_images(full=True)) > 0
        except Exception:
            return False

    async def _analyze_page_visuals(
        self,
        *,
        page,
        page_number: int,
        language: str,
        page_text: str,
    ) -> Optional[str]:
        """
        Analyze page visuals with a vision model and return a concise enrichment note.

        Returns None on any failure or when visuals are not relevant.
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.warning("openai package not available for multimodal vision enrichment")
            return None

        try:
            import fitz  # type: ignore
        except ImportError:
            return None

        try:
            scale = float(self.settings.MULTIMODAL_PDF_RENDER_SCALE)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        except Exception:
            # Fallback: default render
            pix = page.get_pixmap(alpha=False)

        image_b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
        prompt = (
            "You analyze textbook page visuals for ingestion quality.\n"
            "Return ONLY valid JSON with fields:\n"
            "{"
            "\"has_relevant_visual\": true|false, "
            "\"image_summary\": \"...\", "
            "\"teaching_intent\": \"...\", "
            "\"relevance_to_text\": \"high|medium|low\", "
            "\"embedded_image_text\": \"...\""
            "}\n"
            "Rules:\n"
            "- Focus on whether visuals help understand the written text.\n"
            "- For kids books, capture what concept the visual is teaching.\n"
            "- Do not hallucinate.\n"
            f"- Page language hint: {language}\n"
            f"- Page text excerpt: {page_text[:1500] if page_text else '(no extracted text)'}"
        )

        client = AsyncOpenAI(api_key=self.settings.get_llm_api_key())
        try:
            response = None
            retries = max(0, int(self.settings.MULTIMODAL_VISION_RATE_LIMIT_RETRIES))
            base_backoff = max(0.1, float(self.settings.MULTIMODAL_VISION_RETRY_BASE_SECONDS))

            for attempt in range(retries + 1):
                try:
                    response = await client.chat.completions.create(
                        model=self.settings.MULTIMODAL_VISION_MODEL,
                        messages=[
                            {"role": "system", "content": "You are a precise multimodal extraction assistant."},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                                    },
                                ],
                            },
                        ],
                    )
                    break
                except Exception as e:
                    err_text = str(e)
                    is_rate_limit = ("rate_limit_exceeded" in err_text.lower()) or ("error code: 429" in err_text.lower())
                    if not is_rate_limit or attempt >= retries:
                        raise

                    retry_after = self._extract_retry_after_seconds(err_text)
                    # Keep retries conservative: tiny retry_after hints (e.g. 300ms)
                    # can still hit the same TPM window repeatedly.
                    suggested_backoff = retry_after if retry_after is not None else 0.0
                    backoff = max(suggested_backoff, base_backoff * (2 ** attempt))
                    logger.warning(
                        f"Vision rate limited on page {page_number}; retry {attempt + 1}/{retries} "
                        f"after {backoff:.2f}s"
                    )
                    await asyncio.sleep(backoff)

            if response is None:
                return None
        except Exception as e:
            logger.warning(f"Vision analysis failed for page {page_number}: {e}")
            return None
        finally:
            await client.close()

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            return None

        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                return None
            data = json.loads(raw[start:end + 1])
        except Exception:
            logger.warning(f"Vision response parse failed on page {page_number}")
            return None

        if not data.get("has_relevant_visual"):
            return None

        relevance = str(data.get("relevance_to_text", "low")).lower()
        if relevance == "low":
            return None

        summary = str(data.get("image_summary", "")).strip()
        intent = str(data.get("teaching_intent", "")).strip()
        embedded_text = str(data.get("embedded_image_text", "")).strip()

        note_parts = [f"[PAGE {page_number} VISUAL NOTE]"]
        if summary:
            note_parts.append(f"Image summary: {summary}")
        if intent:
            note_parts.append(f"Teaching intent: {intent}")
        if embedded_text and embedded_text.lower() not in {"none", "n/a", "null", ""}:
            note_parts.append(f"Text inside image: {embedded_text}")

        if len(note_parts) <= 1:
            return None
        return "\n".join(note_parts)

    def _extract_retry_after_seconds(self, error_text: str) -> Optional[float]:
        """Extract retry delay seconds from provider error text if present."""
        if not error_text:
            return None
        match_ms = re.search(r"try again in\s+(\d+)\s*ms", error_text, flags=re.IGNORECASE)
        if match_ms:
            return max(0.05, float(match_ms.group(1)) / 1000.0)

        match_s = re.search(r"try again in\s+(\d+(?:\.\d+)?)\s*s", error_text, flags=re.IGNORECASE)
        if match_s:
            return max(0.05, float(match_s.group(1)))
        return None
