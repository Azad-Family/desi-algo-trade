"""Cross-stock correlation and sector analysis.

Computes pairwise correlation of daily returns, beta vs Nifty,
and sector rotation scores.  Results are cached in MongoDB
(`db.correlation_data`) and refreshed once daily.

Usage:
    await compute_correlations()           # daily batch job
    peers = await get_correlated_peers("TCS")  # top 5 peers
    text  = format_correlation_for_prompt("TCS", peers)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

from database import db

logger = logging.getLogger(__name__)

CORRELATION_MIN_DAYS = 60
TOP_PEERS = 5


# ─── Helpers ─────────────────────────────────────────────────

def _daily_returns(candles: list) -> pd.Series:
    """Convert raw candle list → pd.Series of daily % returns."""
    if not candles or len(candles) < 2:
        return pd.Series(dtype=float)
    df = pd.DataFrame(candles, columns=["ts", "o", "h", "l", "c", "v", "oi"])
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.sort_values("ts").drop_duplicates("ts")
    df["ret"] = df["c"].astype(float).pct_change()
    df = df.dropna(subset=["ret"])
    return df.set_index("ts")["ret"]


# ─── Core computation ───────────────────────────────────────

async def compute_correlations(min_days: int = CORRELATION_MIN_DAYS) -> Dict[str, Any]:
    """Compute pairwise correlation matrix from cached candle data.

    Returns summary dict with stats; detailed per-symbol data is persisted
    to `db.correlation_data`.
    """
    logger.info("Computing pairwise correlation matrix...")

    cursor = db.candle_cache.find(
        {"candles": {"$exists": True}},
        {"_id": 0, "symbol": 1, "candles": 1},
    )
    docs = await cursor.to_list(500)

    returns_map: Dict[str, pd.Series] = {}
    index_returns: Dict[str, pd.Series] = {}
    for doc in docs:
        sym = doc["symbol"]
        ret = _daily_returns(doc["candles"])
        if len(ret) >= min_days:
            if sym.startswith("_IDX_"):
                index_returns[sym] = ret
            else:
                returns_map[sym] = ret

    symbols = sorted(returns_map.keys())
    n = len(symbols)
    logger.info(f"Building {n}x{n} correlation matrix ({n} symbols with >= {min_days} days)")

    if n < 2:
        logger.warning("Not enough symbols for correlation analysis")
        return {"symbols": n, "pairs_stored": 0}

    combined = pd.DataFrame(returns_map)
    combined = combined.dropna(axis=0, how="all")

    corr_matrix = combined.corr(min_periods=min_days)

    pairs_stored = 0
    now = datetime.utcnow().isoformat()

    nifty_ret = index_returns.get("_IDX_NIFTY50")

    for sym in symbols:
        if sym not in corr_matrix:
            continue

        row = corr_matrix[sym].drop(sym, errors="ignore")
        row = row.dropna().sort_values(ascending=False)

        top_peers = []
        for peer_sym, corr_val in row.head(TOP_PEERS).items():
            if np.isnan(corr_val):
                continue
            top_peers.append({
                "symbol": peer_sym,
                "correlation": round(float(corr_val), 4),
            })

        beta = None
        if nifty_ret is not None and sym in returns_map:
            aligned = pd.DataFrame({"stock": returns_map[sym], "nifty": nifty_ret}).dropna()
            if len(aligned) >= 30:
                cov = aligned["stock"].cov(aligned["nifty"])
                var_nifty = aligned["nifty"].var()
                if var_nifty > 0:
                    beta = round(float(cov / var_nifty), 3)

        doc = {
            "symbol": sym,
            "top_peers": top_peers,
            "beta_nifty": beta,
            "computed_at": now,
        }
        await db.correlation_data.update_one(
            {"symbol": sym}, {"$set": doc}, upsert=True,
        )
        pairs_stored += 1

    logger.info(f"Correlation data stored for {pairs_stored} symbols")
    return {"symbols": n, "pairs_stored": pairs_stored}


# ─── Query helpers ───────────────────────────────────────────

async def get_correlated_peers(symbol: str) -> List[Dict[str, Any]]:
    """Return top correlated peers for a symbol, enriched with current price data."""
    symbol = symbol.upper()
    doc = await db.correlation_data.find_one({"symbol": symbol}, {"_id": 0})
    if not doc:
        return []

    peers = doc.get("top_peers", [])

    # Enrich with latest change_percent from db.stocks
    for p in peers:
        stock = await db.stocks.find_one({"symbol": p["symbol"]}, {"_id": 0, "change_percent": 1, "sector": 1, "current_price": 1})
        if stock:
            p["change_pct_1d"] = stock.get("change_percent", 0)
            p["sector"] = stock.get("sector", "")
            p["price"] = stock.get("current_price", 0)

    return peers


async def get_beta(symbol: str) -> Optional[float]:
    """Return the stock's beta vs Nifty 50."""
    doc = await db.correlation_data.find_one({"symbol": symbol.upper()}, {"_id": 0, "beta_nifty": 1})
    return doc.get("beta_nifty") if doc else None


async def get_pair_correlation(symbol_a: str, symbol_b: str) -> Optional[float]:
    """Return the pairwise correlation between two symbols."""
    doc = await db.correlation_data.find_one({"symbol": symbol_a.upper()}, {"_id": 0})
    if not doc:
        return None
    for p in doc.get("top_peers", []):
        if p["symbol"] == symbol_b.upper():
            return p["correlation"]
    # If not in top-5, check the reverse
    doc_b = await db.correlation_data.find_one({"symbol": symbol_b.upper()}, {"_id": 0})
    if doc_b:
        for p in doc_b.get("top_peers", []):
            if p["symbol"] == symbol_a.upper():
                return p["correlation"]
    return None


# ─── Prompt formatting ──────────────────────────────────────

def format_correlation_for_prompt(
    symbol: str,
    peers: List[Dict[str, Any]],
    beta: Optional[float] = None,
    sector_rank: Optional[Dict[str, Any]] = None,
) -> str:
    """Format correlation data as text for injection into AI prompts."""
    if not peers:
        return ""

    lines = ["CORRELATED PEERS:"]
    for p in peers:
        corr = p.get("correlation", 0)
        change = p.get("change_pct_1d", 0)
        if change is None:
            change = 0

        if corr > 0.6 and change > 0.5:
            direction = "CONFIRMING bullish"
        elif corr > 0.6 and change < -0.5:
            direction = "CONFIRMING bearish"
        else:
            direction = "NEUTRAL"

        lines.append(
            f"  - {p['symbol']} (corr: {corr:.2f}, today: {change:+.1f}%) — {direction}"
        )

    if beta is not None:
        lines.append(f"BETA vs Nifty 50: {beta:.2f}")

    if sector_rank:
        sec = sector_rank.get("sector", "")
        rank = sector_rank.get("rank", "?")
        total = sector_rank.get("stock_count", "?")
        avg = sector_rank.get("avg_change_1d", 0)
        lines.append(f"SECTOR: {sec} rank #{rank} ({avg:+.2f}% avg today)")

    return "\n".join(lines)
