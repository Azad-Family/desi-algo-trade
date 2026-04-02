"""Sandbox (paper) trading engine.

Manages a virtual portfolio with Rs.1,00,000 starting capital.
Supports 4 trade types:
  - BUY CNC:       Buy for delivery (hold overnight)
  - BUY INTRADAY:  Buy intraday (auto-squareoff at 15:15 IST)
  - SHORT INTRADAY: Sell first, buy back intraday (auto-squareoff at 15:15)
  - SELL CNC:      Exit an existing CNC holding

Executes trades automatically based on AI signals without touching
the real Upstox order API. Tracks performance, win rate, and P&L
so the AI can learn from outcomes.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, time
import uuid as uuid_lib
import pytz

from database import db
from trading import UpstoxClient
from models import SandboxAccount, SandboxHolding, SandboxTrade

logger = logging.getLogger(__name__)

STARTING_CAPITAL = 100000.0
IST = pytz.timezone("Asia/Kolkata")
INTRADAY_SQUAREOFF_TIME = time(15, 15)

upstox_client = UpstoxClient()


async def get_or_create_account() -> Dict[str, Any]:
    """Get the sandbox account, creating it if it doesn't exist."""
    account = await db.sandbox_account.find_one({"id": "sandbox_account"}, {"_id": 0})
    if not account:
        acc = SandboxAccount(starting_capital=STARTING_CAPITAL, current_capital=STARTING_CAPITAL)
        doc = acc.model_dump()
        await db.sandbox_account.insert_one(doc)
        account = await db.sandbox_account.find_one({"id": "sandbox_account"}, {"_id": 0})
        logger.info(f"Created sandbox account with Rs.{STARTING_CAPITAL:,.0f} capital")
    return account


async def _update_account_stats():
    """Recalculate account-level stats from trade history."""
    account = await get_or_create_account()
    trades = await db.sandbox_trades.find({}, {"_id": 0}).to_list(1000)
    holdings = await db.sandbox_holdings.find({}, {"_id": 0}).to_list(100)

    total_trades = len(trades)
    winning = sum(1 for t in trades if t["pnl"] > 0)
    losing = sum(1 for t in trades if t["pnl"] < 0)
    total_realized_pnl = sum(t["pnl"] for t in trades)

    invested = sum(h["entry_price"] * h["quantity"] for h in holdings)
    current_val = sum(h["current_price"] * h["quantity"] for h in holdings)

    # Unrealized P&L must account for SHORT positions (profit when price drops)
    unrealized_pnl = 0
    for h in holdings:
        entry_val = h["entry_price"] * h["quantity"]
        curr_val = h["current_price"] * h["quantity"]
        if h.get("action") == "SHORT":
            unrealized_pnl += entry_val - curr_val
        else:
            unrealized_pnl += curr_val - entry_val

    capital = STARTING_CAPITAL + total_realized_pnl - invested
    total_pnl = total_realized_pnl + unrealized_pnl

    pnl_list = [t["pnl"] for t in trades]
    best_pnl = max(pnl_list) if pnl_list else 0
    worst_pnl = min(pnl_list) if pnl_list else 0
    avg_pnl = (sum(pnl_list) / len(pnl_list)) if pnl_list else 0

    max_dd = 0
    peak = 0
    running = 0
    for t in sorted(trades, key=lambda x: x.get("exited_at", "")):
        running += t["pnl"]
        peak = max(peak, running)
        dd = peak - running
        max_dd = max(max_dd, dd)

    update = {
        "current_capital": round(capital, 2),
        "invested_value": round(invested, 2),
        "current_value": round(current_val, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / STARTING_CAPITAL) * 100, 2) if STARTING_CAPITAL else 0,
        "total_trades": total_trades,
        "winning_trades": winning,
        "losing_trades": losing,
        "win_rate": round((winning / total_trades) * 100, 1) if total_trades else 0,
        "max_drawdown": round(max_dd, 2),
        "best_trade_pnl": round(best_pnl, 2),
        "worst_trade_pnl": round(worst_pnl, 2),
        "avg_trade_pnl": round(avg_pnl, 2),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.sandbox_account.update_one({"id": "sandbox_account"}, {"$set": update})
    return {**account, **update}


