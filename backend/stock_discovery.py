"""Dynamic stock universe management.

Manages a "Core + Dynamic" stock universe where stocks can be
discovered and added at runtime by the agent, user, or automated
sector/correlation scans.

Core stocks (~125): defined in stock_data.py, always tracked.
Dynamic stocks: discovered at runtime, stored in db.dynamic_watchlist.

Lifecycle:
  new → active → pruned (after 30 days of no activity)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from database import db
from trading import UpstoxClient

logger = logging.getLogger(__name__)

_upstox = UpstoxClient()

PRUNE_AFTER_DAYS = 30


# ─── Discovery ──────────────────────────────────────────────

async def discover_stock(
    symbol: str,
    name: str = "",
    sector: str = "Unknown",
    discovered_by: str = "agent",
    reason: str = "",
) -> Optional[Dict[str, Any]]:
    """Add a stock to the dynamic watchlist.

    If the symbol is already in core stocks or active dynamic watchlist,
    returns the existing entry without duplicating.
    """
    symbol = symbol.upper()

    # Check if already in core universe
    core = await db.stocks.find_one({"symbol": symbol}, {"_id": 0, "symbol": 1})
    if core:
        logger.info(f"{symbol} already in core universe, skipping dynamic add")
        return {"symbol": symbol, "source": "core", "status": "exists"}

    # Check if already in dynamic watchlist
    existing = await db.dynamic_watchlist.find_one({"symbol": symbol}, {"_id": 0})
    if existing:
        if existing.get("status") == "pruned":
            await db.dynamic_watchlist.update_one(
                {"symbol": symbol},
                {"$set": {"status": "active", "last_active": datetime.now(timezone.utc).isoformat()}},
            )
            logger.info(f"Reactivated pruned dynamic stock: {symbol}")
            return {**existing, "status": "active"}
        logger.info(f"{symbol} already in dynamic watchlist")
        return existing

    # Resolve on Upstox
    instrument_key = await _upstox.resolve_instrument_key(symbol)
    if not instrument_key or instrument_key.startswith("NSE_EQ|"):
        logger.warning(f"Could not resolve instrument for {symbol}")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "symbol": symbol,
        "name": name or symbol,
        "sector": sector,
        "instrument_key": instrument_key,
        "discovered_by": discovered_by,
        "discovered_at": now,
        "reason": reason,
        "last_active": now,
        "status": "active",
        "analysis_count": 0,
        "trade_count": 0,
    }

    await db.dynamic_watchlist.insert_one(doc)
    logger.info(f"Added {symbol} to dynamic watchlist (by: {discovered_by}, reason: {reason})")

    # Fetch initial candle data
    try:
        from candle_cache import get_candles as get_candles_cached
        candles = await get_candles_cached(symbol, db, _upstox)
        if candles:
            logger.info(f"Fetched {len(candles)} initial candles for dynamic stock {symbol}")
    except Exception as e:
        logger.warning(f"Could not fetch candles for {symbol}: {e}")

    return doc


async def discover_from_conversation(user_message: str) -> List[Dict[str, Any]]:
    """Extract stock symbols from a user message and add to dynamic watchlist.

    Parses out NSE stock symbols from natural language.
    Returns list of newly discovered stocks.
    """
    import re
    potential_symbols = re.findall(r'\b([A-Z]{2,15})\b', user_message.upper())

    exclusions = {
        "THE", "AND", "FOR", "NOT", "BUT", "HAS", "WAS", "ARE", "CAN",
        "BUY", "SELL", "HOLD", "SHORT", "LONG", "WHAT", "HOW", "WHY",
        "STOCK", "TRADE", "MARKET", "PRICE", "ABOUT", "SHOULD", "WOULD",
        "ANALYZE", "ANALYSIS", "RESEARCH", "PORTFOLIO", "NSE", "BSE",
        "NIFTY", "SENSEX", "BANKNIFTY", "VIX", "FII", "DII",
    }

    added = []
    for sym in potential_symbols:
        if sym in exclusions or len(sym) < 3:
            continue

        # Check if it's an actual tradeable instrument
        await _upstox._ensure_instrument_map()
        if sym in _upstox._instrument_map:
            result = await discover_stock(
                sym,
                discovered_by="user_conversation",
                reason=f"Mentioned in user message",
            )
            if result and result.get("status") != "exists":
                added.append(result)

    return added


# ─── Universe queries ───────────────────────────────────────

async def get_full_universe() -> List[Dict[str, Any]]:
    """Return all symbols in the full universe (core + active dynamic)."""
    core = await db.stocks.find({}, {"_id": 0, "symbol": 1, "name": 1, "sector": 1}).to_list(500)
    dynamic = await db.dynamic_watchlist.find(
        {"status": "active"},
        {"_id": 0, "symbol": 1, "name": 1, "sector": 1},
    ).to_list(200)

    all_symbols = {s["symbol"] for s in core}
    result = list(core)
    for d in dynamic:
        if d["symbol"] not in all_symbols:
            result.append(d)
            all_symbols.add(d["symbol"])

    return result


async def get_dynamic_stocks() -> List[Dict[str, Any]]:
    """Return only dynamic watchlist stocks (active)."""
    return await db.dynamic_watchlist.find(
        {"status": "active"},
        {"_id": 0},
    ).to_list(200)


async def get_dynamic_stock(symbol: str) -> Optional[Dict[str, Any]]:
    """Get a specific dynamic stock entry."""
    return await db.dynamic_watchlist.find_one(
        {"symbol": symbol.upper()},
        {"_id": 0},
    )


async def mark_active(symbol: str):
    """Update last_active timestamp for a dynamic stock."""
    await db.dynamic_watchlist.update_one(
        {"symbol": symbol.upper(), "status": "active"},
        {"$set": {"last_active": datetime.now(timezone.utc).isoformat()}},
    )


async def increment_analysis(symbol: str):
    """Increment analysis count for a dynamic stock."""
    await db.dynamic_watchlist.update_one(
        {"symbol": symbol.upper()},
        {
            "$inc": {"analysis_count": 1},
            "$set": {"last_active": datetime.now(timezone.utc).isoformat()},
        },
    )


# ─── Pruning ────────────────────────────────────────────────

async def prune_inactive_stocks() -> int:
    """Prune dynamic stocks that haven't been active for PRUNE_AFTER_DAYS.

    Pruned stocks keep their candle data but are excluded from daily scans.
    Returns the number of stocks pruned.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PRUNE_AFTER_DAYS)).isoformat()
    result = await db.dynamic_watchlist.update_many(
        {"status": "active", "last_active": {"$lt": cutoff}},
        {"$set": {"status": "pruned"}},
    )
    if result.modified_count:
        logger.info(f"Pruned {result.modified_count} inactive dynamic stocks")
    return result.modified_count


async def remove_stock(symbol: str) -> bool:
    """Remove a stock from the dynamic watchlist entirely."""
    result = await db.dynamic_watchlist.delete_one({"symbol": symbol.upper()})
    return result.deleted_count > 0
