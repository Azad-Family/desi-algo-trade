"""Market-wide context layer.

Computes a "market pulse" that gets prepended to every AI prompt
so the model understands the macro regime before analysing any stock.

Components:
  - Nifty 50 / Bank Nifty index trend (EMA, RSI, day change)
  - India VIX (fear gauge → position-sizing hint)
  - Sector performance & rotation ranking
  - Advance / Decline ratio from the stock universe
  - FII / DII activity (net buy/sell from NSE)

Usage:
  ctx = await get_market_context()          # full dict
  prompt_block = format_market_context(ctx)  # text for Gemini
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import pytz
import pandas as pd

from database import db
from trading import UpstoxClient

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

INDEX_KEYS = {
    "NIFTY50": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "INDIA_VIX": "NSE_INDEX|India VIX",
    "NIFTY_IT": "NSE_INDEX|Nifty IT",
    "NIFTY_PHARMA": "NSE_INDEX|Nifty Pharma",
    "NIFTY_FIN": "NSE_INDEX|Nifty Financial Services",
    "NIFTY_AUTO": "NSE_INDEX|Nifty Auto",
    "NIFTY_METAL": "NSE_INDEX|Nifty Metal",
    "NIFTY_FMCG": "NSE_INDEX|Nifty FMCG",
    "NIFTY_ENERGY": "NSE_INDEX|Nifty Energy",
    "NIFTY_REALTY": "NSE_INDEX|Nifty Realty",
}

_upstox = UpstoxClient()

# Cache so we don't re-fetch every 60s during the same session
_context_cache: Dict[str, Any] = {}
_cache_ts: Optional[datetime] = None
CACHE_TTL_SECONDS = 300  # 5 minutes


# ─── Index data ──────────────────────────────────────────────

async def _fetch_index_quotes() -> Dict[str, Dict[str, Any]]:
    """Fetch live quotes for major NSE indices via Upstox batch-quote API."""
    if not _upstox.is_configured():
        return {}

    import httpx

    instrument_keys = ",".join(INDEX_KEYS.values())
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_upstox.market_quote_url}/market-quote/quotes",
                params={"instrument_key": instrument_keys},
                headers={
                    "Authorization": f"Bearer {_upstox.live_access_token}",
                    "Accept": "application/json",
                },
                timeout=10.0,
            )
            if resp.status_code != 200:
                logger.warning(f"Index quote API returned {resp.status_code}: {resp.text[:200]}")
                return {}

            data = resp.json().get("data", {})
            result = {}
            inv_keys = {v: k for k, v in INDEX_KEYS.items()}
            for raw_key, quote in data.items():
                clean_key = raw_key.replace("NSE_INDEX:", "NSE_INDEX|")
                alias = inv_keys.get(clean_key)
                if not alias:
                    for ik_alias, ik_val in INDEX_KEYS.items():
                        if ik_val.split("|")[1].upper() in raw_key.upper():
                            alias = ik_alias
                            break
                if alias:
                    ltp = quote.get("last_price") or quote.get("ltp", 0)
                    ohlc = quote.get("ohlc", {})
                    prev_close = ohlc.get("close", 0)
                    change = quote.get("net_change", 0)
                    change_pct = (change / prev_close * 100) if prev_close else 0
                    result[alias] = {
                        "ltp": round(float(ltp), 2),
                        "prev_close": round(float(prev_close), 2),
                        "change": round(float(change), 2),
                        "change_pct": round(float(change_pct), 2),
                        "day_high": round(float(ohlc.get("high", ltp)), 2),
                        "day_low": round(float(ohlc.get("low", ltp)), 2),
                        "day_open": round(float(ohlc.get("open", ltp)), 2),
                    }
            logger.info(f"Fetched quotes for {len(result)} indices")
            return result
    except Exception as e:
        logger.error(f"Error fetching index quotes: {e}")
        return {}


async def _compute_index_trend(symbol: str = "NIFTY50") -> Dict[str, Any]:
    """Compute short-term trend indicators for an index using cached candles.

    Returns EMA-based trend, RSI approximation, and returns.
    """
    from candle_cache import get_candles as get_candles_cached

    inst_key = INDEX_KEYS.get(symbol, f"NSE_INDEX|{symbol}")
    candle_symbol = f"_IDX_{symbol}"

    try:
        candles = await get_candles_cached(candle_symbol, db, _upstox)
    except Exception:
        candles = []

    if not candles or len(candles) < 20:
        # Try direct fetch for indices (candle cache may not have them yet)
        try:
            candles = await _upstox.get_historical_candles(
                candle_symbol, unit="days", interval=1,
            )
        except Exception:
            pass

    if not candles or len(candles) < 20:
        return {"trend": "unknown", "reason": "insufficient data"}

    df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume", "oi"])
    df["close"] = df["close"].astype(float)
    df = df.sort_values("ts").reset_index(drop=True)

    close = df["close"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    last_close = float(close.iloc[-1])
    last_ema20 = float(ema20.iloc[-1])
    last_ema50 = float(ema50.iloc[-1])

    # Simple RSI (14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    last_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

    if last_close > last_ema20 > last_ema50:
        trend = "bullish"
    elif last_close < last_ema20 < last_ema50:
        trend = "bearish"
    else:
        trend = "sideways"

    ret_1d = float((close.iloc[-1] / close.iloc[-2] - 1) * 100) if len(close) > 1 else 0
    ret_5d = float((close.iloc[-1] / close.iloc[-6] - 1) * 100) if len(close) > 5 else 0
    ret_20d = float((close.iloc[-1] / close.iloc[-21] - 1) * 100) if len(close) > 20 else 0

    return {
        "trend": trend,
        "ema20": round(last_ema20, 2),
        "ema50": round(last_ema50, 2),
        "rsi": round(last_rsi, 1),
        "return_1d": round(ret_1d, 2),
        "return_5d": round(ret_5d, 2),
        "return_20d": round(ret_20d, 2),
    }


# ─── Sector analysis ────────────────────────────────────────

async def _compute_sector_performance() -> List[Dict[str, Any]]:
    """Rank sectors by momentum using stocks from our universe.

    Returns sectors sorted by 1-day average change, with 5d/20d returns.
    """
    stocks = await db.stocks.find({}, {"_id": 0, "symbol": 1, "sector": 1, "change_percent": 1}).to_list(500)

    sectors: Dict[str, List[float]] = {}
    for s in stocks:
        sec = s.get("sector", "Unknown")
        cp = s.get("change_percent", 0)
        if cp is None:
            cp = 0
        sectors.setdefault(sec, []).append(float(cp))

    result = []
    for sec, changes in sectors.items():
        if not changes:
            continue
        avg_change = sum(changes) / len(changes)
        advancing = sum(1 for c in changes if c > 0)
        declining = sum(1 for c in changes if c < 0)
        result.append({
            "sector": sec,
            "avg_change_1d": round(avg_change, 2),
            "advancing": advancing,
            "declining": declining,
            "stock_count": len(changes),
        })

    result.sort(key=lambda x: x["avg_change_1d"], reverse=True)

    for i, r in enumerate(result):
        r["rank"] = i + 1

    return result


# ─── Advance / Decline ──────────────────────────────────────

async def _compute_advance_decline() -> Dict[str, Any]:
    """Compute advance/decline ratio from the stock universe.

    Uses the latest change_percent stored in db.stocks.
    """
    stocks = await db.stocks.find({}, {"_id": 0, "change_percent": 1}).to_list(500)
    advancing = sum(1 for s in stocks if (s.get("change_percent") or 0) > 0)
    declining = sum(1 for s in stocks if (s.get("change_percent") or 0) < 0)
    unchanged = len(stocks) - advancing - declining
    ratio = round(advancing / declining, 2) if declining > 0 else float(advancing)
    breadth = "positive" if ratio > 1.5 else ("negative" if ratio < 0.67 else "neutral")

    return {
        "advancing": advancing,
        "declining": declining,
        "unchanged": unchanged,
        "total": len(stocks),
        "ad_ratio": ratio,
        "breadth": breadth,
    }


# ─── FII / DII (best-effort scrape from NSE) ────────────────

async def _fetch_fii_dii() -> Dict[str, Any]:
    """Fetch latest FII/DII activity from NSE.

    This is best-effort — NSE may block scraping. Falls back to
    empty data gracefully.
    """
    import httpx

    url = "https://www.nseindia.com/api/fiidiiTradeReact"
    try:
        async with httpx.AsyncClient() as client:
            # NSE requires browser-like headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://www.nseindia.com/reports/fii-dii",
            }
            # First hit the main page to get cookies
            await client.get("https://www.nseindia.com", headers=headers, timeout=5.0)
            resp = await client.get(url, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                result = {}
                for entry in data:
                    cat = entry.get("category", "")
                    if "FII" in cat.upper() or "FPI" in cat.upper():
                        result["fii_net"] = round(float(entry.get("buyValue", 0)) - float(entry.get("sellValue", 0)), 2)
                        result["fii_buy"] = round(float(entry.get("buyValue", 0)), 2)
                        result["fii_sell"] = round(float(entry.get("sellValue", 0)), 2)
                    elif "DII" in cat.upper():
                        result["dii_net"] = round(float(entry.get("buyValue", 0)) - float(entry.get("sellValue", 0)), 2)
                        result["dii_buy"] = round(float(entry.get("buyValue", 0)), 2)
                        result["dii_sell"] = round(float(entry.get("sellValue", 0)), 2)
                if result:
                    logger.info(f"FII/DII data: FII net={result.get('fii_net')}, DII net={result.get('dii_net')}")
                    return result
            else:
                logger.debug(f"NSE FII/DII API returned {resp.status_code}")
    except Exception as e:
        logger.debug(f"Could not fetch FII/DII data: {e}")

    return {}


# ─── Market regime classification ────────────────────────────

def _classify_regime(nifty_trend: Dict, vix: Dict, ad: Dict) -> Dict[str, Any]:
    """Classify the overall market regime from available data."""
    trend = nifty_trend.get("trend", "unknown")
    rsi = nifty_trend.get("rsi", 50)
    vix_ltp = vix.get("ltp", 15)
    breadth = ad.get("breadth", "neutral")
    ad_ratio = ad.get("ad_ratio", 1.0)

    # Regime
    if trend == "bullish" and rsi > 55 and breadth == "positive":
        regime = "STRONG_BULL"
        sizing_hint = "full position size"
    elif trend == "bullish":
        regime = "BULL"
        sizing_hint = "full position size"
    elif trend == "bearish" and rsi < 45 and breadth == "negative":
        regime = "STRONG_BEAR"
        sizing_hint = "reduce position size by 50%, prefer SHORT"
    elif trend == "bearish":
        regime = "BEAR"
        sizing_hint = "reduce position size by 30%, caution on longs"
    else:
        regime = "SIDEWAYS"
        sizing_hint = "normal position size, range-bound strategies"

    # VIX overlay
    if vix_ltp > 25:
        vix_regime = "HIGH_FEAR"
        sizing_hint += ", tighten stop-losses (VIX elevated)"
    elif vix_ltp > 18:
        vix_regime = "ELEVATED"
        sizing_hint += ", slightly tighter stop-losses"
    elif vix_ltp < 12:
        vix_regime = "COMPLACENT"
        sizing_hint += ", watch for sudden spikes"
    else:
        vix_regime = "NORMAL"

    return {
        "regime": regime,
        "vix_regime": vix_regime,
        "sizing_hint": sizing_hint,
    }


# ─── Main entry point ───────────────────────────────────────

async def get_market_context(force_refresh: bool = False) -> Dict[str, Any]:
    """Compute the full market context.

    Cached for 5 minutes to avoid hammering APIs on rapid scans.
    Pass force_refresh=True for scheduler pre-market calls.
    """
    global _context_cache, _cache_ts

    now = datetime.now(IST)
    if not force_refresh and _cache_ts and (now - _cache_ts).total_seconds() < CACHE_TTL_SECONDS:
        return _context_cache

    logger.info("Computing market context...")

    index_quotes = await _fetch_index_quotes()
    nifty_quote = index_quotes.get("NIFTY50", {})
    banknifty_quote = index_quotes.get("BANKNIFTY", {})
    vix_quote = index_quotes.get("INDIA_VIX", {})

    sectors = await _compute_sector_performance()
    ad = await _compute_advance_decline()
    fii_dii = await _fetch_fii_dii()

    nifty_trend = await _compute_index_trend("NIFTY50")

    regime_info = _classify_regime(
        nifty_trend,
        vix_quote,
        ad,
    )

    ctx = {
        "timestamp": now.isoformat(),
        "indices": {
            "nifty50": nifty_quote,
            "banknifty": banknifty_quote,
            "india_vix": vix_quote,
        },
        "sector_performance": sectors,
        "advance_decline": ad,
        "fii_dii": fii_dii,
        "regime": regime_info,
    }

    # Persist to DB for historical tracking
    await db.market_context.update_one(
        {"date": now.strftime("%Y-%m-%d")},
        {"$set": ctx},
        upsert=True,
    )

    _context_cache = ctx
    _cache_ts = now
    logger.info(f"Market context computed — regime: {regime_info['regime']}, VIX: {vix_quote.get('ltp', 'N/A')}")
    return ctx


# ─── Formatting for AI prompts ───────────────────────────────

def format_market_context(ctx: Dict[str, Any]) -> str:
    """Format market context as a text block for Gemini prompts.

    This block should be prepended to every stock analysis prompt
    so the AI is aware of the macro environment.
    """
    lines = ["=" * 50, "MARKET CONTEXT (macro regime — factor this into your analysis)", "=" * 50]

    # Indices
    nifty = ctx.get("indices", {}).get("nifty50", {})
    banknifty = ctx.get("indices", {}).get("banknifty", {})
    vix = ctx.get("indices", {}).get("india_vix", {})

    if nifty:
        lines.append(f"NIFTY 50: {nifty.get('ltp', 'N/A')} ({nifty.get('change_pct', 0):+.2f}%)")
    if banknifty:
        lines.append(f"BANK NIFTY: {banknifty.get('ltp', 'N/A')} ({banknifty.get('change_pct', 0):+.2f}%)")
    if vix:
        vix_val = vix.get("ltp", 0)
        vix_label = "HIGH FEAR" if vix_val > 25 else ("ELEVATED" if vix_val > 18 else "NORMAL")
        lines.append(f"INDIA VIX: {vix_val} ({vix_label})")

    # Regime
    regime = ctx.get("regime", {})
    if regime:
        lines.append(f"\nMARKET REGIME: {regime.get('regime', 'UNKNOWN')}")
        lines.append(f"POSITION SIZING: {regime.get('sizing_hint', 'normal')}")

    # Advance / Decline
    ad = ctx.get("advance_decline", {})
    if ad:
        lines.append(
            f"\nBREADTH: {ad.get('advancing', 0)} advancing / {ad.get('declining', 0)} declining "
            f"(A/D ratio: {ad.get('ad_ratio', 'N/A')}, {ad.get('breadth', 'neutral')})"
        )

    # FII / DII
    fii = ctx.get("fii_dii", {})
    if fii:
        fii_net = fii.get("fii_net", 0)
        dii_net = fii.get("dii_net", 0)
        fii_dir = "BUYING" if fii_net > 0 else "SELLING"
        dii_dir = "BUYING" if dii_net > 0 else "SELLING"
        lines.append(f"FII/FPI: Rs.{abs(fii_net):,.0f} Cr net {fii_dir}")
        lines.append(f"DII:     Rs.{abs(dii_net):,.0f} Cr net {dii_dir}")

    # Sector rotation
    sectors = ctx.get("sector_performance", [])
    if sectors:
        lines.append("\nSECTOR ROTATION (ranked by today's performance):")
        top_3 = sectors[:3]
        bottom_3 = sectors[-3:] if len(sectors) > 3 else []
        for s in top_3:
            lines.append(f"  #{s['rank']} {s['sector']}: {s['avg_change_1d']:+.2f}% ({s['advancing']}↑ {s['declining']}↓)")
        if bottom_3:
            lines.append("  ...")
            for s in bottom_3:
                lines.append(f"  #{s['rank']} {s['sector']}: {s['avg_change_1d']:+.2f}% ({s['advancing']}↑ {s['declining']}↓)")

    lines.append("=" * 50)
    return "\n".join(lines)


def get_sector_rank(ctx: Dict[str, Any], sector: str) -> Optional[Dict[str, Any]]:
    """Get ranking info for a specific sector from the market context."""
    for s in ctx.get("sector_performance", []):
        if s["sector"].upper() == sector.upper():
            return s
    return None
