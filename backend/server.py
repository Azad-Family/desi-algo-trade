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
from agent_routes import agent_router
from sandbox_routes import sandbox_router
from stock_init import initialize_stocks, get_stock_count
from ai_engine import set_preferred_model
from scheduler import start_scheduler, stop_scheduler, is_scheduler_running

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
            logger.info(f"✓ Stock database ready: {stock_count} stocks available")

        # Restore user's preferred Gemini model from DB
        settings = await db.settings.find_one({"id": "main_settings"}, {"_id": 0})
        if settings and settings.get("gemini_model"):
            set_preferred_model(settings["gemini_model"])
            logger.info(f"✓ Gemini model preference loaded: {settings['gemini_model']}")

        # Auto-start sandbox scheduler (daily scan + intraday monitor)
        scheduler_config = await db.scheduler_config.find_one({"id": "scheduler_config"}, {"_id": 0})
        should_start = not scheduler_config or scheduler_config.get("enabled", True)
        if should_start and not is_scheduler_running():
            await start_scheduler()
            logger.info("✓ Sandbox scheduler auto-started")

    except Exception as e:
        logger.error(f"✗ Startup initialization failed: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop scheduler and close database connection on app shutdown"""
    if is_scheduler_running():
        await stop_scheduler()
    await close_db()


# ============ MIDDLEWARE ============
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ ROUTERS ============
app.include_router(api_router)
app.include_router(agent_router)
app.include_router(sandbox_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
