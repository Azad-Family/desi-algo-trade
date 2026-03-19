"""Fast technical screener for pre-filtering stocks before deep AI analysis.

Runs lightweight indicator checks on all stocks in the universe and produces
a ranked shortlist of actionable candidates. This avoids burning Gemini API
calls on stocks that are flat or have no setup.

The screener looks for:
  - Strong momentum (RSI, MACD, EMA crossovers)
  - Volume spikes (institutional activity)
  - Supertrend flips
  - Bollinger squeeze breakouts
  - Proximity to key support/resistance (pivot, Fibonacci)
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from database import db
from trading import UpstoxClient
from candle_cache import get_candles as get_candles_cached
from indicators import compute_indicators, compute_signal_scorecard

logger = logging.getLogger(__name__)

upstox_client = UpstoxClient()

SCREENER_MIN_SCORE = 25  # absolute score threshold (|score| >= 25 means actionable)


def _compute_screen_score(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a fast screening score from raw indicators.

    Returns a dict with score, bias, and the top reasons for the signal.
    """
    if not indicators:
        return {"score": 0, "bias": "no_data", "reasons": [], "actionable": False}

    scorecard = compute_signal_scorecard(indicators)
    score = scorecard["score"]
    bias = scorecard["net_bias"]
    reasons: List[str] = []

    # Collect top reasons
    for name, verdict in scorecard["signals"]:
        if verdict in ("bullish", "bearish"):
            reasons.append(f"{name}: {verdict}")

    # Bonus triggers that bump priority
    bonus = 0.0

    # Volume spike with price move
    vol_ratio = indicators.get("volume_ratio", 1.0)
    if vol_ratio and vol_ratio >= 2.0:
        bonus += 10
        reasons.append(f"volume_spike: {vol_ratio}x avg")

    # EMA crossover event (recent cross is very actionable)
    cross_event = indicators.get("ema_9_21_cross_event")
    if cross_event and cross_event != "none":
        bonus += 15
        reasons.append(f"ema_crossover_event: {cross_event}")

    # Supertrend flip
    st = indicators.get("supertrend_signal")
    if st:
        reasons.append(f"supertrend: {st}")

    # Bollinger squeeze (breakout imminent)
    if indicators.get("bb_squeeze"):
        bonus += 8
        reasons.append("bollinger_squeeze: YES")

    # RSI extremes
    rsi = indicators.get("rsi_14")
    if rsi is not None:
        if rsi <= 30 or rsi >= 70:
            bonus += 5
            reasons.append(f"rsi_extreme: {rsi}")

    # RSI divergence
    rsi_div = indicators.get("rsi_divergence")
    if rsi_div and "divergence" in rsi_div:
        bonus += 12
        reasons.append(f"rsi_divergence: {rsi_div}")

    # Apply bonus in the direction of bias
    if score >= 0:
        adjusted_score = score + bonus
    else:
        adjusted_score = score - bonus

    adjusted_score = max(-100, min(100, adjusted_score))
    actionable = abs(adjusted_score) >= SCREENER_MIN_SCORE

    return {
        "score": round(adjusted_score, 1),
        "raw_score": score,
        "bias": bias,
        "bullish_count": scorecard["bullish"],
        "bearish_count": scorecard["bearish"],
        "total_signals": scorecard["total"],
        "reasons": reasons[:8],
        "actionable": actionable,
        "volume_ratio": indicators.get("volume_ratio"),
        "rsi": indicators.get("rsi_14"),
        "price": indicators.get("current_price"),
        "change_1d": indicators.get("change_1d"),
        "change_5d": indicators.get("change_5d"),
        "atr_pct": indicators.get("atr_pct"),
    }


async def screen_single_stock(symbol: str) -> Optional[Dict[str, Any]]:
    """Screen a single stock. Returns screening result or None on failure."""
    try:
        candles = await get_candles_cached(symbol, db, upstox_client)
        if not candles:
            return None

        indicators = compute_indicators(candles)
        if not indicators:
            return None

        result = _compute_screen_score(indicators)
        result["symbol"] = symbol
        return result
    except Exception as e:
        logger.warning(f"Screener failed for {symbol}: {e}")
        return None


async def screen_all_stocks(
    concurrency: int = 5,
    min_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Screen all stocks in the universe and return ranked results.

    Args:
        concurrency: Max parallel candle fetch tasks.
        min_score: Override minimum score for actionable filter (default: SCREENER_MIN_SCORE).

    Returns dict with:
        - buy_candidates: sorted strongest bullish first
        - short_candidates: sorted strongest bearish first
        - all_results: full list
        - summary stats
    """
    threshold = min_score if min_score is not None else SCREENER_MIN_SCORE
    stocks = await db.stocks.find({}, {"_id": 0, "symbol": 1, "name": 1, "sector": 1}).to_list(500)

    if not stocks:
        return {"buy_candidates": [], "short_candidates": [], "all_results": [], "total": 0}

    stock_meta = {s["symbol"]: s for s in stocks}
    symbols = [s["symbol"] for s in stocks]

    semaphore = asyncio.Semaphore(concurrency)

    async def _screen_with_limit(sym: str):
        async with semaphore:
            return await screen_single_stock(sym)

    tasks = [_screen_with_limit(sym) for sym in symbols]
    raw_results = await asyncio.gather(*tasks)

    all_results = []
    for r in raw_results:
        if r is None:
            continue
        sym = r["symbol"]
        meta = stock_meta.get(sym, {})
        r["name"] = meta.get("name", sym)
        r["sector"] = meta.get("sector", "Unknown")
        all_results.append(r)

    all_results.sort(key=lambda x: abs(x["score"]), reverse=True)

    buy_candidates = [
        r for r in all_results
        if r["score"] >= threshold
    ]
    buy_candidates.sort(key=lambda x: x["score"], reverse=True)

    short_candidates = [
        r for r in all_results
        if r["score"] <= -threshold
    ]
    short_candidates.sort(key=lambda x: x["score"])

    scan_time = datetime.now(timezone.utc).isoformat()

    # Persist screening results
    screen_doc = {
        "id": scan_time,
        "scan_time": scan_time,
        "total_screened": len(all_results),
        "buy_candidates_count": len(buy_candidates),
        "short_candidates_count": len(short_candidates),
        "threshold": threshold,
        "buy_candidates": buy_candidates[:30],
        "short_candidates": short_candidates[:30],
    }
    await db.screener_results.insert_one(screen_doc)

    logger.info(
        f"Screener complete: {len(all_results)} stocks screened, "
        f"{len(buy_candidates)} BUY candidates, {len(short_candidates)} SHORT candidates"
    )

    return {
        "buy_candidates": buy_candidates,
        "short_candidates": short_candidates,
        "all_results": all_results,
        "total_screened": len(all_results),
        "scan_time": scan_time,
    }
