"""
PDF Extraction utilities for financial reports
"""
import logging
import re
import pdfplumber
from typing import List, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


def camel_case(s: str) -> str:
    """
    Convert a string to camelCase, removing special characters
    
    Args:
        s: Input string
        
    Returns:
        camelCase string
    """
    if not s:
        return ""
    
    # Map Turkish characters to English
    turkish_to_english = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = s.translate(turkish_to_english)
    
    # Remove special characters
    s = re.sub(r'[^a-zA-Z0-9]', '', s)
    s = s.title().replace(" ", "")
    
    return s[0].lower() + s[1:] if s else ""


def extract_tables_from_pdf(pdf_path: str) -> List[List[List[str]]]:
    """
    Extract all tables from a PDF file
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        List of tables, where each table is a list of rows
    """
    tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                page_tables = page.extract_tables()
                
                if page_tables:
                    for table in page_tables:
                        if table and len(table) > 1:
                            tables.append({
                                "page": page_num,
                                "data": table
                            })
                            logger.debug(f"Extracted table from page {page_num}")
        
        logger.info(f"Extracted {len(tables)} tables from {pdf_path}")
        return tables
        
    except Exception as e:
        logger.error(f"Error extracting tables from PDF: {e}")
        return []


def table_to_dataframe(
    table: List[List[str]],
    normalize_columns: bool = True
) -> pd.DataFrame:
    """
    Convert a table to pandas DataFrame
    
    Args:
        table: Table data (list of rows)
        normalize_columns: Whether to normalize column names
        
    Returns:
        pandas DataFrame
    """
    if not table or len(table) < 2:
        return pd.DataFrame()
    
    df = pd.DataFrame(table[1:], columns=table[0])
    
    if normalize_columns:
        df.columns = [
            camel_case(col.strip()) if col and col.strip() else f"column_{i}"
            for i, col in enumerate(df.columns)
        ]
    
    return df


def save_table_to_db(
    table_data: Dict[str, Any],
    db_manager,
    table_name: str,
    additional_columns: Dict[str, Any] = None
) -> bool:
    """
    Save table data to database
    
    Args:
        table_data: Table data with page and data
        db_manager: Database manager instance
        table_name: Target table name
        additional_columns: Additional columns to add
        
    Returns:
        Success status
    """
    try:
        table = table_data.get("data", [])
        df = table_to_dataframe(table)
        
        if df.empty:
            logger.warning("Empty DataFrame, skipping")
            return False
        
        # Add additional columns
        if additional_columns:
            for col, value in additional_columns.items():
                df[col] = value
        
        # Convert DataFrame to list of dicts
        records = df.to_dict('records')
        
        # Bulk insert
        return db_manager.bulk_insert(table_name, records)
        
    except Exception as e:
        logger.error(f"Error saving table to database: {e}")
        return False


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract all text from a PDF file
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Extracted text
    """
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        return text
        
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return ""


def has_images_in_page(page) -> bool:
    """
    Check if a PDF page has images
    
    Args:
        page: pdfplumber page object
        
    Returns:
        True if page has images
    """
    try:
        return len(page.images) > 0
    except Exception:
        return False
