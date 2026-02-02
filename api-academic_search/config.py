"""
Configuration management for Academic Search.

This module provides centralized configuration for API keys, 
timeouts, and other settings.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import json


@dataclass
class APIConfig:
    """Configuration for API keys and endpoints."""
    elsevier_api_key: Optional[str] = None
    semantic_scholar_api_key: Optional[str] = None
    
    def __post_init__(self):
        """Load from environment if not provided."""
        if not self.elsevier_api_key:
            self.elsevier_api_key = os.getenv(
                "ELSEVIER_API_KEY",
                "7e0c8c4ed4e0fb320d69074f093779d9"  # Default key
            )
        if not self.semantic_scholar_api_key:
            self.semantic_scholar_api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")


@dataclass
class Config:
    """
    Main configuration class for Academic Search.
    
    Configuration can be loaded from:
    - Environment variables
    - JSON config file
    - Direct initialization
    
    Example:
        >>> config = Config()  # Uses defaults and env vars
        >>> config = Config.from_file("config.json")
        >>> config = Config(enable_llm_analysis=True)
    """
    
    # API Configuration
    api: APIConfig = field(default_factory=APIConfig)
    
    # Search Settings
    max_results: int = 25
    timeout: int = 30
    enable_abstract_enrichment: bool = True
    deduplicate_results: bool = True
    
    # LLM Analysis Settings
    llm_provider: Optional[str] = None  # "openai", "anthropic", "local"
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None  # "gpt-4o-mini", "claude-3-sonnet-20240229"
    enable_llm_analysis: bool = False
    
    # Output Settings
    output_format: str = "json"  # "json", "markdown", "csv"
    
    # Debug
    debug: bool = False
    
    # Contact email for API requests (good practice)
    contact_email: str = "research@example.com"
    
    def __post_init__(self):
        """Load configuration from environment variables."""
        self._load_from_env()
    
    def _load_from_env(self):
        """Load settings from environment variables."""
        # LLM Settings
        if not self.llm_api_key:
            self.llm_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        
        if os.getenv("LLM_PROVIDER"):
            self.llm_provider = os.getenv("LLM_PROVIDER")
        
        # Contact email
        if os.getenv("ACADEMIC_SEARCH_EMAIL"):
            self.contact_email = os.getenv("ACADEMIC_SEARCH_EMAIL")
        
        # Debug
        if os.getenv("ACADEMIC_SEARCH_DEBUG"):
            self.debug = os.getenv("ACADEMIC_SEARCH_DEBUG").lower() in ("true", "1", "yes")
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        return cls()
    
    @classmethod
    def from_file(cls, filepath: str) -> "Config":
        """
        Load configuration from a JSON file.
        
        Args:
            filepath: Path to the JSON configuration file.
            
        Returns:
            Config instance with loaded settings.
        """
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Handle nested api config
        if "api" in data and isinstance(data["api"], dict):
            data["api"] = APIConfig(**data["api"])
        
        return cls(**data)
    
    @classmethod
    def load(cls, filepath: str) -> "Config":
        """Alias for from_file()."""
        return cls.from_file(filepath)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "api": {
                "elsevier_api_key": "***" if self.api.elsevier_api_key else None,
                "semantic_scholar_api_key": "***" if self.api.semantic_scholar_api_key else None,
            },
            "max_results": self.max_results,
            "timeout": self.timeout,
            "enable_abstract_enrichment": self.enable_abstract_enrichment,
            "llm_provider": self.llm_provider,
            "enable_llm_analysis": self.enable_llm_analysis,
            "debug": self.debug,
        }
    
    def save(self, filepath: str):
        """Save configuration to JSON file (excludes sensitive keys)."""
        data = {
            "max_results": self.max_results,
            "timeout": self.timeout,
            "enable_abstract_enrichment": self.enable_abstract_enrichment,
            "deduplicate_results": self.deduplicate_results,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "enable_llm_analysis": self.enable_llm_analysis,
            "output_format": self.output_format,
            "contact_email": self.contact_email,
            "debug": self.debug,
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
