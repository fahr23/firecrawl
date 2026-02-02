"""
Export modules for saving search results.

This module provides various export formats for academic search results.
"""

import json
import csv
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from .base import BaseExporter
from .models import SearchResult, Article
from .config import Config


class JSONExporter(BaseExporter):
    """Export search results to JSON format."""
    
    def __init__(self, config: Config, indent: int = 2, 
                 include_metadata: bool = True):
        """
        Initialize JSON exporter.
        
        Args:
            config: Configuration object.
            indent: JSON indentation level.
            include_metadata: Include search metadata in output.
        """
        super().__init__(config)
        self.indent = indent
        self.include_metadata = include_metadata
    
    @property
    def format_name(self) -> str:
        return "JSON"
    
    @property
    def file_extension(self) -> str:
        return "json"
    
    def export(self, result: SearchResult, filepath: str) -> str:
        """
        Export results to JSON file.
        
        Args:
            result: SearchResult to export.
            filepath: Output file path.
            
        Returns:
            Path to the created file.
        """
        filepath = self._ensure_extension(filepath)
        
        data = {
            "articles": [a.to_dict() for a in result.articles]
        }
        
        if self.include_metadata:
            data["metadata"] = {
                "query": result.query,
                "total_found": result.total_found,
                "sources": result.sources,
                "exported_count": len(result.articles),
                "export_time": datetime.now().isoformat(),
                "articles_with_abstracts": sum(
                    1 for a in result.articles if a.abstract
                )
            }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=self.indent, ensure_ascii=False)
        
        self.logger.info(f"Exported {len(result.articles)} articles to {filepath}")
        return filepath
    
    def export_to_string(self, result: SearchResult) -> str:
        """Export results to JSON string."""
        data = {
            "articles": [a.to_dict() for a in result.articles]
        }
        
        if self.include_metadata:
            data["metadata"] = {
                "query": result.query,
                "total_found": result.total_found,
                "sources": result.sources,
                "exported_count": len(result.articles)
            }
        
        return json.dumps(data, indent=self.indent, ensure_ascii=False)


class CSVExporter(BaseExporter):
    """Export search results to CSV format."""
    
    DEFAULT_FIELDS = [
        'title', 'authors', 'year', 'journal', 'doi', 
        'abstract', 'url', 'source', 'keywords'
    ]
    
    def __init__(self, config: Config, fields: Optional[List[str]] = None,
                 include_abstract: bool = True):
        """
        Initialize CSV exporter.
        
        Args:
            config: Configuration object.
            fields: List of fields to include. Uses defaults if None.
            include_abstract: Whether to include abstracts.
        """
        super().__init__(config)
        self.fields = fields or self.DEFAULT_FIELDS.copy()
        
        if not include_abstract and 'abstract' in self.fields:
            self.fields.remove('abstract')
    
    @property
    def format_name(self) -> str:
        return "CSV"
    
    @property
    def file_extension(self) -> str:
        return "csv"
    
    def export(self, result: SearchResult, filepath: str) -> str:
        """
        Export results to CSV file.
        
        Args:
            result: SearchResult to export.
            filepath: Output file path.
            
        Returns:
            Path to the created file.
        """
        filepath = self._ensure_extension(filepath)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.fields)
            writer.writeheader()
            
            for article in result.articles:
                row = {}
                for field in self.fields:
                    value = getattr(article, field, '')
                    if isinstance(value, list):
                        value = '; '.join(value)
                    row[field] = value
                writer.writerow(row)
        
        self.logger.info(f"Exported {len(result.articles)} articles to {filepath}")
        return filepath


