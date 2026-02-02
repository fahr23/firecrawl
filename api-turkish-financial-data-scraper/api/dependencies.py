"""
Shared dependencies for FastAPI routes
"""
from functools import lru_cache
from database.db_manager import DatabaseManager
from config import config


@lru_cache()
def get_db_manager() -> DatabaseManager:
    """Get database manager singleton"""
    return DatabaseManager()


def get_config():
    """Get application config"""
    return config
