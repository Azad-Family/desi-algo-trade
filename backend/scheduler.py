"""Daily automated trading scheduler.

Pipeline:
1. Pre-market (09:20 IST): Run screener on all 125 stocks
2. Filter: Pick top N candidates by score
3. Deep analysis: Run full AI analysis on filtered candidates
4. Classify each signal into one of 4 types:
   - BUY CNC:        bullish + short/medium term → delivery
   - BUY INTRADAY:   bullish + intraday horizon → auto-squareoff at 15:15
   - SHORT INTRADAY:  bearish → sell first, buy back intraday
   - SELL CNC:       exit existing CNC holdings that hit SL/target
5. Sandbox: auto-execute all 4 types with virtual capital
6. Monitor: check SL/target throughout the day (every 60s)
7. 15:15 IST: auto-squareoff all INTRADAY positions

Uses asyncio background tasks.
"""
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, time
import pytz

from database import db
from screener import screen_all_stocks
from sandbox import (
    get_or_create_account,
    execute_sandbox_entry,
    check_sandbox_exits,
    update_sandbox_prices,
    squareoff_intraday_positions,
)
from ai_engine import generate_trade_recommendation

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

_scheduler_task: Optional[asyncio.Task] = None
_monitor_task: Optional[asyncio.Task] = None
_running = False


async def _get_scheduler_config() -> Dict[str, Any]:
    config = await db.scheduler_config.find_one({"id": "scheduler_config"}, {"_id": 0})
    if not config:
        config = {
            "id": "scheduler_config",
            "enabled": True,
            "scan_time": "09:20",
            "exit_scan_time": "15:00",
            "max_positions": 5,
            "max_trade_value": 20000.0,
            "min_screener_score": 30.0,
            "auto_execute_sandbox": True,
            "screener_concurrency": 5,
        }
        await db.scheduler_config.insert_one(config)
    return config


def _ist_now() -> datetime:
    return datetime.now(IST)


def _is_market_hours() -> bool:
    now = _ist_now()
    if now.weekday() >= 5:
        return False
    market_open = time(9, 15)
    market_close = time(15, 30)
    return market_open <= now.time() <= market_close


def _classify_trade(action: str, trade_horizon: str) -> tuple:
    """Classify a trade signal into (action, product_type).

    Returns:
        ("BUY", "CNC")       — bullish, swing/positional
        ("BUY", "INTRADAY")  — bullish, intraday
        ("SHORT", "INTRADAY") — bearish (always intraday in India)
    """
    if action == "SHORT":
        return "SHORT", "INTRADAY"

    if action == "BUY":
        if trade_horizon == "short_term":
            return "BUY", "INTRADAY"
        return "BUY", "CNC"

    return action, "CNC"


