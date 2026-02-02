"""
Text Extraction utilities using Strategy Pattern
Supports PDF and other document formats
"""
import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import tempfile
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class TextExtractor(ABC):
    """Abstract base class for text extraction strategies"""
    
    @abstractmethod
    def extract_text(self, content: bytes) -> str:
        """
        Extract text from document content
        
        Args:
            content: Raw document bytes
            
        Returns:
            Extracted and normalized text
        """
        pass
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize unicode characters and clean text
        
        Args:
            text: Raw extracted text
            
        Returns:
            Normalized text
        """
        # Normalize unicode characters
        text = unicodedata.normalize('NFKD', text)
        # Replace specific unwanted characters
        text = text.replace("൴", "i")
        # Remove non-ASCII characters and extra spaces
        text = re.sub(r'[^\x00-\x7F]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


class PDFTextExtractor(TextExtractor):
    """PDF text extraction using PyMuPDF"""
    
    def extract_text(self, content: bytes) -> str:
        """
        Extract text from PDF content
        
        Args:
            content: PDF file bytes
            
        Returns:
            Extracted text
        """
        try:
            # Use temporary file for PyMuPDF
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as temp_file:
                temp_file.write(content)
                temp_file.flush()
                
                # Open and extract text
                with fitz.open(temp_file.name) as pdf_document:
                    extracted_text = ""
                    for page_num in range(len(pdf_document)):
                        page = pdf_document.load_page(page_num)
                        extracted_text += page.get_text()
                    
                    return self.normalize_text(extracted_text)
                    
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return ""


class TextExtractorFactory:
    """Factory for creating text extractors based on content type"""
    
    _extractors = {
        'application/pdf': PDFTextExtractor,
        'pdf': PDFTextExtractor,
    }
    
    @classmethod
    def create(cls, content_type: str) -> Optional[TextExtractor]:
        """
        Create appropriate text extractor for content type
        
        Args:
            content_type: MIME type or file extension
            
        Returns:
            TextExtractor instance or None
        """
        content_type = content_type.lower()
        extractor_class = cls._extractors.get(content_type)
        
        if extractor_class:
            return extractor_class()
        
        logger.warning(f"No extractor found for content type: {content_type}")
        return None
    
    @classmethod
    def register_extractor(cls, content_type: str, extractor_class: type):
        """
        Register a new extractor type
        
        Args:
            content_type: MIME type or file extension
            extractor_class: TextExtractor subclass
        """
        cls._extractors[content_type] = extractor_class
