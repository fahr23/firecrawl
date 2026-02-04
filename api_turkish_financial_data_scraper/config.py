"""
Configuration management for Turkish Financial Data Scraper
"""
import os
from typing import Dict, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class DatabaseConfig(BaseModel):
    """Database configuration"""
    host: str = Field(default_factory=lambda: os.getenv("APP_DB_HOST", "localhost"))
    port: int = Field(default_factory=lambda: int(os.getenv("APP_DB_PORT", "5432")))
    database: str = Field(default_factory=lambda: os.getenv("APP_DB_NAME", "backtofuture"))
    user: str = Field(default_factory=lambda: os.getenv("APP_DB_USER", "backtofuture"))
    password: str = Field(default_factory=lambda: os.getenv("APP_DB_PASSWORD", "back2future"))
    schema: str = Field(default_factory=lambda: os.getenv("DB_SCHEMA", "turkish_financial"))
    pool_size: int = Field(default=20)
    
    def get_connection_string(self) -> str:
        """Get database connection string"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    def get_connection_params(self) -> Dict:
        """Get database connection parameters"""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password
        }


class FirecrawlConfig(BaseModel):
    """Firecrawl API configuration"""
    api_key: str = ""
    base_url: Optional[str] = None
    wait_for: int = Field(default=3000, description="Wait time for JS rendering (ms)")
    timeout: int = Field(default=30000, description="Request timeout (ms)")
    formats: list[str] = Field(default=["markdown", "html"])
    max_retries: int = Field(default=3)
    retry_backoff: int = Field(default=2)


class ScraperConfig(BaseModel):
    """General scraper configuration"""
    max_concurrent_tasks: int = Field(default=10)
    rate_limit_per_minute: int = Field(default=30)
    request_timeout: int = Field(default=30)
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )


class LoggingConfig(BaseModel):
    """Logging configuration"""
    level: str = Field(default="INFO")
    log_file: str = Field(default="logs/scraper.log")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


class Config:
    """Main configuration class"""
    
    def __init__(self):
        self.database = DatabaseConfig(
            host=os.getenv("APP_DB_HOST", "localhost"),
            port=int(os.getenv("APP_DB_PORT", "5432")),
            database=os.getenv("APP_DB_NAME", "backtofuture"),
            user=os.getenv("APP_DB_USER", "backtofuture"),
            password=os.getenv("APP_DB_PASSWORD", "back2future"),
            schema=os.getenv("DB_SCHEMA", "turkish_financial"),
        )
        
        self.firecrawl = FirecrawlConfig(
            api_key=os.getenv("FIRECRAWL_API_KEY", ""),
            base_url=os.getenv("FIRECRAWL_BASE_URL"),
            wait_for=int(os.getenv("FIRECRAWL_WAIT_FOR", "3000")),
            timeout=int(os.getenv("FIRECRAWL_TIMEOUT", "30000")),
            formats=os.getenv("FIRECRAWL_FORMATS", "markdown,html").split(","),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            retry_backoff=int(os.getenv("RETRY_BACKOFF_FACTOR", "2")),
        )
        
        self.scraper = ScraperConfig(
            max_concurrent_tasks=int(os.getenv("MAX_CONCURRENT_TASKS", "10")),
            rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")),
            request_timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
        )
        
        self.logging = LoggingConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            log_file=os.getenv("LOG_FILE", "logs/scraper.log"),
        )
    
    def validate(self) -> bool:
        """Validate configuration"""
        # API key is optional for self-hosted instances with base_url
        if not self.firecrawl.api_key and not self.firecrawl.base_url:
            raise ValueError(
                "Either FIRECRAWL_API_KEY or FIRECRAWL_BASE_URL is required"
            )
        return True


# Global config instance
config = Config()