async def run_daily_scan() -> Dict[str, Any]:
    """Full daily pipeline: screen -> filter -> deep AI analysis -> sandbox execute.

    Generates all 4 trade types: BUY CNC, BUY INTRADAY, SHORT INTRADAY, SELL CNC.
    """
    config = await _get_scheduler_config()
    scan_log = {
        "id": datetime.now(IST).strftime("%Y%m%d_%H%M%S"),
        "started_at": datetime.now(IST).isoformat(),
        "phase": "screening",
        "status": "running",
    }
    await db.scheduler_logs.insert_one(scan_log)

    try:
        # Phase 1: Screen all stocks
        logger.info("=== DAILY SCAN: Phase 1 — Screening all stocks ===")
        screen_results = await screen_all_stocks(
            concurrency=config.get("screener_concurrency", 5),
            min_score=config.get("min_screener_score", 30.0),
        )

        buy_candidates = screen_results["buy_candidates"]
        short_candidates = screen_results["short_candidates"]
        total_screened = screen_results["total_screened"]

        logger.info(
            f"Screening done: {total_screened} stocks -> "
            f"{len(buy_candidates)} BUY candidates, {len(short_candidates)} SHORT candidates"
        )

        # Phase 2: Deep AI analysis on top candidates
        logger.info("=== DAILY SCAN: Phase 2 — Deep AI analysis ===")
        max_positions = config.get("max_positions", 5)
        max_trade_val = config.get("max_trade_value", 20000.0)

        top_buys = buy_candidates[:max_positions]
        top_shorts = short_candidates[:3]

        signals_generated = []
        sandbox_entries = []
        type_counts = {"BUY_CNC": 0, "BUY_INTRADAY": 0, "SHORT_INTRADAY": 0}

        for candidate in top_buys + top_shorts:
            sym = candidate["symbol"]
            stock = await db.stocks.find_one({"symbol": sym}, {"_id": 0})
            if not stock:
                continue

            try:
                from routes import _get_technical_data
                technical_data, indicators_raw = await _get_technical_data(sym)

                recommendation = await generate_trade_recommendation(
                    sym,
                    stock.get("name", sym),
                    stock.get("sector", ""),
                    technical_data=technical_data,
                    indicators_raw=indicators_raw,
                    max_trade_value=max_trade_val,
                    risk_per_trade_pct=2.0,
                )

                if not recommendation:
                    continue

                raw_action = recommendation["action"]
                if raw_action not in ("BUY", "SHORT"):
                    continue

                trade_horizon = recommendation.get("trade_horizon", "medium_term")
                action, product_type = _classify_trade(raw_action, trade_horizon)
                type_key = f"{action}_{product_type}"
                type_counts[type_key] = type_counts.get(type_key, 0) + 1

                # Sandbox: auto-execute
                if config.get("auto_execute_sandbox", True):
                    account = await get_or_create_account()
                    entry_price = recommendation["current_price"]
                    qty = recommendation["quantity"]
                    cost = entry_price * qty

                    if cost <= account["current_capital"] and cost <= max_trade_val:
                        entry_result = await execute_sandbox_entry(
                            symbol=sym,
                            name=recommendation["stock_name"],
                            action=action,
                            quantity=qty,
                            entry_price=entry_price,
                            product_type=product_type,
                            target_price=recommendation.get("target_price"),
                            stop_loss=recommendation.get("stop_loss"),
                            sector=stock.get("sector", ""),
                            ai_reasoning=recommendation.get("ai_reasoning", ""),
                            confidence_score=recommendation.get("confidence_score", 0),
                            trade_horizon=trade_horizon,
                        )
                        if entry_result["success"]:
                            sandbox_entries.append(entry_result["holding"])
                            logger.info(f"Sandbox auto-entry: {action} {product_type} {sym}")

                signals_generated.append({
                    "symbol": sym, "action": action, "product_type": product_type,
                    "price": recommendation["current_price"],
                    "confidence": recommendation["confidence_score"],
                })

                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Deep analysis failed for {sym}: {e}")

        # Phase 3: Check existing CNC holdings for exit signals
        logger.info("=== DAILY SCAN: Phase 3 — CNC exit scan ===")
        cnc_exits = await _scan_cnc_exits(max_trade_val)

        result = {
            "total_screened": total_screened,
            "buy_candidates": len(buy_candidates),
            "short_candidates": len(short_candidates),
            "deep_analyzed": len(top_buys) + len(top_shorts),
            "signals_generated": len(signals_generated),
            "sandbox_entries": len(sandbox_entries),
            "cnc_exits": cnc_exits,
            "type_counts": type_counts,
            "signals": signals_generated,
            "completed_at": datetime.now(IST).isoformat(),
        }

        await db.scheduler_logs.update_one(
            {"id": scan_log["id"]},
            {"$set": {"status": "completed", "result": result, "completed_at": result["completed_at"]}}
        )

        logger.info(f"Daily scan complete: {result}")
        return result

    except Exception as e:
        logger.error(f"Daily scan failed: {e}")
        await db.scheduler_logs.update_one(
            {"id": scan_log["id"]},
            {"$set": {"status": "failed", "error": str(e)}}
        )
        return {"error": str(e)}


