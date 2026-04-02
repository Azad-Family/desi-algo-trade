"""Trade signal validation layer.

Every signal must pass these checks before reaching the trade queue.
This is the last line of defense before real money is at risk.

Usage:
    result = await validate_signal(signal, portfolio_context)
    if not result["passed"]:
        logger.warning(f"Signal rejected: {result['reasons']}")
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from database import db

logger = logging.getLogger(__name__)

# Configurable thresholds
MAX_SINGLE_TRADE_PCT = 20.0        # Max % of capital for one trade
DAILY_LOSS_LIMIT_PCT = 2.0         # Pause if daily loss exceeds this %
MAX_CORRELATED_POSITIONS = 3       # Max stocks with >0.7 correlation
EARNINGS_BLACKOUT_DAYS = 3         # Warn if earnings within N days
ATR_MULTIPLIER_LIMIT = 2.0         # Target/SL must be within 2x ATR
MIN_CONFIDENCE_FOR_LIVE = 80       # Min confidence for live trades
MIN_CONFIDENCE_TO_TRADE = 70       # Min confidence for any trade


async def validate_signal(
    signal: Dict[str, Any],
    trade_mode: str = "sandbox",
    available_capital: float = 0,
) -> Dict[str, Any]:
    """Run all validation checks on a trade signal.

    Returns {passed: bool, reasons: list, warnings: list}
    """
    reasons = []
    warnings = []

    action = signal.get("action", "HOLD")
    symbol = signal.get("stock_symbol", "")
    current_price = float(signal.get("current_price", 0))
    target_price = float(signal.get("target_price", 0))
    stop_loss = float(signal.get("stop_loss", 0))
    confidence = float(signal.get("confidence_score", 0))
    quantity = int(signal.get("quantity", 0))

    # 1. Direction consistency
    if action == "BUY":
        if target_price and target_price <= current_price:
            reasons.append(f"BUY target ({target_price}) must be above current price ({current_price})")
        if stop_loss and stop_loss >= current_price:
            reasons.append(f"BUY stop-loss ({stop_loss}) must be below current price ({current_price})")
    elif action in ("SELL", "SHORT"):
        if target_price and target_price >= current_price:
            reasons.append(f"{action} target ({target_price}) must be below current price ({current_price})")
        if stop_loss and stop_loss <= current_price:
            reasons.append(f"{action} stop-loss ({stop_loss}) must be above current price ({current_price})")

    # 2. Price sanity (ATR bounds)
    if current_price > 0:
        atr = signal.get("atr") or signal.get("key_signals", {}).get("atr")
        if atr:
            atr = float(atr)
            max_distance = atr * ATR_MULTIPLIER_LIMIT
            if target_price and abs(target_price - current_price) > max_distance * 2:
                warnings.append(f"Target distance ({abs(target_price - current_price):.2f}) exceeds 2x ATR ({max_distance:.2f})")
            if stop_loss and abs(stop_loss - current_price) > max_distance * 2:
                warnings.append(f"Stop-loss distance ({abs(stop_loss - current_price):.2f}) exceeds 2x ATR ({max_distance:.2f})")

        # Extreme target check
        if target_price and current_price > 0:
            pct_move = abs(target_price - current_price) / current_price * 100
            if pct_move > 20:
                warnings.append(f"Target implies {pct_move:.1f}% move — unusually large")

    # 3. Capital allocation
    trade_value = current_price * quantity if current_price and quantity else 0
    if available_capital > 0 and trade_value > 0:
        pct_of_capital = (trade_value / available_capital) * 100
        if pct_of_capital > MAX_SINGLE_TRADE_PCT:
            reasons.append(
                f"Trade value Rs.{trade_value:,.0f} is {pct_of_capital:.1f}% of capital "
                f"(max: {MAX_SINGLE_TRADE_PCT}%)"
            )

    # 4. Confidence thresholds
    if confidence < MIN_CONFIDENCE_TO_TRADE:
        reasons.append(f"Confidence {confidence:.0f} below minimum {MIN_CONFIDENCE_TO_TRADE}")
    if trade_mode == "live" and confidence < MIN_CONFIDENCE_FOR_LIVE:
        reasons.append(f"Live trade requires confidence >= {MIN_CONFIDENCE_FOR_LIVE}, got {confidence:.0f}")

    # 5. Double-entry prevention
    if action == "BUY":
        existing = await db.portfolio.find_one({
            "stock_symbol": symbol,
            "trade_mode": trade_mode,
        })
        if existing and existing.get("quantity", 0) > 0:
            warnings.append(f"Already holding {existing['quantity']} shares of {symbol}")

    # 6. Correlation limit
    if action in ("BUY", "SHORT"):
        corr_doc = await db.correlation_data.find_one({"symbol": symbol}, {"_id": 0})
        if corr_doc:
            high_corr_peers = [
                p["symbol"] for p in corr_doc.get("top_peers", [])
                if p.get("correlation", 0) > 0.7
            ]
            # Count how many of these we already hold
            held_correlated = 0
            for peer_sym in high_corr_peers:
                peer_holding = await db.portfolio.find_one({
                    "stock_symbol": peer_sym,
                    "trade_mode": trade_mode,
                    "quantity": {"$gt": 0},
                })
                if peer_holding:
                    held_correlated += 1
            if held_correlated >= MAX_CORRELATED_POSITIONS:
                warnings.append(
                    f"Already hold {held_correlated} stocks highly correlated with {symbol} "
                    f"(max: {MAX_CORRELATED_POSITIONS})"
                )

    # 7. Earnings proximity
    try:
        from fundamentals import is_near_earnings
        if await is_near_earnings(symbol, EARNINGS_BLACKOUT_DAYS):
            warnings.append(f"{symbol} has earnings within {EARNINGS_BLACKOUT_DAYS} days — trade with caution")
    except Exception:
        pass

    # 8. Daily loss limit
    if trade_mode == "live":
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_trades = await db.trade_history.find({
                "trade_mode": "live",
                "executed_at": {"$regex": f"^{today}"},
            }).to_list(200)
            total_pnl = sum(float(t.get("pnl", 0)) for t in today_trades if t.get("pnl") is not None)
            if available_capital > 0 and total_pnl < 0:
                loss_pct = (total_pnl / available_capital) * 100
                if loss_pct < -DAILY_LOSS_LIMIT_PCT:
                    reasons.append(
                        f"Daily loss limit exceeded: {loss_pct:.2f}% "
                        f"(limit: -{DAILY_LOSS_LIMIT_PCT}%)"
                    )
        except Exception:
            pass

    passed = len(reasons) == 0
    result = {
        "passed": passed,
        "reasons": reasons,
        "warnings": warnings,
        "signal_symbol": symbol,
        "signal_action": action,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not passed:
        logger.warning(f"Signal REJECTED for {symbol} {action}: {reasons}")
    elif warnings:
        logger.info(f"Signal PASSED with warnings for {symbol} {action}: {warnings}")

    # Persist validation result for audit trail
    await db.validation_logs.insert_one(result)

    return result


async def validate_pair_signal(
    signal: Dict[str, Any],
    trade_mode: str = "sandbox",
) -> Dict[str, Any]:
    """Validate a pair trade signal.

    Checks both legs are valid and correlation is still above threshold.
    """
    reasons = []
    warnings = []

    long_leg = signal.get("long_leg", "")
    short_leg = signal.get("short_leg", "")
    correlation = float(signal.get("correlation", 0))
    z_score = float(signal.get("z_score", 0))

    # Correlation still valid
    if correlation < 0.6:
        reasons.append(f"Pair correlation ({correlation:.2f}) below minimum (0.6)")

    # Z-score still beyond threshold
    if abs(z_score) < 1.5:
        warnings.append(f"Z-score ({z_score:.2f}) is moderate — signal may be weak")

    # Both legs resolvable
    for leg in [long_leg, short_leg]:
        stock = await db.stocks.find_one({"symbol": leg}) or await db.dynamic_watchlist.find_one({"symbol": leg})
        if not stock:
            reasons.append(f"Pair leg {leg} not found in universe")

    passed = len(reasons) == 0
    result = {
        "passed": passed,
        "reasons": reasons,
        "warnings": warnings,
        "pair": f"{long_leg}/{short_leg}",
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.validation_logs.insert_one(result)
    return result
