"""
Shared dependencies for FastAPI routes
"""
from threading import Lock
from database.db_manager import DatabaseManager
from config import config

_db_manager: DatabaseManager | None = None
_db_manager_lock = Lock()

def get_db_manager() -> DatabaseManager:
    """Get a process-wide database manager singleton safely."""
    global _db_manager

    if _db_manager is None:
        with _db_manager_lock:
            if _db_manager is None:
                _db_manager = DatabaseManager()

    return _db_manager


def get_config():
    """Get application config"""
    return config
