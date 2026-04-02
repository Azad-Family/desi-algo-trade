"""Fundamental data layer.

Provides earnings calendar, corporate actions, and basic fundamentals
(PE, market cap, 52-week range, promoter holding) for stocks.

Data sources:
  - india-corp-actions package (NSE/BSE corporate actions, free)
  - Upstox instrument data (52-week range, market cap via OHLC)
  - NSE endpoints (earnings calendar, promoter holding — best-effort)

Usage:
    await refresh_fundamentals("RELIANCE")
    data = await get_fundamentals("RELIANCE")
    upcoming = await get_upcoming_earnings()
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from database import db

logger = logging.getLogger(__name__)


# ─── Earnings calendar ──────────────────────────────────────

async def fetch_upcoming_earnings() -> List[Dict[str, Any]]:
    """Fetch upcoming quarterly result dates from NSE.

    Uses india-corp-actions if available, falls back to stored data.
    Returns list of {symbol, date, purpose}.
    """
    results = []
    try:
        from india_corp_actions import get_upcoming_results
        df = get_upcoming_results()
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                symbol = str(row.get("symbol", "")).upper()
                date_str = str(row.get("date", row.get("bm_date", "")))
                purpose = str(row.get("purpose", row.get("bm_purpose", "")))
                if symbol:
                    results.append({
                        "symbol": symbol,
                        "date": date_str,
                        "purpose": purpose,
                    })
            logger.info(f"Fetched {len(results)} upcoming earnings from india-corp-actions")
    except ImportError:
        logger.debug("india-corp-actions not installed, skipping earnings fetch")
    except Exception as e:
        logger.warning(f"Error fetching earnings calendar: {e}")

    if results:
        await db.earnings_calendar.delete_many({})
        if results:
            await db.earnings_calendar.insert_many(results)

    return results


async def get_upcoming_earnings(symbol: str = None) -> List[Dict[str, Any]]:
    """Get upcoming earnings from cached data.

    If symbol is provided, returns only that stock's earnings.
    """
    query = {}
    if symbol:
        query["symbol"] = symbol.upper()

    results = await db.earnings_calendar.find(query, {"_id": 0}).to_list(200)
    return results


async def is_near_earnings(symbol: str, days: int = 3) -> bool:
    """Check if a stock has earnings within the next N days."""
    earnings = await get_upcoming_earnings(symbol)
    if not earnings:
        return False

    now = datetime.now(timezone.utc)
    for e in earnings:
        try:
            date_str = e.get("date", "")
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    earn_date = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                continue

            delta = (earn_date - now).days
            if 0 <= delta <= days:
                return True
        except Exception:
            continue

    return False


# ─── Corporate actions ──────────────────────────────────────

async def fetch_corporate_actions(symbol: str = None) -> List[Dict[str, Any]]:
    """Fetch recent corporate actions (dividends, splits, bonuses).

    Uses india-corp-actions if available.
    """
    results = []
    try:
        from india_corp_actions import get_actions_df
        kwargs = {}
        if symbol:
            kwargs["symbol"] = symbol.upper()
        df = get_actions_df(**kwargs)
        if df is not None and not df.empty:
            for _, row in df.head(100).iterrows():
                results.append({
                    "symbol": str(row.get("symbol", "")).upper(),
                    "ex_date": str(row.get("ex_date", "")),
                    "action_type": str(row.get("subject", row.get("action", ""))),
                    "details": str(row.get("subject", "")),
                })
            logger.info(f"Fetched {len(results)} corporate actions")
    except ImportError:
        logger.debug("india-corp-actions not installed")
    except Exception as e:
        logger.warning(f"Error fetching corporate actions: {e}")

    return results


# ─── Basic fundamentals ─────────────────────────────────────

async def refresh_fundamentals(symbol: str) -> Optional[Dict[str, Any]]:
    """Compute and store basic fundamental data for a stock.

    Uses cached candle data and db.stocks for existing fields.
    """
    symbol = symbol.upper()

    stock = await db.stocks.find_one({"symbol": symbol}, {"_id": 0})
    if not stock:
        return None

    # 52-week high/low from candle cache
    candle_doc = await db.candle_cache.find_one({"symbol": symbol}, {"_id": 0, "candles": 1})
    high_52w = None
    low_52w = None
    if candle_doc and candle_doc.get("candles"):
        candles = candle_doc["candles"]
        # Last 252 trading days ≈ 1 year
        recent = candles[-252:] if len(candles) >= 252 else candles
        highs = [float(c[2]) for c in recent]
        lows = [float(c[3]) for c in recent]
        high_52w = max(highs) if highs else None
        low_52w = min(lows) if lows else None

    # Check if near earnings
    near_earnings = await is_near_earnings(symbol)
    earnings = await get_upcoming_earnings(symbol)
    next_earnings = earnings[0].get("date") if earnings else None

    fundamentals = {
        "symbol": symbol,
        "pe_ratio": stock.get("pe_ratio"),
        "market_cap": stock.get("market_cap"),
        "high_52w": high_52w,
        "low_52w": low_52w,
        "promoter_holding_pct": stock.get("promoter_holding_pct"),
        "next_earnings_date": next_earnings,
        "near_earnings": near_earnings,
        "last_refreshed": datetime.now(timezone.utc).isoformat(),
    }

    await db.fundamentals.update_one(
        {"symbol": symbol},
        {"$set": fundamentals},
        upsert=True,
    )

    return fundamentals


async def get_fundamentals(symbol: str) -> Optional[Dict[str, Any]]:
    """Get cached fundamental data for a stock."""
    return await db.fundamentals.find_one({"symbol": symbol.upper()}, {"_id": 0})


def format_fundamentals_for_prompt(data: Optional[Dict[str, Any]]) -> str:
    """Format fundamental data as text for AI prompts."""
    if not data:
        return ""

    lines = ["FUNDAMENTAL DATA:"]

    pe = data.get("pe_ratio")
    if pe:
        lines.append(f"  P/E Ratio: {pe}")

    mcap = data.get("market_cap")
    if mcap:
        if mcap >= 1e12:
            lines.append(f"  Market Cap: Rs.{mcap/1e12:.1f}T")
        elif mcap >= 1e9:
            lines.append(f"  Market Cap: Rs.{mcap/1e9:.0f}B")
        else:
            lines.append(f"  Market Cap: Rs.{mcap/1e7:.0f}Cr")

    h52 = data.get("high_52w")
    l52 = data.get("low_52w")
    if h52 and l52:
        lines.append(f"  52-Week Range: Rs.{l52:.2f} — Rs.{h52:.2f}")

    promo = data.get("promoter_holding_pct")
    if promo:
        lines.append(f"  Promoter Holding: {promo}%")

    earn = data.get("next_earnings_date")
    if earn:
        near = data.get("near_earnings", False)
        warning = " ⚠ EARNINGS IMMINENT" if near else ""
        lines.append(f"  Next Earnings: {earn}{warning}")

    return "\n".join(lines) if len(lines) > 1 else ""
