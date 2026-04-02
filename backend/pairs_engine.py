"""Pairs trading engine.

Identifies stable pairs from the correlation matrix, monitors spread
z-scores, and generates paired entry/exit signals.

A pair trade is a market-neutral strategy: BUY the undervalued leg,
SHORT the overvalued leg, and profit from convergence.

Workflow:
  1. Daily pre-market: identify_stable_pairs() — find pairs with
     correlation > threshold sustained over 60+ days.
  2. Intraday (every 5 min): scan_pairs_for_signals() — recompute
     z-scores and generate entry/exit signals.
  3. Monitor open pairs: check for convergence, time decay, or
     correlation breakdown.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import uuid as uuid_lib

import numpy as np
import pandas as pd

from database import db

logger = logging.getLogger(__name__)

# Thresholds (configurable via settings later)
MIN_CORRELATION = 0.75
MIN_CORRELATION_DAYS = 60
ZSCORE_ENTRY = 2.0
ZSCORE_EXIT = 0.5
ZSCORE_STOPLOSS = 3.0
MAX_HOLDING_DAYS = 10
CORRELATION_BREAKDOWN = 0.50


# ─── Pair identification ────────────────────────────────────

async def identify_stable_pairs() -> List[Dict[str, Any]]:
    """Scan correlation data to find stable pairs.

    A stable pair has correlation > MIN_CORRELATION sustained over
    MIN_CORRELATION_DAYS. Uses candle data to compute the spread
    z-score for each pair.
    """
    logger.info("Identifying stable pairs for pairs trading...")

    corr_docs = await db.correlation_data.find({}, {"_id": 0}).to_list(500)

    seen = set()
    candidate_pairs = []

    for doc in corr_docs:
        sym_a = doc["symbol"]
        for peer in doc.get("top_peers", []):
            sym_b = peer["symbol"]
            corr = peer["correlation"]

            if corr < MIN_CORRELATION:
                continue

            pair_key = tuple(sorted([sym_a, sym_b]))
            if pair_key in seen:
                continue
            seen.add(pair_key)

            candidate_pairs.append({
                "stock_a": pair_key[0],
                "stock_b": pair_key[1],
                "correlation": corr,
            })

    logger.info(f"Found {len(candidate_pairs)} candidate pairs with corr > {MIN_CORRELATION}")

    # Compute spread z-scores for each pair
    stable_pairs = []
    for pair in candidate_pairs:
        z_data = await _compute_spread_zscore(pair["stock_a"], pair["stock_b"])
        if z_data is None:
            continue

        pair_doc = {
            "id": f"{pair['stock_a']}_{pair['stock_b']}",
            "stock_a": pair["stock_a"],
            "stock_b": pair["stock_b"],
            "correlation": pair["correlation"],
            "mean_spread": z_data["mean_spread"],
            "spread_std": z_data["spread_std"],
            "current_z_score": z_data["current_z_score"],
            "last_price_a": z_data["last_price_a"],
            "last_price_b": z_data["last_price_b"],
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

        await db.pairs_data.update_one(
            {"id": pair_doc["id"]}, {"$set": pair_doc}, upsert=True,
        )
        stable_pairs.append(pair_doc)

    logger.info(f"Stored {len(stable_pairs)} stable pairs with z-score data")
    return stable_pairs


async def _compute_spread_zscore(sym_a: str, sym_b: str) -> Optional[Dict[str, float]]:
    """Compute the price-ratio spread and its z-score for a pair."""
    doc_a = await db.candle_cache.find_one({"symbol": sym_a}, {"_id": 0, "candles": 1})
    doc_b = await db.candle_cache.find_one({"symbol": sym_b}, {"_id": 0, "candles": 1})

    if not doc_a or not doc_b:
        return None

    candles_a = doc_a.get("candles", [])
    candles_b = doc_b.get("candles", [])

    if len(candles_a) < MIN_CORRELATION_DAYS or len(candles_b) < MIN_CORRELATION_DAYS:
        return None

    df_a = pd.DataFrame(candles_a, columns=["ts", "o", "h", "l", "c", "v", "oi"])
    df_b = pd.DataFrame(candles_b, columns=["ts", "o", "h", "l", "c", "v", "oi"])

    df_a["ts"] = pd.to_datetime(df_a["ts"]).dt.date
    df_b["ts"] = pd.to_datetime(df_b["ts"]).dt.date
    df_a = df_a.drop_duplicates("ts")
    df_b = df_b.drop_duplicates("ts")

    merged = pd.merge(df_a[["ts", "c"]], df_b[["ts", "c"]], on="ts", suffixes=("_a", "_b"))
    merged["c_a"] = merged["c_a"].astype(float)
    merged["c_b"] = merged["c_b"].astype(float)

    if len(merged) < MIN_CORRELATION_DAYS:
        return None

    # Price ratio spread
    merged["spread"] = np.log(merged["c_a"] / merged["c_b"])

    lookback = merged.tail(MIN_CORRELATION_DAYS)
    mean_spread = float(lookback["spread"].mean())
    spread_std = float(lookback["spread"].std())

    if spread_std < 1e-8:
        return None

    current_spread = float(merged["spread"].iloc[-1])
    z_score = (current_spread - mean_spread) / spread_std

    return {
        "mean_spread": round(mean_spread, 6),
        "spread_std": round(spread_std, 6),
        "current_z_score": round(z_score, 4),
        "last_price_a": float(merged["c_a"].iloc[-1]),
        "last_price_b": float(merged["c_b"].iloc[-1]),
    }


# ─── Signal generation ──────────────────────────────────────

async def scan_pairs_for_signals() -> List[Dict[str, Any]]:
    """Scan all stored pairs for entry/exit signals based on z-score thresholds.

    Entry: z-score crosses +/- ZSCORE_ENTRY
    Exit:  z-score returns to +/- ZSCORE_EXIT  (or stop-loss / time decay)
    """
    pairs = await db.pairs_data.find({}, {"_id": 0}).to_list(200)
    signals = []

    for pair in pairs:
        z = pair.get("current_z_score", 0)

        # Check for existing open pair trade
        open_trade = await db.pair_trades.find_one({
            "pair_id": pair["id"],
            "status": "open",
        }, {"_id": 0})

        if open_trade:
            # Check exit conditions
            exit_signal = _check_pair_exit(open_trade, z, pair["correlation"])
            if exit_signal:
                signals.append(exit_signal)
        else:
            # Check entry conditions
            if abs(z) >= ZSCORE_ENTRY:
                entry_signal = _generate_pair_entry(pair, z)
                signals.append(entry_signal)

    if signals:
        logger.info(f"Generated {len(signals)} pair trade signals")

    return signals


def _generate_pair_entry(pair: Dict[str, Any], z_score: float) -> Dict[str, Any]:
    """Generate a pair trade entry signal."""
    if z_score > ZSCORE_ENTRY:
        # Stock A overvalued relative to B → SHORT A + BUY B
        long_leg = pair["stock_b"]
        short_leg = pair["stock_a"]
        long_price = pair["last_price_b"]
        short_price = pair["last_price_a"]
    else:
        # Stock B overvalued relative to A → SHORT B + BUY A
        long_leg = pair["stock_a"]
        short_leg = pair["stock_b"]
        long_price = pair["last_price_a"]
        short_price = pair["last_price_b"]

    return {
        "type": "PAIR_ENTRY",
        "pair_id": pair["id"],
        "trade_id": str(uuid_lib.uuid4()),
        "long_leg": long_leg,
        "long_price": long_price,
        "short_leg": short_leg,
        "short_price": short_price,
        "correlation": pair["correlation"],
        "z_score": z_score,
        "z_entry": ZSCORE_ENTRY,
        "z_target": ZSCORE_EXIT,
        "z_stoploss": ZSCORE_STOPLOSS,
        "max_holding_days": MAX_HOLDING_DAYS,
        "reasoning": (
            f"Pair {pair['stock_a']}/{pair['stock_b']} diverged — z-score {z_score:.2f} "
            f"(threshold: ±{ZSCORE_ENTRY}). Correlation: {pair['correlation']:.2f}. "
            f"Strategy: BUY {long_leg} + SHORT {short_leg}, expecting mean reversion."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _check_pair_exit(
    trade: Dict[str, Any],
    current_z: float,
    current_corr: float,
) -> Optional[Dict[str, Any]]:
    """Check if an open pair trade should be closed."""
    reason = None

    # Target hit: z-score returned to near mean
    if abs(current_z) <= ZSCORE_EXIT:
        reason = f"TARGET HIT — z-score normalized to {current_z:.2f} (within ±{ZSCORE_EXIT})"

    # Stop-loss: z-score widened beyond threshold
    entry_z = trade.get("z_score", 0)
    if entry_z > 0 and current_z > ZSCORE_STOPLOSS:
        reason = f"STOP-LOSS — z-score widened to {current_z:.2f} (beyond {ZSCORE_STOPLOSS})"
    elif entry_z < 0 and current_z < -ZSCORE_STOPLOSS:
        reason = f"STOP-LOSS — z-score widened to {current_z:.2f} (beyond -{ZSCORE_STOPLOSS})"

    # Time decay
    opened_at = trade.get("created_at", "")
    if opened_at:
        try:
            opened_dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
            days_held = (datetime.now(timezone.utc) - opened_dt).days
            if days_held >= MAX_HOLDING_DAYS:
                reason = f"TIME DECAY — held {days_held} days (max: {MAX_HOLDING_DAYS})"
        except Exception:
            pass

    # Correlation breakdown
    if current_corr < CORRELATION_BREAKDOWN:
        reason = f"CORRELATION BREAKDOWN — correlation dropped to {current_corr:.2f} (min: {CORRELATION_BREAKDOWN})"

    if not reason:
        return None

    return {
        "type": "PAIR_EXIT",
        "pair_id": trade.get("pair_id"),
        "trade_id": trade.get("trade_id"),
        "long_leg": trade.get("long_leg"),
        "short_leg": trade.get("short_leg"),
        "reason": reason,
        "current_z_score": current_z,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Persistence helpers ────────────────────────────────────

async def open_pair_trade(signal: Dict[str, Any], trade_mode: str = "sandbox") -> Dict[str, Any]:
    """Persist a new pair trade to the database."""
    doc = {
        **signal,
        "status": "open",
        "trade_mode": trade_mode,
    }
    await db.pair_trades.insert_one(doc)
    logger.info(f"Opened pair trade: BUY {signal['long_leg']} + SHORT {signal['short_leg']}")
    return doc


async def close_pair_trade(trade_id: str, exit_signal: Dict[str, Any]) -> bool:
    """Close an open pair trade."""
    result = await db.pair_trades.update_one(
        {"trade_id": trade_id, "status": "open"},
        {"$set": {
            "status": "closed",
            "exit_reason": exit_signal.get("reason", ""),
            "exit_z_score": exit_signal.get("current_z_score"),
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    if result.modified_count:
        logger.info(f"Closed pair trade {trade_id}: {exit_signal.get('reason', '')}")
        return True
    return False


async def get_open_pair_trades(trade_mode: str = "sandbox") -> List[Dict[str, Any]]:
    """Get all open pair trades for a given mode."""
    trades = await db.pair_trades.find(
        {"status": "open", "trade_mode": trade_mode},
        {"_id": 0},
    ).to_list(100)
    return trades


async def get_all_stable_pairs() -> List[Dict[str, Any]]:
    """Return all currently tracked stable pairs."""
    pairs = await db.pairs_data.find({}, {"_id": 0}).to_list(200)
    return pairs
