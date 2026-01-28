"""
FastAPI application for Turkish Financial Data Scraper REST API
"""
import logging
import json
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.routers import scrapers, reports, health, sentiment
from utils.logger import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Request/Response logging middleware
class RequestResponseLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Log request
        logger.info(f"\n{'='*80}")
        logger.info(f"📥 INCOMING REQUEST")
        logger.info(f"   Method: {request.method}")
        logger.info(f"   Path: {request.url.path}")
        logger.info(f"   Query: {request.url.query}")
        
        # Log request body if present
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    try:
                        body_json = json.loads(body)
                        logger.info(f"   Payload: {json.dumps(body_json, indent=6)}")
                    except:
                        logger.info(f"   Body: {body.decode()}")
            except:
                pass
        
        # Measure response time
        start_time = time.time()
        
        # Get response
        response = await call_next(request)
        
        process_time = time.time() - start_time
        
        # Log response
        logger.info(f"\n📤 OUTGOING RESPONSE")
        logger.info(f"   Status Code: {response.status_code}")
        logger.info(f"   Process Time: {process_time:.3f}s")
        
        # Try to read response body
        try:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            try:
                body_json = json.loads(body)
                logger.info(f"   Payload: {json.dumps(body_json, indent=6)}")
            except:
                logger.info(f"   Body: {body.decode()[:500]}")
            
            # Return response with body
            from starlette.responses import Response
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
        except Exception as e:
            logger.info(f"   (Response body logging skipped)")
        
        logger.info(f"{'='*80}")
        
        return response

# Create FastAPI app
app = FastAPI(
    title="Turkish Financial Data Scraper API",
    description="REST API for scraping and analyzing Turkish financial data from KAP, BIST, and TradingView with AI-powered sentiment analysis",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add request/response logging middleware
app.add_middleware(RequestResponseLoggerMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(scrapers.router)
app.include_router(reports.router)
app.include_router(sentiment.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Turkish Financial Data Scraper API with AI Sentiment Analysis",
        "version": "1.1.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "sentiment_api": "/api/v1/sentiment/",
        "documentation": "See API_DOCUMENTATION.md for detailed usage guide"
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
