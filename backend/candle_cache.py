"""Cache for Upstox historical candles to avoid refetching on every scan.

Candles are stored in MongoDB (collection: candle_cache). Indicators are
recomputed from cached candles each time. Cache is considered fresh for
CACHE_TTL_HOURS; after that we refetch from Upstox.
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24


async def get_candles(symbol: str, db, upstox_client) -> list:
    """Return daily candles for the symbol, from cache or Upstox.

    Uses collection candle_cache: { symbol, candles, updated_at }.
    Refetches from Upstox if missing or older than CACHE_TTL_HOURS.
    """
    symbol = symbol.upper()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=CACHE_TTL_HOURS)).isoformat()

    doc = await db.candle_cache.find_one({"symbol": symbol}, {"_id": 0})
    if doc and doc.get("updated_at", "") >= cutoff and doc.get("candles"):
        logger.debug(f"Using cached candles for {symbol} ({len(doc['candles'])} bars)")
        return doc["candles"]

    candles = await upstox_client.get_historical_candles(symbol, unit="days", interval=1)
    if candles:
        await db.candle_cache.update_one(
            {"symbol": symbol},
            {"$set": {"symbol": symbol, "candles": candles, "updated_at": now.isoformat()}},
            upsert=True,
        )
        logger.info(f"Cached {len(candles)} candles for {symbol}")
    return candles
