"""
Standalone API server startup script
"""
import uvicorn
import logging
from utils.logger import setup_logging

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Turkish Financial Data Scraper API Server...")
    logger.info("API Documentation: http://localhost:8000/docs")
    logger.info("Health Check: http://localhost:8000/api/v1/health")
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