async def _scan_cnc_exits(max_trade_val: float) -> int:
    """Check CNC sandbox holdings for exit signals (SELL CNC).

    For each CNC holding, re-runs technical analysis and generates
    a SELL signal if the AI recommends exiting.
    """
    cnc_holdings = await db.sandbox_holdings.find({"product_type": "CNC"}, {"_id": 0}).to_list(100)
    if not cnc_holdings:
        return 0

    from sandbox import execute_sandbox_exit, upstox_client as sb_client
    symbols = [h["stock_symbol"] for h in cnc_holdings]
    quotes = await sb_client.get_batch_quotes(symbols)

    exits = 0
    for h in cnc_holdings:
        sym = h["stock_symbol"]
        price_data = quotes.get(sym)
        if not price_data:
            continue

        ltp = float(price_data.get("ltp", 0))
        if ltp <= 0:
            continue

        sl = h.get("stop_loss")
        tgt = h.get("target_price")
        exit_reason = None

        if h["action"] == "BUY":
            if sl and ltp <= sl:
                exit_reason = "stop_loss_hit"
            elif tgt and ltp >= tgt:
                exit_reason = "target_hit"

        if exit_reason:
            result = await execute_sandbox_exit(sym, ltp, exit_reason, product_type="CNC")
            if result["success"]:
                exits += 1
                logger.info(f"CNC exit: SELL {sym} @ Rs.{ltp} [{exit_reason}]")

    return exits


async def _monitor_loop():
    """Background loop that checks sandbox holdings for SL/target hits every 60s.

    Also triggers intraday squareoff at 15:15 IST.
    """
    global _running
    logger.info("Sandbox monitor loop started")

    last_squareoff_date = None

    while _running:
        try:
            if _is_market_hours():
                exits = await check_sandbox_exits()
                if exits:
                    logger.info(f"Auto-exited {len(exits)} sandbox positions")
                await update_sandbox_prices()

                # Intraday squareoff at 15:15 IST (once per day)
                now = _ist_now()
                today = now.date()
                if now.time() >= time(15, 15) and last_squareoff_date != today:
                    last_squareoff_date = today
                    sq_exits = await squareoff_intraday_positions()
                    if sq_exits:
                        logger.info(f"Squareoff: {len(sq_exits)} intraday positions closed at 15:15")

            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Monitor loop error: {e}")
            await asyncio.sleep(30)

    logger.info("Sandbox monitor loop stopped")


async def _scheduler_loop():
    """Background loop that triggers daily scans at configured times."""
    global _running
    logger.info("Scheduler loop started")

    last_scan_date = None

    while _running:
        try:
            config = await _get_scheduler_config()
            if not config.get("enabled"):
                await asyncio.sleep(30)
                continue

            now = _ist_now()
            today = now.date()

            if now.weekday() >= 5:
                await asyncio.sleep(60)
                continue

            scan_time_str = config.get("scan_time", "09:20")
            scan_h, scan_m = map(int, scan_time_str.split(":"))
            scan_time_val = time(scan_h, scan_m)

            if now.time() >= scan_time_val and last_scan_date != today:
                logger.info("Scheduler triggering daily scan")
                last_scan_date = today
                await run_daily_scan()

            await asyncio.sleep(30)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
            await asyncio.sleep(60)

    logger.info("Scheduler loop stopped")


async def start_scheduler():
    """Start the scheduler and monitor background tasks."""
    global _scheduler_task, _monitor_task, _running

    if _running:
        return {"status": "already_running"}

    _running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    _monitor_task = asyncio.create_task(_monitor_loop())

    await db.scheduler_config.update_one(
        {"id": "scheduler_config"},
        {"$set": {"enabled": True}},
        upsert=True,
    )

    logger.info("Scheduler started (daily scan + intraday monitor)")
    return {"status": "started"}


async def stop_scheduler():
    """Stop the scheduler and monitor background tasks."""
    global _scheduler_task, _monitor_task, _running

    _running = False

    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()

    _scheduler_task = None
    _monitor_task = None

    await db.scheduler_config.update_one(
        {"id": "scheduler_config"},
        {"$set": {"enabled": False}},
        upsert=True,
    )

    logger.info("Scheduler stopped")
    return {"status": "stopped"}


def is_scheduler_running() -> bool:
    return _running
