"""
Health check endpoints
"""
import logging
from fastapi import APIRouter, Depends
from api.models import HealthResponse
from api.dependencies import get_db_manager
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Health check endpoint
    
    Returns:
    - API status
    - Database connection status
    """
    db_status = "disconnected"
    
    try:
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            db_status = "connected"
        finally:
            db_manager.return_connection(conn)
    except DatabaseManager.PoolExhaustedError as e:
        logger.warning(f"Database connection pool exhausted during health check: {e}")
        db_status = "error: connection pool exhausted"
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        db_status = f"error: {str(e)}"
    
    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        database=db_status
    )
