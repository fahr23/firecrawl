"""
PDF Downloader utility

Provides async PDF download with retries and integrates with TextExtractorFactory
for text extraction and saving alongside the PDF.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

import aiohttp

from .text_extractor import TextExtractorFactory

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    success: bool
    pdf_path: Optional[str] = None
    text_path: Optional[str] = None
    extracted_text: Optional[str] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    attempts: int = 0
    error: Optional[str] = None


class PDFDownloader:
    """Async PDF downloader with retry and text extraction support."""

    def __init__(
        self,
        download_dir: Path,
        text_dir: Path,
        extractor_factory: TextExtractorFactory,
        max_attempts: int = 3,
        backoff_initial: float = 2.0,
        timeout_seconds: float = 60.0,
        user_agent: str = "Mozilla/5.0 (compatible; KAPScraper/1.0)"
    ) -> None:
        self.download_dir = Path(download_dir)
        self.text_dir = Path(text_dir)
        self.extractor_factory = extractor_factory
        self.max_attempts = max_attempts
        self.backoff_initial = backoff_initial
        self.timeout_seconds = timeout_seconds
        self.headers = {"User-Agent": user_agent}

        # Ensure directories exist
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.text_dir.mkdir(parents=True, exist_ok=True)

    async def download_and_extract(
        self,
        pdf_url: str,
        filename: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Dict[str, Any]:
        """
        Download a PDF and extract its text.

        Args:
            pdf_url: URL to the PDF file
            filename: Optional target filename (defaults to last URL segment with .pdf)
            session: Optional aiohttp session for reuse by caller

        Returns:
            Dict compatible with KAPScraper expectations.
        """
        if not filename:
            filename = pdf_url.split("/")[-1] or "document.pdf"
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"
        # Normalize filename (no spaces)
        filename = filename.replace(" ", "_")

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        created_session = False

        # Retry loop
        delay = self.backoff_initial
        last_error: Optional[str] = None
        content_type: Optional[str] = None
        content_len: Optional[int] = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                if session is None:
                    session = aiohttp.ClientSession(timeout=timeout, headers=self.headers)
                    created_session = True

                async with session.get(pdf_url) as resp:
                    status = resp.status
                    if status != 200:
                        last_error = f"HTTP {status}"
                        raise aiohttp.ClientResponseError(
                            request_info=resp.request_info,
                            history=resp.history,
                            status=status,
                            message=f"Failed to download PDF: {status}",
                            headers=resp.headers,
                        )

                    content_type = resp.headers.get("Content-Type", "")
                    content_len_str = resp.headers.get("Content-Length")
                    content_len = int(content_len_str) if content_len_str and content_len_str.isdigit() else None

                    # Basic content-type validation
                    if "pdf" not in content_type.lower():
                        logger.warning(f"Expected PDF but got Content-Type={content_type!r} from {pdf_url}")

                    pdf_bytes = await resp.read()

                # Save PDF
                pdf_path = self.download_dir / filename
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)
                logger.info(f"Downloaded PDF: {pdf_path}")

                # Extract text
                extractor = self.extractor_factory.create("pdf")
                if not extractor:
                    raise RuntimeError("PDF extractor not available")
                extracted_text = extractor.extract_text(pdf_bytes)

                # Save text
                text_filename = filename[:-4] + ".txt"
                text_path = self.text_dir / text_filename
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(extracted_text)
                logger.info(f"Extracted text saved: {text_path}")

                # Success
                result: Dict[str, Any] = {
                    "pdf_path": str(pdf_path),
                    "text_path": str(text_path),
                    "extracted_text": extracted_text,
                    "filename": filename,
                    "content_type": content_type,
                    "content_length": content_len,
                    "attempts": attempt,
                }
                return result

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Attempt {attempt}/{self.max_attempts} failed for {pdf_url}: {e}")
                if attempt < self.max_attempts:
                    await asyncio.sleep(delay)
                    delay *= 2
            finally:
                if created_session and session is not None:
                    await session.close()
                    session = None
                    created_session = False

        # If we reach here, all attempts failed
        logger.error(f"Failed to download PDF after {self.max_attempts} attempts: {pdf_url} - {last_error}")
        return {
            "success": False,
            "error": last_error,
            "filename": filename,
            "content_type": content_type,
            "content_length": content_len,
            "attempts": self.max_attempts,
        }