class MarkdownExporter(BaseExporter):
    """Export search results to Markdown format."""
    
    def __init__(self, config: Config, include_abstracts: bool = True,
                 include_toc: bool = True, max_abstract_length: int = 500):
        """
        Initialize Markdown exporter.
        
        Args:
            config: Configuration object.
            include_abstracts: Include abstracts in output.
            include_toc: Include table of contents.
            max_abstract_length: Maximum abstract length (0 for no limit).
        """
        super().__init__(config)
        self.include_abstracts = include_abstracts
        self.include_toc = include_toc
        self.max_abstract_length = max_abstract_length
    
    @property
    def format_name(self) -> str:
        return "Markdown"
    
    @property
    def file_extension(self) -> str:
        return "md"
    
    def export(self, result: SearchResult, filepath: str) -> str:
        """
        Export results to Markdown file.
        
        Args:
            result: SearchResult to export.
            filepath: Output file path.
            
        Returns:
            Path to the created file.
        """
        filepath = self._ensure_extension(filepath)
        content = self._format_result(result)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        self.logger.info(f"Exported {len(result.articles)} articles to {filepath}")
        return filepath
    
    def export_to_string(self, result: SearchResult) -> str:
        """Export results to Markdown string."""
        return self._format_result(result)
    
    def _format_result(self, result: SearchResult) -> str:
        """Format search result as Markdown."""
        lines = []
        
        # Header
        lines.append(f"# Academic Literature Search Results")
        lines.append("")
        lines.append(f"**Query:** {result.query}")
        lines.append(f"**Total Found:** {result.total_found:,}")
        lines.append(f"**Sources:** {', '.join(result.sources)}")
        lines.append(f"**Articles Retrieved:** {len(result.articles)}")
        
        with_abstracts = sum(1 for a in result.articles if a.abstract)
        lines.append(f"**With Abstracts:** {with_abstracts}")
        lines.append(f"**Export Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Table of Contents
        if self.include_toc and result.articles:
            lines.append("## Table of Contents")
            lines.append("")
            for i, article in enumerate(result.articles, 1):
                safe_title = article.title[:60] + "..." if len(article.title) > 60 else article.title
                anchor = f"article-{i}"
                lines.append(f"{i}. [{safe_title}](#{anchor})")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # Articles
        lines.append("## Articles")
        lines.append("")
        
        for i, article in enumerate(result.articles, 1):
            lines.append(f"### {i}. {article.title}")
            lines.append(f"<a name='article-{i}'></a>")
            lines.append("")
            
            # Metadata
            if article.authors:
                lines.append(f"**Authors:** {article.authors}")
            if article.year:
                lines.append(f"**Year:** {article.year}")
            if article.journal:
                lines.append(f"**Journal:** {article.journal}")
            if article.doi:
                lines.append(f"**DOI:** [{article.doi}](https://doi.org/{article.doi})")
            if article.url:
                lines.append(f"**URL:** [{article.url}]({article.url})")
            lines.append(f"**Source:** {article.source}")
            
            if article.keywords:
                lines.append(f"**Keywords:** {', '.join(article.keywords)}")
            
            # Abstract
            if self.include_abstracts and article.abstract:
                lines.append("")
                lines.append("**Abstract:**")
                lines.append("")
                abstract = article.abstract
                if self.max_abstract_length > 0 and len(abstract) > self.max_abstract_length:
                    abstract = abstract[:self.max_abstract_length] + "..."
                lines.append(f"> {abstract}")
            
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)


class BibTeXExporter(BaseExporter):
    """Export search results to BibTeX format."""
    
    @property
    def format_name(self) -> str:
        return "BibTeX"
    
    @property
    def file_extension(self) -> str:
        return "bib"
    
    def export(self, result: SearchResult, filepath: str) -> str:
        """
        Export results to BibTeX file.
        
        Args:
            result: SearchResult to export.
            filepath: Output file path.
            
        Returns:
            Path to the created file.
        """
        filepath = self._ensure_extension(filepath)
        
        entries = []
        for article in result.articles:
            entry = article.to_bibtex()
            if entry:
                entries.append(entry)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n\n".join(entries))
        
        self.logger.info(f"Exported {len(entries)} articles to {filepath}")
        return filepath
    
    def export_to_string(self, result: SearchResult) -> str:
        """Export results to BibTeX string."""
        entries = []
        for article in result.articles:
            entry = article.to_bibtex()
            if entry:
                entries.append(entry)
        return "\n\n".join(entries)


class RISExporter(BaseExporter):
    """Export search results to RIS (Research Information Systems) format."""
    
    @property
    def format_name(self) -> str:
        return "RIS"
    
    @property
    def file_extension(self) -> str:
        return "ris"
    
    def export(self, result: SearchResult, filepath: str) -> str:
        """
        Export results to RIS file.
        
        Args:
            result: SearchResult to export.
            filepath: Output file path.
            
        Returns:
            Path to the created file.
        """
        filepath = self._ensure_extension(filepath)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for article in result.articles:
                f.write(self._format_ris_entry(article))
                f.write("\n")
        
        self.logger.info(f"Exported {len(result.articles)} articles to {filepath}")
        return filepath
    
    def _format_ris_entry(self, article: Article) -> str:
        """Format article as RIS entry."""
        lines = ["TY  - JOUR"]  # Journal Article
        
        lines.append(f"TI  - {article.title}")
        
        # Authors
        for author in (article.authors or "").split(", "):
            if author.strip():
                lines.append(f"AU  - {author.strip()}")
        
        if article.year:
            lines.append(f"PY  - {article.year}")
        
        if article.journal:
            lines.append(f"JO  - {article.journal}")
        
        if article.doi:
            lines.append(f"DO  - {article.doi}")
        
        if article.url:
            lines.append(f"UR  - {article.url}")
        
        if article.abstract:
            lines.append(f"AB  - {article.abstract}")
        
        for keyword in article.keywords:
            lines.append(f"KW  - {keyword}")
        
        lines.append("ER  -")  # End of Reference
        
        return "\n".join(lines)
