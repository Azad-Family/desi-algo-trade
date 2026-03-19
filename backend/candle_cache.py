"""Incremental cache for Upstox historical candles.

Candles are stored in MongoDB (collection: candle_cache).
On first fetch, downloads 1 year of daily candles.
On subsequent fetches, only requests candles since the last cached date
and appends them — avoiding a full re-download every day.

Schema: { symbol, candles, last_candle_date }
  - candles: list of [timestamp, open, high, low, close, volume, oi]
  - last_candle_date: "YYYY-MM-DD" of the most recent candle in the cache
"""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

try:
    import zoneinfo
    IST = zoneinfo.ZoneInfo("Asia/Kolkata")
except ImportError:
    from datetime import timezone as _tz
    IST = _tz(timedelta(hours=5, minutes=30))

MAX_HISTORY_DAYS = 365


def _candle_date(candle) -> str:
    """Extract YYYY-MM-DD from a candle's timestamp (position 0)."""
    ts = candle[0]
    if isinstance(ts, str):
        return ts[:10]
    return str(ts)[:10]


def _today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _trim_old_candles(candles: list) -> list:
    """Drop candles older than MAX_HISTORY_DAYS."""
    cutoff = (datetime.now(IST) - timedelta(days=MAX_HISTORY_DAYS)).strftime("%Y-%m-%d")
    return [c for c in candles if _candle_date(c) >= cutoff]


def _deduplicate(candles: list) -> list:
    """Remove duplicate candles by date, keeping the latest occurrence."""
    seen = {}
    for c in candles:
        seen[_candle_date(c)] = c
    result = list(seen.values())
    result.sort(key=lambda c: _candle_date(c))
    return result


async def get_candles(symbol: str, db, upstox_client) -> list:
    """Return daily candles for the symbol, from cache or Upstox.

    - First call: full 1-year fetch, stored in MongoDB.
    - Subsequent calls on the same day: instant cache hit (zero API calls).
    - Next day: incremental fetch (last_candle_date+1 → today), append & trim.
    """
    symbol = symbol.upper()
    today = _today_ist()

    doc = await db.candle_cache.find_one({"symbol": symbol}, {"_id": 0})

    if doc and doc.get("candles"):
        last_date = doc.get("last_candle_date") or _candle_date(doc["candles"][-1])

        if last_date >= today:
            logger.debug(f"Cache hit for {symbol} ({len(doc['candles'])} bars, up to {last_date})")
            return doc["candles"]

        # Incremental fetch: from day after last cached candle to today
        fetch_from = (datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info(f"Incremental fetch for {symbol}: {fetch_from} → {today}")
        new_candles = await upstox_client.get_historical_candles(
            symbol, unit="days", interval=1, from_date=fetch_from, to_date=today,
        )

        cached = doc["candles"]
        if new_candles:
            merged = _deduplicate(cached + new_candles)
            merged = _trim_old_candles(merged)
            new_last = _candle_date(merged[-1])
            await db.candle_cache.update_one(
                {"symbol": symbol},
                {"$set": {"candles": merged, "last_candle_date": new_last}},
            )
            logger.info(f"Appended {len(new_candles)} candles for {symbol} (total {len(merged)}, up to {new_last})")
            return merged

        # No new candles (weekend / holiday) — mark today so we don't retry
        await db.candle_cache.update_one(
            {"symbol": symbol},
            {"$set": {"last_candle_date": today}},
        )
        logger.debug(f"No new candles for {symbol} (non-trading day?), cache still has {len(cached)} bars")
        return cached

    # No cache at all — full 1-year fetch
    logger.info(f"Full fetch for {symbol}: 1 year of daily candles")
    candles = await upstox_client.get_historical_candles(symbol, unit="days", interval=1)
    if candles:
        candles = _deduplicate(candles)
        last_date = _candle_date(candles[-1])
        await db.candle_cache.update_one(
            {"symbol": symbol},
            {"$set": {"symbol": symbol, "candles": candles, "last_candle_date": last_date}},
            upsert=True,
        )
        logger.info(f"Cached {len(candles)} candles for {symbol} (up to {last_date})")
    return candles or []
