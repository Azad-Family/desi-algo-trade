"""Stock initialization utilities"""
import logging
import asyncio
from models import Stock
from stock_data import STOCK_UNIVERSE
from database import db

logger = logging.getLogger(__name__)

# Global lock to prevent concurrent initializations
_init_lock = asyncio.Lock()


async def initialize_stocks():
    """Initialize stock universe with all predefined stocks
    
    This function:
    - Acquires a lock to prevent concurrent executions
    - Clears existing stocks
    - Inserts fresh stock data
    - Should be called on startup and when user requests reinit
    
    Thread-safe: Multiple concurrent calls wait for the first to complete.
    """
    async with _init_lock:
        logger.info("Starting stock initialization...")
        try:
            # Clear existing stocks
            deleted = await db.stocks.delete_many({})
            logger.info(f"Cleared {deleted.deleted_count} existing stocks")
            
            # Insert all stocks from STOCK_UNIVERSE
            stocks = []
            for stock_data in STOCK_UNIVERSE:
                stock = Stock(
                    symbol=stock_data["symbol"],
                    name=stock_data["name"],
                    sector=stock_data["sector"],
                    current_price=0.0,
                    change_percent=0.0
                )
                stocks.append(stock.model_dump())
            
            if stocks:
                result = await db.stocks.insert_many(stocks)
                logger.info(f"✓ Inserted {len(result.inserted_ids)} stocks successfully")
                return len(result.inserted_ids)
            
            return 0
        
        except Exception as e:
            logger.error(f"✗ Failed to initialize stocks: {e}")
            raise


async def get_stock_count():
    """Get current count of stocks in database"""
    return await db.stocks.count_documents({})
