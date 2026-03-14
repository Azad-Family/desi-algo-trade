"""
AI Trading Agent - Main FastAPI Application

This is the entry point for the application. It orchestrates all the modules:
- database: MongoDB connection
- models: Pydantic models and enums
- stock_data: stock universe data
- ai_engine: AI analysis and recommendations
- trading: Upstox trading integration
- routes: all API endpoints
"""
import logging
import os
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from database import db, close_db
from routes import api_router
from stock_init import initialize_stocks, get_stock_count

# Configure logging with console output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
    ]
)
logger = logging.getLogger(__name__)
logger.info("🚀 AI Trading Agent Server Starting...")

# Create FastAPI app
app = FastAPI(
    title="AI Trading Agent - Indian Stocks",
    description="AI-powered stock analysis and trading for Indian markets",
    version="1.0.0"
)

# ============ STARTUP & SHUTDOWN EVENTS ============
@app.on_event("startup")
async def startup_event():
    """Initialize stocks on app startup if database is empty
    
    This runs ONCE on first boot:
    - Checks if stocks collection exists
    - If empty (stock_count == 0): deletes and loads 59 stocks
    - If exists: skips initialization, keeps existing data
    
    On subsequent boots: skips this entire block (count > 0)
    """
    try:
        stock_count = await get_stock_count()
        
        if stock_count == 0:
            # Only on FIRST startup (empty database)
            logger.info("Stock database is empty. Initializing with predefined stocks...")
            count = await initialize_stocks()
            logger.info(f"✓ Startup initialization complete: {count} stocks loaded")
        else:
            # On all SUBSEQUENT startups (database already has stocks)
            logger.info(f"✓ Stock database ready: {stock_count} stocks available")
    
    except Exception as e:
        logger.error(f"✗ Startup initialization failed: {e}")
        # Don't crash the app, just log the error
        # Users can manually initialize via POST /api/stocks/initialize if needed


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection on app shutdown"""
    await close_db()


# ============ MIDDLEWARE ============
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ ROUTER ============
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
