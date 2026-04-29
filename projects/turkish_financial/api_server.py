"""
Standalone API server startup script
"""
import os
import uvicorn
import logging
from utils.logger import setup_logging

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Use environment variable or default to 8001 (to avoid conflict with Docker's 8000)
    port = int(os.getenv("API_PORT", "8001"))
    
    logger.info("Starting Turkish Financial Data Scraper API Server...")
    logger.info(f"API Documentation: http://localhost:{port}/docs")
    logger.info(f"Health Check: http://localhost:{port}/api/v1/health")
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