async def execute_sandbox_entry(
    symbol: str,
    name: str,
    action: str,
    quantity: int,
    entry_price: float,
    product_type: str = "CNC",
    target_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    sector: str = "",
    ai_reasoning: str = "",
    confidence_score: float = 0.0,
    trade_horizon: str = "short_term",
) -> Dict[str, Any]:
    """Execute a sandbox BUY or SHORT entry.

    product_type: CNC (delivery, can hold overnight) or INTRADAY (auto-squareoff at 15:15)
    """
    account = await get_or_create_account()
    cost = entry_price * quantity

    if cost > account["current_capital"]:
        return {"success": False, "error": "Insufficient sandbox capital"}

    # For intraday: allow same stock in CNC + intraday
    # For CNC: don't allow duplicate
    existing_query = {"stock_symbol": symbol, "product_type": product_type}
    existing = await db.sandbox_holdings.find_one(existing_query, {"_id": 0})
    if existing:
        return {"success": False, "error": f"Already holding {symbol} ({product_type}) in sandbox"}

    holding = SandboxHolding(
        stock_symbol=symbol,
        stock_name=name,
        action=action,
        product_type=product_type,
        quantity=quantity,
        entry_price=entry_price,
        current_price=entry_price,
        target_price=target_price,
        stop_loss=stop_loss,
        sector=sector,
        ai_reasoning=ai_reasoning,
        confidence_score=confidence_score,
        trade_horizon=trade_horizon,
    )
    await db.sandbox_holdings.insert_one(holding.model_dump())

    new_capital = account["current_capital"] - cost
    await db.sandbox_account.update_one(
        {"id": "sandbox_account"},
        {"$set": {"current_capital": round(new_capital, 2), "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    tag = f"{action} {product_type}"
    logger.info(f"Sandbox {tag}: {symbol} x{quantity} @ Rs.{entry_price} (cost Rs.{cost:.0f})")
    return {"success": True, "holding": holding.model_dump()}


async def execute_sandbox_exit(
    symbol: str,
    exit_price: float,
    exit_reason: str = "manual",
    product_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Exit a sandbox position. Records the trade and releases capital.

    If product_type is specified, only exits that specific position type.
    """
    query = {"stock_symbol": symbol}
    if product_type:
        query["product_type"] = product_type
    holding = await db.sandbox_holdings.find_one(query, {"_id": 0})
    if not holding:
        return {"success": False, "error": f"No sandbox holding for {symbol}"}

    qty = holding["quantity"]
    entry = holding["entry_price"]
    h_product = holding.get("product_type", "CNC")

    if holding["action"] == "SHORT":
        pnl = (entry - exit_price) * qty
    else:
        pnl = (exit_price - entry) * qty

    pnl_pct = (pnl / (entry * qty)) * 100 if entry * qty > 0 else 0

    entered_at = holding.get("entered_at", "")
    duration_hours = 0
    if entered_at:
        try:
            entered_dt = datetime.fromisoformat(entered_at)
            duration_hours = (datetime.now(timezone.utc) - entered_dt).total_seconds() / 3600
        except Exception:
            pass

    trade = SandboxTrade(
        stock_symbol=symbol,
        stock_name=holding.get("stock_name", symbol),
        action=holding["action"],
        product_type=h_product,
        entry_price=entry,
        exit_price=exit_price,
        quantity=qty,
        pnl=round(pnl, 2),
        pnl_pct=round(pnl_pct, 2),
        holding_duration_hours=round(duration_hours, 1),
        target_price=holding.get("target_price"),
        stop_loss=holding.get("stop_loss"),
        exit_reason=exit_reason,
        ai_reasoning=holding.get("ai_reasoning", ""),
        confidence_score=holding.get("confidence_score", 0),
        entered_at=entered_at,
    )
    await db.sandbox_trades.insert_one(trade.model_dump())

    # Capital release depends on position type:
    # LONG exit (selling shares): you receive sale proceeds = exit_price * qty
    # SHORT cover (buying back): you release margin (entry_price * qty) and realize P&L
    if holding["action"] == "SHORT":
        released = (entry * qty) + pnl
    else:
        released = exit_price * qty
    account = await get_or_create_account()
    new_capital = account["current_capital"] + released
    await db.sandbox_account.update_one(
        {"id": "sandbox_account"},
        {"$set": {"current_capital": round(new_capital, 2)}}
    )

    await db.sandbox_holdings.delete_one({"id": holding["id"]})
    await _update_account_stats()

    tag = f"{holding['action']} {h_product}"
    logger.info(f"Sandbox EXIT [{tag}] {symbol} @ Rs.{exit_price} — P&L: Rs.{pnl:.2f} ({pnl_pct:.1f}%) [{exit_reason}]")
    return {"success": True, "trade": trade.model_dump()}


async def squareoff_intraday_positions() -> List[Dict[str, Any]]:
    """Auto-squareoff all INTRADAY positions. Called at 15:15 IST."""
    holdings = await db.sandbox_holdings.find({"product_type": "INTRADAY"}, {"_id": 0}).to_list(100)
    if not holdings:
        return []

    symbols = [h["stock_symbol"] for h in holdings]
    quotes = await upstox_client.get_batch_quotes(symbols)

    exits = []
    for h in holdings:
        sym = h["stock_symbol"]
        price_data = quotes.get(sym)
        ltp = float(price_data.get("ltp", 0)) if price_data else 0

        if ltp <= 0:
            ltp = h["current_price"] if h["current_price"] > 0 else h["entry_price"]

        result = await execute_sandbox_exit(sym, ltp, "intraday_squareoff", product_type="INTRADAY")
        if result["success"]:
            exits.append(result["trade"])
            logger.info(f"Intraday squareoff: {h['action']} {sym} @ Rs.{ltp}")

    if exits:
        logger.info(f"Squared off {len(exits)} intraday positions at 15:15 IST")
    return exits


async def check_sandbox_exits() -> List[Dict[str, Any]]:
    """Check all sandbox holdings for stop-loss or target hits.

    Called periodically by the scheduler to auto-exit positions.
    Also checks if it's past 15:15 IST and squareoff intraday positions.
    """
    now_ist = datetime.now(IST)

    # Auto-squareoff intraday positions at 15:15
    if now_ist.weekday() < 5 and now_ist.time() >= INTRADAY_SQUAREOFF_TIME:
        intraday_holdings = await db.sandbox_holdings.find({"product_type": "INTRADAY"}, {"_id": 0}).to_list(100)
        if intraday_holdings:
            return await squareoff_intraday_positions()

    holdings = await db.sandbox_holdings.find({}, {"_id": 0}).to_list(100)
    if not holdings:
        return []

    symbols = list(set(h["stock_symbol"] for h in holdings))
    quotes = await upstox_client.get_batch_quotes(symbols)

    exits = []
    for h in holdings:
        sym = h["stock_symbol"]
        price_data = quotes.get(sym)
        if not price_data:
            continue

        ltp = float(price_data.get("ltp", 0))
        if ltp <= 0:
            continue

        if h["action"] == "BUY":
            pnl = (ltp - h["entry_price"]) * h["quantity"]
        else:
            pnl = (h["entry_price"] - ltp) * h["quantity"]
        pnl_pct = (pnl / (h["entry_price"] * h["quantity"])) * 100 if h["entry_price"] > 0 else 0

        await db.sandbox_holdings.update_one(
            {"id": h["id"]},
            {"$set": {"current_price": ltp, "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2)}}
        )

        exit_reason = None
        sl = h.get("stop_loss")
        tgt = h.get("target_price")

        if h["action"] == "BUY":
            if sl and ltp <= sl:
                exit_reason = "stop_loss_hit"
            elif tgt and ltp >= tgt:
                exit_reason = "target_hit"
        elif h["action"] == "SHORT":
            if sl and ltp >= sl:
                exit_reason = "stop_loss_hit"
            elif tgt and ltp <= tgt:
                exit_reason = "target_hit"

        if exit_reason:
            result = await execute_sandbox_exit(sym, ltp, exit_reason, product_type=h.get("product_type"))
            if result["success"]:
                exits.append(result["trade"])

    return exits


async def update_sandbox_prices() -> int:
    """Refresh current prices on all sandbox holdings."""
    holdings = await db.sandbox_holdings.find({}, {"_id": 0}).to_list(100)
    if not holdings:
        return 0

    symbols = list(set(h["stock_symbol"] for h in holdings))
    quotes = await upstox_client.get_batch_quotes(symbols)

    updated = 0
    for h in holdings:
        sym = h["stock_symbol"]
        price_data = quotes.get(sym)
        if not price_data:
            continue

        ltp = float(price_data.get("ltp", 0))
        if ltp <= 0:
            continue

        if h["action"] == "BUY":
            pnl = (ltp - h["entry_price"]) * h["quantity"]
        else:
            pnl = (h["entry_price"] - ltp) * h["quantity"]
        pnl_pct = (pnl / (h["entry_price"] * h["quantity"])) * 100 if h["entry_price"] > 0 else 0

        await db.sandbox_holdings.update_one(
            {"id": h["id"]},
            {"$set": {"current_price": ltp, "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2)}}
        )
        updated += 1

    await _update_account_stats()
    return updated


async def reset_sandbox() -> Dict[str, Any]:
    """Reset the sandbox account to starting state."""
    await db.sandbox_account.delete_many({})
    await db.sandbox_holdings.delete_many({})
    await db.sandbox_trades.delete_many({})
    await db.screener_results.delete_many({})

    account = await get_or_create_account()
    logger.info("Sandbox account reset to starting capital")
    return account


async def get_strategy_insights() -> Dict[str, Any]:
    """Analyze sandbox trade history to extract strategy insights."""
    trades = await db.sandbox_trades.find({}, {"_id": 0}).to_list(1000)
    if not trades:
        return {"message": "No completed sandbox trades yet", "total_trades": 0}

    buy_cnc = [t for t in trades if t["action"] == "BUY" and t.get("product_type") == "CNC"]
    buy_intra = [t for t in trades if t["action"] == "BUY" and t.get("product_type") == "INTRADAY"]
    short_intra = [t for t in trades if t["action"] == "SHORT" and t.get("product_type") == "INTRADAY"]
    sell_cnc = [t for t in trades if t["action"] == "SHORT" and t.get("product_type") == "CNC"]

    def _stats(trade_list):
        if not trade_list:
            return {"count": 0, "total_pnl": 0, "win_rate": 0, "avg_pnl": 0}
        total = sum(t["pnl"] for t in trade_list)
        wins = sum(1 for t in trade_list if t["pnl"] > 0)
        return {
            "count": len(trade_list),
            "total_pnl": round(total, 2),
            "win_rate": round(wins / len(trade_list) * 100, 1),
            "avg_pnl": round(total / len(trade_list), 2),
        }

    reason_groups = {}
    for t in trades:
        r = t.get("exit_reason", "unknown")
        reason_groups.setdefault(r, []).append(t)

    high_conf = [t for t in trades if t.get("confidence_score", 0) >= 70]
    med_conf = [t for t in trades if 40 <= t.get("confidence_score", 0) < 70]
    low_conf = [t for t in trades if t.get("confidence_score", 0) < 40]

    quick_trades = [t for t in trades if t.get("holding_duration_hours", 0) < 8]
    swing_trades = [t for t in trades if t.get("holding_duration_hours", 0) >= 8]

    sorted_by_pnl = sorted(trades, key=lambda x: x["pnl"], reverse=True)
    top_winners = sorted_by_pnl[:5]
    top_losers = sorted_by_pnl[-5:]

    return {
        "total_trades": len(trades),
        "overall": _stats(trades),
        "by_trade_type": {
            "BUY_CNC": _stats(buy_cnc),
            "BUY_INTRADAY": _stats(buy_intra),
            "SHORT_INTRADAY": _stats(short_intra),
            "SELL_CNC": _stats(sell_cnc),
        },
        "by_exit_reason": {r: _stats(tl) for r, tl in reason_groups.items()},
        "by_confidence": {
            "high_70+": _stats(high_conf),
            "medium_40-70": _stats(med_conf),
            "low_0-40": _stats(low_conf),
        },
        "by_duration": {
            "intraday": _stats(quick_trades),
            "swing": _stats(swing_trades),
        },
        "top_winners": [{
            "symbol": t["stock_symbol"], "pnl": t["pnl"],
            "pnl_pct": t["pnl_pct"], "action": t["action"],
            "product_type": t.get("product_type", "CNC"),
            "exit_reason": t.get("exit_reason", ""),
        } for t in top_winners],
        "top_losers": [{
            "symbol": t["stock_symbol"], "pnl": t["pnl"],
            "pnl_pct": t["pnl_pct"], "action": t["action"],
            "product_type": t.get("product_type", "CNC"),
            "exit_reason": t.get("exit_reason", ""),
        } for t in top_losers],
    }
