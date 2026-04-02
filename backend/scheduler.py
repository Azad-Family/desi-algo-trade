"""Unified daily trading scheduler — scans once, serves both modes.

Analysis happens once. Execution is mode-specific:
  Sandbox → auto-execute (paper trading for strategy testing)
  Live    → queue as pending TradeRecommendation (manual approval required)

Multi-window pipeline:
  05:30 IST — Pre-market data refresh (candles, correlations, fundamentals)
  09:20 IST — Entry scan: screen universe → deep AI → BUY/SHORT signals
  10:30 IST — Exit scan: AI re-evaluates all CNC holdings (sandbox + live)
  12:00 IST — Mid-day review (pairs check)
  14:30 IST — Exit prep: mechanical SL/target + second AI exit scan
  15:15 IST — Intraday squareoff (sandbox)
  15:30 IST — EOD cleanup (prune watchlist)

Intraday monitor (every 60s):
  - SL/target hits for sandbox positions
  - Trailing stop-loss (1% breakeven, 2% lock-in)
  - Pair z-score monitoring

Uses asyncio background tasks.
"""
import logging
import asyncio
import uuid as uuid_lib
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
from ai_engine import generate_trade_recommendation, deep_research
from models import TradeRecommendation

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

_scheduler_task: Optional[asyncio.Task] = None
_monitor_task: Optional[asyncio.Task] = None
_running = False

# Trailing stop-loss thresholds
TRAILING_SL_BREAKEVEN_PCT = 1.0   # If up 1%, trail SL to breakeven
TRAILING_SL_LOCKIN_PCT = 2.0      # If up 2%, trail SL to lock in 1%


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


async def _pre_market_refresh():
    """Pre-market data refresh: candles, correlations, fundamentals, earnings."""
    logger.info("=== PRE-MARKET: Data refresh ===")
    try:
        from market_context import get_market_context
        await get_market_context(force_refresh=True)
        logger.info("Market context refreshed")
    except Exception as e:
        logger.warning(f"Market context refresh failed: {e}")

    try:
        from correlation import compute_correlations
        corr_result = await compute_correlations()
        logger.info(f"Correlation matrix computed: {corr_result.get('pairs_stored', 0)} symbols")
    except Exception as e:
        logger.warning(f"Correlation computation failed: {e}")

    try:
        from pairs_engine import identify_stable_pairs
        pairs = await identify_stable_pairs()
        logger.info(f"Identified {len(pairs)} stable pairs")
    except Exception as e:
        logger.warning(f"Pairs identification failed: {e}")

    try:
        from fundamentals import fetch_upcoming_earnings
        earnings = await fetch_upcoming_earnings()
        logger.info(f"Fetched {len(earnings)} upcoming earnings entries")
    except Exception as e:
        logger.warning(f"Earnings fetch failed: {e}")

    try:
        from stock_discovery import prune_inactive_stocks
        pruned = await prune_inactive_stocks()
        if pruned:
            logger.info(f"Pruned {pruned} inactive dynamic stocks")
    except Exception as e:
        logger.warning(f"Pruning failed: {e}")


async def _apply_trailing_stop_loss():
    """Apply trailing stop-loss to sandbox positions.

    - If up >= 1%, trail SL to breakeven (entry price)
    - If up >= 2%, trail SL to lock in 1% profit
    """
    holdings = await db.sandbox_holdings.find({}, {"_id": 0}).to_list(100)
    from sandbox import upstox_client as sb_client

    symbols = [h["stock_symbol"] for h in holdings]
    if not symbols:
        return 0

    quotes = await sb_client.get_batch_quotes(symbols)
    adjustments = 0

    for h in holdings:
        sym = h["stock_symbol"]
        price_data = quotes.get(sym)
        if not price_data:
            continue

        ltp = float(price_data.get("ltp", 0))
        if ltp <= 0:
            continue

        entry = float(h.get("entry_price", 0))
        current_sl = h.get("stop_loss")
        action = h.get("action", "BUY")

        if entry <= 0 or action not in ("BUY", "SHORT"):
            continue

        if action == "BUY":
            # Long: trail SL upward as price rises
            pct_profit = (ltp - entry) / entry * 100

            new_sl = None
            if pct_profit >= TRAILING_SL_LOCKIN_PCT:
                new_sl = round(entry * 1.01, 2)
            elif pct_profit >= TRAILING_SL_BREAKEVEN_PCT:
                new_sl = round(entry, 2)

            if new_sl and (not current_sl or new_sl > current_sl):
                sl_query = {"stock_symbol": sym, "product_type": h.get("product_type", "DELIVERY")}
                await db.sandbox_holdings.update_one(
                    sl_query,
                    {"$set": {"stop_loss": new_sl, "trailing_sl_applied": True}},
                )
                adjustments += 1
                logger.info(f"Trailing SL (LONG): {sym} SL ↑ Rs.{new_sl} (was Rs.{current_sl or 'none'})")

        elif action == "SHORT":
            pct_profit = (entry - ltp) / entry * 100

            new_sl = None
            if pct_profit >= TRAILING_SL_LOCKIN_PCT:
                new_sl = round(entry * 0.99, 2)
            elif pct_profit >= TRAILING_SL_BREAKEVEN_PCT:
                new_sl = round(entry, 2)

            if new_sl and (not current_sl or new_sl < current_sl):
                sl_query = {"stock_symbol": sym, "product_type": h.get("product_type", "INTRADAY")}
                await db.sandbox_holdings.update_one(
                    sl_query,
                    {"$set": {"stop_loss": new_sl, "trailing_sl_applied": True}},
                )
                adjustments += 1
                logger.info(f"Trailing SL (SHORT): {sym} SL ↓ Rs.{new_sl} (was Rs.{current_sl or 'none'})")

    return adjustments


async def _mid_day_pair_check():
    """Check pair trades for convergence/divergence at mid-day."""
    try:
        from pairs_engine import scan_pairs_for_signals, close_pair_trade
        signals = await scan_pairs_for_signals()
        for sig in signals:
            if sig["type"] == "PAIR_EXIT":
                await close_pair_trade(sig["trade_id"], sig)
                logger.info(f"Pair trade closed: {sig.get('reason', '')}")
    except Exception as e:
        logger.warning(f"Mid-day pair check failed: {e}")


async def run_daily_scan() -> Dict[str, Any]:
    """Unified daily pipeline: screen → deep AI → generate for BOTH modes.

    Sandbox: auto-executes trades.
    Live: creates pending TradeRecommendation for manual approval.
    Same analysis, two execution paths.
    """
    config = await _get_scheduler_config()
    scan_log = {
        "id": datetime.now(IST).strftime("%Y%m%d_%H%M%S"),
        "started_at": datetime.now(IST).isoformat(),
        "phase": "pre_market",
        "status": "running",
    }
    await db.scheduler_logs.insert_one(scan_log)

    try:
        # Phase 0: Pre-market data refresh
        await _pre_market_refresh()

        # Phase 1: Screen all stocks (core + active dynamic)
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

        # Phase 2: Deep AI analysis with market context
        logger.info("=== DAILY SCAN: Phase 2 — Deep AI analysis ===")
        max_positions = config.get("max_positions", 5)
        max_trade_val = config.get("max_trade_value", 20000.0)

        top_buys = buy_candidates[:max_positions]
        top_shorts = short_candidates[:3]

        # Fetch market context once for all candidates
        from market_context import get_market_context, format_market_context
        mkt_ctx = await get_market_context()
        mkt_ctx_text = format_market_context(mkt_ctx)

        signals_generated = []
        sandbox_entries = []
        live_recs_created = 0
        type_counts = {"BUY_CNC": 0, "BUY_INTRADAY": 0, "SHORT_INTRADAY": 0}

        # Clear stale pending BUY/SHORT live recommendations from previous scans
        # so the trade queue always shows the freshest signals
        stale_deleted = await db.trade_recommendations.delete_many({
            "trade_mode": "live",
            "status": "pending",
            "action": {"$in": ["BUY", "SHORT"]},
            "ai_reasoning": {"$regex": "^\\[AUTO-SCAN\\]"},
        })
        if stale_deleted.deleted_count:
            logger.info(f"Cleared {stale_deleted.deleted_count} stale pending live BUY/SHORT recs")

        from correlation import get_correlated_peers, format_correlation_for_prompt, get_beta
        from fundamentals import get_fundamentals, format_fundamentals_for_prompt
        from market_context import get_sector_rank

        for candidate in top_buys + top_shorts:
            sym = candidate["symbol"]
            stock = await db.stocks.find_one({"symbol": sym}, {"_id": 0})
            if not stock:
                continue

            try:
                from routes import _get_technical_data, _get_risk_settings
                technical_data, indicators_raw = await _get_technical_data(sym, include_intraday=True)

                # Enrich with correlation, fundamentals, peer data
                peers = await get_correlated_peers(sym)
                beta = await get_beta(sym)
                sector_rank_info = get_sector_rank(mkt_ctx, stock.get("sector", ""))
                corr_text = format_correlation_for_prompt(sym, peers, beta, sector_rank_info)

                fund_data = await get_fundamentals(sym)
                fund_text = format_fundamentals_for_prompt(fund_data)

                peer_lines = []
                for p in peers:
                    change = p.get("change_pct_1d", 0) or 0
                    peer_lines.append(f"  {p['symbol']}: corr={p['correlation']:.2f}, today={change:+.1f}%")
                peer_text = "\n".join(peer_lines) if peer_lines else ""

                # Run 3-step deep research: ANALYZE → VERIFY → SIGNAL
                result = await deep_research(
                    stock_symbol=sym,
                    stock_name=stock.get("name", sym),
                    sector=stock.get("sector", ""),
                    technical_data=technical_data,
                    indicators_raw=indicators_raw,
                    market_context=mkt_ctx_text,
                    fundamental_data=fund_text,
                    correlation_data=corr_text,
                    peer_data=peer_text,
                    max_trade_value=max_trade_val,
                    risk_per_trade_pct=2.0,
                )

                # Persist full analysis to analysis_history for AI Research page
                analysis_doc = {
                    "id": str(uuid_lib.uuid4()),
                    "stock_symbol": sym,
                    "analysis": result.get("full_analysis", "")[:2000],
                    "confidence_score": result.get("signal", {}).get("confidence_score", 0) if result.get("signal") else 0,
                    "analysis_type": "deep_research",
                    "trade_horizon": result.get("signal", {}).get("trade_horizon") if result.get("signal") else None,
                    "key_signals": {
                        "action": result.get("signal", {}).get("action", "HOLD") if result.get("signal") else "HOLD",
                        "steps_completed": len(result.get("steps", [])),
                        "screener_score": candidate.get("score"),
                        "screener_bias": candidate.get("bias"),
                        **(result.get("signal", {}).get("key_signals", {}) if result.get("signal") else {}),
                    },
                    "mode": "entry",
                    "source": "auto_scan",
                    "created_at": datetime.now(IST).isoformat(),
                }
                await db.analysis_history.insert_one(analysis_doc)

                recommendation = result.get("signal")
                if not recommendation:
                    logger.info(f"Deep research for {sym}: no actionable signal")
                    continue

                # Validate signal before execution
                from validator import validate_signal
                validation = await validate_signal(recommendation, trade_mode="sandbox")
                if not validation["passed"]:
                    logger.info(f"Signal rejected for {sym}: {validation['reasons']}")
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

                # Live: validate with stricter live threshold before queuing
                live_validation = await validate_signal(recommendation, trade_mode="live")
                if live_validation["passed"]:
                    live_rec = TradeRecommendation(
                        stock_symbol=sym,
                        stock_name=recommendation.get("stock_name", sym),
                        sector=stock.get("sector", ""),
                        action=action,
                        quantity=recommendation["quantity"],
                        target_price=recommendation.get("target_price", 0),
                        current_price=recommendation["current_price"],
                        stop_loss=recommendation.get("stop_loss"),
                        ai_reasoning=f"[AUTO-SCAN] {recommendation.get('ai_reasoning', '')}",
                        confidence_score=recommendation.get("confidence_score", 0),
                        trade_horizon=trade_horizon,
                        product_type=product_type,
                        key_signals=recommendation.get("key_signals", {}),
                        status="pending",
                        trade_mode="live",
                    )
                    await db.trade_recommendations.insert_one(live_rec.model_dump())
                    live_recs_created += 1
                    logger.info(f"Live rec queued: {action} {product_type} {sym} (pending approval)")
                else:
                    logger.info(f"Live rec skipped for {sym}: {live_validation['reasons']}")

                signals_generated.append({
                    "symbol": sym, "action": action, "product_type": product_type,
                    "price": recommendation["current_price"],
                    "confidence": recommendation.get("confidence_score", 0),
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
            "live_recs_queued": live_recs_created,
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
    """Mechanical SL/target check for CNC holdings — runs every monitor cycle.

    This is the fast path: pure price-based check, no AI calls.
    For AI-driven exit analysis, see _deep_exit_scan().
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


async def _analyze_holding_for_exit(
    h: Dict[str, Any],
    ltp: float,
    mkt_ctx_text: str,
    mode: str,
) -> Optional[Dict[str, Any]]:
    """Run AI exit analysis on a single holding. Shared by sandbox and live paths."""
    from ai_engine import generate_portfolio_sell_signal
    from correlation import get_correlated_peers, format_correlation_for_prompt, get_beta
    from fundamentals import get_fundamentals, format_fundamentals_for_prompt, is_near_earnings

    sym = h["stock_symbol"]

    # Normalize field names (sandbox uses entry_price, live/portfolio uses avg_buy_price)
    entry_price = float(h.get("entry_price", 0) or h.get("avg_buy_price", 0))
    qty = h.get("quantity", 0)
    action = h.get("action", "BUY")
    is_short = action == "SHORT"

    if is_short:
        pnl_pct = ((entry_price - ltp) / entry_price * 100) if entry_price > 0 else 0
    else:
        pnl_pct = ((ltp - entry_price) / entry_price * 100) if entry_price > 0 else 0

    holding_for_ai = {
        "stock_symbol": sym,
        "stock_name": h.get("stock_name", sym),
        "sector": h.get("sector", "Unknown"),
        "quantity": qty,
        "avg_buy_price": entry_price,
        "current_price": ltp,
        "invested_value": entry_price * qty,
        "current_value": ltp * qty,
        "trade_horizon": h.get("trade_horizon", "medium_term"),
        "target_price": h.get("target_price"),
        "stop_loss": h.get("stop_loss"),
        "bought_at": h.get("opened_at", h.get("bought_at", h.get("created_at", ""))),
        "action": action,
        "is_short": is_short,
    }

    from routes import _get_technical_data
    technical_data, _ = await _get_technical_data(sym)

    peers = await get_correlated_peers(sym)
    beta = await get_beta(sym)
    corr_text = format_correlation_for_prompt(sym, peers, beta)

    fund_data = await get_fundamentals(sym)
    fund_text = format_fundamentals_for_prompt(fund_data)

    near_earnings = await is_near_earnings(sym, days=3)

    enriched_data = technical_data
    if mkt_ctx_text:
        enriched_data += f"\n\n{mkt_ctx_text}"
    if corr_text:
        enriched_data += f"\n\n{corr_text}"
    if fund_text:
        enriched_data += f"\n\n{fund_text}"
    if near_earnings:
        enriched_data += f"\n\n⚠️ EARNINGS IMMINENT: {sym} reports within 3 days. Factor this into your exit decision."

    bearish_peers = [p for p in peers if (p.get("change_pct_1d") or 0) < -2 and p.get("correlation", 0) > 0.7]
    if bearish_peers:
        names = ", ".join(f"{p['symbol']} ({p['change_pct_1d']:+.1f}%)" for p in bearish_peers)
        enriched_data += f"\n\n⚠️ CORRELATED PEERS FALLING: {names}. Warning sign for {sym}."

    sell_result = await generate_portfolio_sell_signal(
        holding=holding_for_ai,
        technical_data=enriched_data,
    )

    if sell_result:
        sell_result["_pnl_pct"] = round(pnl_pct, 2)
        sell_result["_ltp"] = ltp
        sell_result["_qty"] = qty
        sell_result["_entry_price"] = entry_price
        sell_result["_mode"] = mode
    return sell_result


async def _deep_exit_scan() -> Dict[str, Any]:
    """Unified AI-driven exit analysis for BOTH sandbox and live holdings.

    Sandbox holdings  → AI says SELL → auto-execute exit
    Live holdings     → AI says SELL → queue TradeRecommendation (pending manual approval)
    Both              → AI says HOLD with revised levels → update SL/target

    Runs at 10:30 and 14:30 daily.
    """
    from market_context import get_market_context, format_market_context
    from sandbox import execute_sandbox_exit, upstox_client as sb_client
    from trading import UpstoxClient

    mkt_ctx = await get_market_context()
    mkt_ctx_text = format_market_context(mkt_ctx)

    sandbox_exits = 0
    live_recs_created = 0
    evaluated = 0
    exit_details = []

    # ── Part 1: Sandbox CNC holdings ──
    sandbox_holdings = await db.sandbox_holdings.find(
        {"product_type": "CNC"}, {"_id": 0}
    ).to_list(100)

    if sandbox_holdings:
        sb_symbols = [h["stock_symbol"] for h in sandbox_holdings]
        sb_quotes = await sb_client.get_batch_quotes(sb_symbols)

        for h in sandbox_holdings:
            sym = h["stock_symbol"]
            price_data = sb_quotes.get(sym)
            ltp = float(price_data.get("ltp", 0)) if price_data else 0
            if ltp <= 0:
                continue

            evaluated += 1
            try:
                result = await _analyze_holding_for_exit(h, ltp, mkt_ctx_text, "sandbox")
                if not result:
                    continue

                exit_action_label = result.get("action", "HOLD")
                # Persist to analysis_history for AI Research page
                analysis_doc = {
                    "id": str(uuid_lib.uuid4()),
                    "stock_symbol": sym,
                    "analysis": result.get("reasoning", ""),
                    "confidence_score": result.get("confidence", 0),
                    "analysis_type": "exit_analysis",
                    "trade_horizon": h.get("trade_horizon", "medium_term"),
                    "key_signals": {
                        "action": exit_action_label,
                        "urgency": result.get("urgency", "monitor"),
                        "pnl_pct": result.get("_pnl_pct", 0),
                        "revised_target": result.get("revised_target"),
                        "revised_stop_loss": result.get("revised_stop_loss"),
                        **(result.get("key_signals", {})),
                    },
                    "mode": "exit",
                    "source": "deep_exit_scan",
                    "created_at": datetime.now(IST).isoformat(),
                }
                await db.analysis_history.insert_one(analysis_doc)

                if result.get("action") == "SELL":
                    reasoning = result.get("reasoning", "")
                    exit_result = await execute_sandbox_exit(
                        sym, ltp,
                        exit_reason=f"ai_deep_exit: {reasoning[:200]}",
                        product_type="CNC",
                    )
                    if exit_result["success"]:
                        sandbox_exits += 1
                        exit_details.append({
                            "symbol": sym, "mode": "sandbox", "action": "SELL",
                            "price": ltp, "pnl_pct": result["_pnl_pct"],
                            "confidence": result.get("confidence", 0),
                            "urgency": result.get("urgency", "normal"),
                            "reason": reasoning[:200],
                        })
                    logger.info(f"Deep exit (sandbox): SELL {sym} P&L={result['_pnl_pct']:+.1f}%")
                else:
                    await _update_levels_if_revised(result, "sandbox_holdings", sym)
                    logger.info(f"Deep exit (sandbox): HOLD {sym} P&L={result['_pnl_pct']:+.1f}%")

                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Deep exit scan failed for sandbox {sym}: {e}")

    # ── Part 2: Live portfolio holdings ──
    live_holdings = await db.portfolio.find(
        {"trade_mode": "live"}, {"_id": 0}
    ).to_list(100)

    # Also try Upstox holdings if available
    try:
        live_client = UpstoxClient()
        upstox_holdings = await live_client.get_holdings()
        if upstox_holdings:
            existing_syms = {h["stock_symbol"] for h in live_holdings}
            all_stocks = await db.stocks.find({}, {"_id": 0, "symbol": 1, "sector": 1, "name": 1}).to_list(500)
            stock_map = {s["symbol"]: s for s in all_stocks}

            for uh in upstox_holdings:
                qty = uh.get("quantity", 0)
                if qty <= 0:
                    continue
                ts = uh.get("trading_symbol", "")
                if ts not in existing_syms:
                    stock_info = stock_map.get(ts, {})
                    live_holdings.append({
                        "stock_symbol": ts,
                        "stock_name": uh.get("company_name", ts),
                        "quantity": qty,
                        "avg_buy_price": float(uh.get("average_price", 0)),
                        "current_price": float(uh.get("last_price", 0)),
                        "sector": stock_info.get("sector", "Unknown"),
                        "trade_horizon": "medium_term",
                        "target_price": None,
                        "stop_loss": None,
                        "bought_at": None,
                    })
    except Exception as e:
        logger.warning(f"Could not fetch Upstox holdings for exit scan: {e}")

    if live_holdings:
        live_symbols = [h["stock_symbol"] for h in live_holdings]
        live_quotes = await sb_client.get_batch_quotes(live_symbols)

        # Clear stale pending SELL recs from previous exit scans
        stale = await db.trade_recommendations.delete_many({
            "trade_mode": "live",
            "status": "pending",
            "action": {"$in": ["SELL", "COVER"]},
            "ai_reasoning": {"$regex": "^\\[AUTO-EXIT-SCAN\\]"},
        })
        if stale.deleted_count:
            logger.info(f"Cleared {stale.deleted_count} stale pending live exit recs")

        for h in live_holdings:
            sym = h["stock_symbol"]
            price_data = live_quotes.get(sym)
            ltp = float(price_data.get("ltp", 0)) if price_data else float(h.get("current_price", 0))
            if ltp <= 0:
                continue

            evaluated += 1
            try:
                result = await _analyze_holding_for_exit(h, ltp, mkt_ctx_text, "live")
                if not result:
                    continue

                # Persist to analysis_history for AI Research page
                exit_action_label = result.get("action", "HOLD")
                analysis_doc = {
                    "id": str(uuid_lib.uuid4()),
                    "stock_symbol": sym,
                    "analysis": result.get("reasoning", ""),
                    "confidence_score": result.get("confidence", 0),
                    "analysis_type": "exit_analysis",
                    "trade_horizon": h.get("trade_horizon", "medium_term"),
                    "key_signals": {
                        "action": exit_action_label,
                        "urgency": result.get("urgency", "monitor"),
                        "pnl_pct": result.get("_pnl_pct", 0),
                        "revised_target": result.get("revised_target"),
                        "revised_stop_loss": result.get("revised_stop_loss"),
                        **(result.get("key_signals", {})),
                    },
                    "mode": "exit",
                    "source": "deep_exit_scan",
                    "created_at": datetime.now(IST).isoformat(),
                }
                await db.analysis_history.insert_one(analysis_doc)

                if result.get("action") == "SELL":
                    reasoning = result.get("reasoning", "")
                    confidence = result.get("confidence", 0)
                    sell_qty = min(result.get("sell_quantity", h["quantity"]), h["quantity"])

                    is_short = h.get("action") == "SHORT" or h.get("is_short", False)
                    exit_action = "COVER" if is_short else "SELL"

                    sell_rec = TradeRecommendation(
                        stock_symbol=sym,
                        stock_name=h.get("stock_name", sym),
                        sector=h.get("sector", ""),
                        action=exit_action,
                        quantity=sell_qty,
                        target_price=ltp,
                        current_price=ltp,
                        stop_loss=result.get("revised_stop_loss"),
                        ai_reasoning=f"[AUTO-EXIT-SCAN] {reasoning}",
                        confidence_score=confidence,
                        trade_horizon=h.get("trade_horizon", "medium_term"),
                        product_type="INTRADAY" if is_short else h.get("product_type", "DELIVERY"),
                        key_signals=result.get("key_signals", {}),
                        status="pending",
                        trade_mode="live",
                    )
                    await db.trade_recommendations.insert_one(sell_rec.model_dump())
                    live_recs_created += 1

                    exit_details.append({
                        "symbol": sym, "mode": "live", "action": f"{exit_action} (pending)",
                        "price": ltp, "pnl_pct": result["_pnl_pct"],
                        "confidence": confidence,
                        "urgency": result.get("urgency", "normal"),
                        "reason": reasoning[:200],
                    })
                    logger.info(
                        f"Deep exit (live): SELL rec queued for {sym} "
                        f"P&L={result['_pnl_pct']:+.1f}% confidence={confidence}"
                    )
                else:
                    if result.get("revised_stop_loss") or result.get("revised_target"):
                        await _update_levels_if_revised(result, "portfolio", sym, "live")
                    logger.info(f"Deep exit (live): HOLD {sym} P&L={result['_pnl_pct']:+.1f}%")

                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Deep exit scan failed for live {sym}: {e}")

    scan_result = {
        "type": "deep_exit_scan",
        "evaluated": evaluated,
        "sandbox_exits": sandbox_exits,
        "live_recs_queued": live_recs_created,
        "exit_details": exit_details,
        "timestamp": datetime.now(IST).isoformat(),
    }
    await db.scheduler_logs.insert_one(scan_result)

    logger.info(
        f"Deep exit scan complete: {evaluated} evaluated, "
        f"{sandbox_exits} sandbox exits, {live_recs_created} live SELL recs queued"
    )
    return scan_result


async def _update_levels_if_revised(
    result: Dict[str, Any], collection: str, symbol: str, trade_mode: str = None
):
    """Update holding SL/target if the AI revised them."""
    updates = {}
    revised_sl = result.get("revised_stop_loss")
    revised_tgt = result.get("revised_target")
    if revised_sl:
        updates["stop_loss"] = float(revised_sl)
    if revised_tgt:
        updates["target_price"] = float(revised_tgt)
    if not updates:
        return

    query = {"stock_symbol": symbol}
    if trade_mode:
        query["trade_mode"] = trade_mode

    coll = getattr(db, collection)
    await coll.update_one(query, {"$set": updates})
    logger.info(f"Revised levels for {symbol} ({collection}): {updates}")


async def _intraday_exit_scan() -> Dict[str, Any]:
    """AI-driven exit analysis for INTRADAY positions using 15-min candle data.

    Unlike CNC deep exit scan (daily candles), this uses intraday candles and
    intraday-specific indicators (VWAP, session RSI, micro-trend) to decide
    whether to exit intraday positions before the forced squareoff at 15:15.

    Runs hourly: 11:00, 12:00, 13:00, 14:00.
    """
    from ai_engine import generate_portfolio_sell_signal
    from market_context import get_market_context, format_market_context
    from candle_cache import get_intraday_candles
    from indicators import compute_intraday_indicators, format_intraday_for_prompt
    from sandbox import execute_sandbox_exit, upstox_client as sb_client

    intraday_holdings = await db.sandbox_holdings.find(
        {"product_type": "INTRADAY"}, {"_id": 0}
    ).to_list(100)

    if not intraday_holdings:
        return {"evaluated": 0, "exits": 0}

    logger.info(f"=== INTRADAY EXIT SCAN: {len(intraday_holdings)} positions ===")

    symbols = [h["stock_symbol"] for h in intraday_holdings]
    quotes = await sb_client.get_batch_quotes(symbols)
    mkt_ctx = await get_market_context()
    mkt_ctx_text = format_market_context(mkt_ctx)

    exits = 0
    evaluated = 0
    exit_details = []

    for h in intraday_holdings:
        sym = h["stock_symbol"]
        price_data = quotes.get(sym)
        ltp = float(price_data.get("ltp", 0)) if price_data else 0
        if ltp <= 0:
            continue

        evaluated += 1
        entry_price = float(h.get("entry_price", 0))
        qty = h.get("quantity", 0)
        action = h.get("action", "BUY")
        is_short = action == "SHORT"

        if is_short:
            pnl_pct = ((entry_price - ltp) / entry_price * 100) if entry_price > 0 else 0
        else:
            pnl_pct = ((ltp - entry_price) / entry_price * 100) if entry_price > 0 else 0

        try:
            # Fetch 15-min candles for intraday analysis
            intraday_candles = await get_intraday_candles(sym, sb_client, interval=15)
            intraday_ind = compute_intraday_indicators(intraday_candles) if intraday_candles else None
            intraday_text = format_intraday_for_prompt(intraday_ind) if intraday_ind else ""

            # Also get daily context
            from routes import _get_technical_data
            daily_data, _ = await _get_technical_data(sym)

            # Combine: intraday first (primary for intraday trades), then daily context
            enriched_data = ""
            if intraday_text:
                enriched_data += intraday_text + "\n\n"
            if daily_data:
                enriched_data += daily_data
            if mkt_ctx_text:
                enriched_data += f"\n\n{mkt_ctx_text}"

            now = _ist_now()
            time_to_close = (15 * 60 + 15) - (now.hour * 60 + now.minute)
            position_type = "SHORT SELL" if is_short else "BUY"
            enriched_data += (
                f"\n\n⏰ INTRADAY {position_type} POSITION: Must be squared off by 15:15 IST. "
                f"Time remaining: {time_to_close} minutes. "
                f"{'Price RISING = LOSING money on this short.' if is_short else 'Price FALLING = LOSING money.'} "
                f"If P&L is negative and momentum is against the trade, exit now — "
                f"don't wait for forced squareoff at worse prices."
            )

            holding_for_ai = {
                "stock_symbol": sym,
                "stock_name": h.get("stock_name", sym),
                "sector": h.get("sector", "Unknown"),
                "quantity": qty,
                "avg_buy_price": entry_price,
                "current_price": ltp,
                "invested_value": entry_price * qty,
                "current_value": ltp * qty,
                "trade_horizon": "short_term",
                "target_price": h.get("target_price"),
                "stop_loss": h.get("stop_loss"),
                "bought_at": h.get("opened_at", h.get("created_at", "")),
                "action": action,
                "is_short": is_short,
            }

            sell_result = await generate_portfolio_sell_signal(
                holding=holding_for_ai,
                technical_data=enriched_data,
            )

            if sell_result:
                # Persist to analysis_history for AI Research page
                intraday_action = sell_result.get("action", "HOLD")
                analysis_doc = {
                    "id": str(uuid_lib.uuid4()),
                    "stock_symbol": sym,
                    "analysis": sell_result.get("reasoning", ""),
                    "confidence_score": sell_result.get("confidence", 0),
                    "analysis_type": "intraday_exit",
                    "trade_horizon": "short_term",
                    "key_signals": {
                        "action": intraday_action,
                        "urgency": sell_result.get("urgency", "monitor"),
                        "pnl_pct": round(pnl_pct, 2),
                        "position_type": "SHORT" if is_short else "LONG",
                        **(sell_result.get("key_signals", {})),
                    },
                    "mode": "exit",
                    "source": "intraday_exit_scan",
                    "created_at": datetime.now(IST).isoformat(),
                }
                await db.analysis_history.insert_one(analysis_doc)

            if sell_result and sell_result.get("action") == "SELL":
                reasoning = sell_result.get("reasoning", "")
                confidence = sell_result.get("confidence", 0)

                exit_result = await execute_sandbox_exit(
                    sym, ltp,
                    exit_reason=f"ai_intraday_exit: {reasoning[:200]}",
                    product_type="INTRADAY",
                )
                if exit_result["success"]:
                    exits += 1
                    exit_details.append({
                        "symbol": sym, "mode": "sandbox", "action": "SELL",
                        "price": ltp, "pnl_pct": round(pnl_pct, 2),
                        "confidence": confidence,
                        "reason": reasoning[:200],
                    })
                logger.info(
                    f"Intraday exit: SELL {sym} P&L={pnl_pct:+.1f}% "
                    f"confidence={confidence}"
                )
            else:
                logger.info(f"Intraday exit: HOLD {sym} P&L={pnl_pct:+.1f}%")
                if sell_result:
                    await _update_levels_if_revised(sell_result, "sandbox_holdings", sym)

            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Intraday exit scan failed for {sym}: {e}")

    # Also queue live SELL recs for live intraday positions
    live_intraday = await db.portfolio.find(
        {"trade_mode": "live", "product_type": "INTRADAY"}, {"_id": 0}
    ).to_list(50)

    live_recs = 0
    for h in live_intraday:
        sym = h["stock_symbol"]
        price_data = quotes.get(sym) if sym in [x["stock_symbol"] for x in intraday_holdings] else None
        if not price_data:
            try:
                extra_q = await sb_client.get_batch_quotes([sym])
                price_data = extra_q.get(sym)
            except Exception:
                continue
        ltp = float(price_data.get("ltp", 0)) if price_data else 0
        if ltp <= 0:
            continue

        evaluated += 1
        try:
            result = await _analyze_holding_for_exit(h, ltp, mkt_ctx_text, "live")
            if not result:
                continue

            # Persist to analysis_history for AI Research page
            analysis_doc = {
                "id": str(uuid_lib.uuid4()),
                "stock_symbol": sym,
                "analysis": result.get("reasoning", ""),
                "confidence_score": result.get("confidence", 0),
                "analysis_type": "intraday_exit",
                "trade_horizon": "short_term",
                "key_signals": {
                    "action": result.get("action", "HOLD"),
                    "urgency": result.get("urgency", "monitor"),
                    "pnl_pct": result.get("_pnl_pct", 0),
                    **(result.get("key_signals", {})),
                },
                "mode": "exit",
                "source": "intraday_exit_scan",
                "created_at": datetime.now(IST).isoformat(),
            }
            await db.analysis_history.insert_one(analysis_doc)

            if result.get("action") == "SELL":
                is_short = h.get("action") == "SHORT" or h.get("is_short", False)
                exit_action = "COVER" if is_short else "SELL"

                sell_rec = TradeRecommendation(
                    stock_symbol=sym,
                    stock_name=h.get("stock_name", sym),
                    sector=h.get("sector", ""),
                    action=exit_action,
                    quantity=h.get("quantity", 0),
                    target_price=ltp,
                    current_price=ltp,
                    stop_loss=result.get("revised_stop_loss"),
                    ai_reasoning=f"[AUTO-INTRADAY-EXIT] {result.get('reasoning', '')}",
                    confidence_score=result.get("confidence", 0),
                    trade_horizon="short_term",
                    product_type="INTRADAY",
                    key_signals=result.get("key_signals", {}),
                    status="pending",
                    trade_mode="live",
                )
                await db.trade_recommendations.insert_one(sell_rec.model_dump())
                live_recs += 1
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Intraday exit scan (live) failed for {sym}: {e}")

    scan_result = {
        "type": "intraday_exit_scan",
        "evaluated": evaluated,
        "sandbox_exits": exits,
        "live_recs_queued": live_recs,
        "exit_details": exit_details,
        "timestamp": datetime.now(IST).isoformat(),
    }
    await db.scheduler_logs.insert_one(scan_result)

    logger.info(f"Intraday exit scan: {evaluated} evaluated, {exits} sandbox exits, {live_recs} live recs")
    return scan_result


async def _monitor_loop():
    """Enhanced background loop with trailing SL, pair monitoring, and intraday squareoff.

    Runs every 60s during market hours.
    """
    global _running
    logger.info("Enhanced monitor loop started")

    last_squareoff_date = None
    last_trailing_sl_time = None
    last_mid_day_check = None
    last_intraday_exit_hour = None

    while _running:
        try:
            if _is_market_hours():
                # Standard SL/target monitoring
                exits = await check_sandbox_exits()
                if exits:
                    logger.info(f"Auto-exited {len(exits)} sandbox positions")
                await update_sandbox_prices()

                now = _ist_now()
                today = now.date()
                current_minute = now.hour * 60 + now.minute

                # Trailing stop-loss check (every 5 minutes)
                trailing_key = f"{today}_{current_minute // 5}"
                if last_trailing_sl_time != trailing_key:
                    last_trailing_sl_time = trailing_key
                    adjustments = await _apply_trailing_stop_loss()
                    if adjustments:
                        logger.info(f"Trailing SL: adjusted {adjustments} positions")

                # Hourly intraday exit scan using 15-min candles (11, 12, 13, 14)
                intraday_hour_key = f"{today}_{now.hour}"
                if (now.hour in (11, 12, 13, 14) and
                        last_intraday_exit_hour != intraday_hour_key):
                    last_intraday_exit_hour = intraday_hour_key
                    try:
                        result = await _intraday_exit_scan()
                        logger.info(
                            f"Intraday exit scan ({now.hour}:00): "
                            f"{result.get('sandbox_exits', 0)} exits"
                        )
                    except Exception as e:
                        logger.error(f"Intraday exit scan failed: {e}")

                # Mid-day pair check (once around 12:00)
                if now.time() >= time(11, 55) and now.time() <= time(12, 10) and last_mid_day_check != today:
                    last_mid_day_check = today
                    await _mid_day_pair_check()

                # Intraday squareoff at 15:15 IST (once per day)
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

    logger.info("Enhanced monitor loop stopped")


async def _scheduler_loop():
    """Enhanced scheduler loop with multiple scan windows throughout the day.

    Windows: pre-market (05:30), main scan (09:20), second-chance (10:00),
             mid-day review (12:00), exit prep (14:30), EOD (15:30).
    """
    global _running
    logger.info("Enhanced scheduler loop started")

    completed_windows: Dict[str, bool] = {}

    def _window_key(window: str) -> str:
        return f"{_ist_now().date()}_{window}"

    while _running:
        try:
            config = await _get_scheduler_config()
            if not config.get("enabled"):
                await asyncio.sleep(30)
                continue

            now = _ist_now()

            if now.weekday() >= 5:
                await asyncio.sleep(60)
                continue

            current_time = now.time()

            # Pre-market data refresh (05:30)
            key = _window_key("pre_market")
            if current_time >= time(5, 30) and key not in completed_windows:
                completed_windows[key] = True
                logger.info("=== WINDOW: Pre-market data refresh ===")
                try:
                    await _pre_market_refresh()
                except Exception as e:
                    logger.error(f"Pre-market refresh failed: {e}")

            # Main scan (09:20)
            scan_time_str = config.get("scan_time", "09:20")
            scan_h, scan_m = map(int, scan_time_str.split(":"))
            key = _window_key("main_scan")
            if current_time >= time(scan_h, scan_m) and key not in completed_windows:
                completed_windows[key] = True
                logger.info("=== WINDOW: Main daily scan ===")
                try:
                    await run_daily_scan()
                except Exception as e:
                    logger.error(f"Main scan failed: {e}")

            # Deep exit scan for CNC holdings (10:30)
            # After the market has traded for an hour, run full AI analysis
            # on all CNC holdings to decide if any position should be exited.
            key = _window_key("deep_exit")
            if current_time >= time(10, 30) and key not in completed_windows:
                completed_windows[key] = True
                logger.info("=== WINDOW: Deep exit scan (AI-driven) ===")
                try:
                    result = await _deep_exit_scan()
                    logger.info(f"Deep exit scan: {result.get('exits', 0)} exits from {result.get('evaluated', 0)} holdings")
                except Exception as e:
                    logger.error(f"Deep exit scan failed: {e}")

            # Mid-day review (12:00) — pairs + second exit check
            key = _window_key("mid_day")
            if current_time >= time(12, 0) and key not in completed_windows:
                completed_windows[key] = True
                logger.info("=== WINDOW: Mid-day review ===")
                try:
                    await _mid_day_pair_check()
                except Exception as e:
                    logger.error(f"Mid-day pair check failed: {e}")

            # Exit preparation (14:30)
            # Mechanical SL/target check + second deep exit scan for any
            # holdings that the AI flagged as HOLD in the morning but
            # the situation may have changed by afternoon.
            exit_time_str = config.get("exit_scan_time", "14:30")
            exit_h, exit_m = map(int, exit_time_str.split(":"))
            key = _window_key("exit_prep")
            if current_time >= time(exit_h, exit_m) and key not in completed_windows:
                completed_windows[key] = True
                logger.info("=== WINDOW: Exit preparation ===")
                try:
                    cnc_exits = await _scan_cnc_exits(config.get("max_trade_value", 20000.0))
                    logger.info(f"Exit prep (mechanical): {cnc_exits} CNC exits")
                except Exception as e:
                    logger.error(f"Exit prep (mechanical) failed: {e}")
                try:
                    result = await _deep_exit_scan()
                    logger.info(f"Exit prep (AI): {result.get('exits', 0)} exits from {result.get('evaluated', 0)} holdings")
                except Exception as e:
                    logger.error(f"Exit prep (AI) failed: {e}")

            # EOD cleanup (15:30)
            key = _window_key("eod")
            if current_time >= time(15, 30) and key not in completed_windows:
                completed_windows[key] = True
                logger.info("=== WINDOW: End of day ===")
                try:
                    from stock_discovery import prune_inactive_stocks
                    await prune_inactive_stocks()
                except Exception as e:
                    logger.error(f"EOD cleanup failed: {e}")

            # Clean up old window keys (keep only today's)
            today_prefix = str(now.date())
            completed_windows = {k: v for k, v in completed_windows.items() if k.startswith(today_prefix)}

            await asyncio.sleep(30)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
            await asyncio.sleep(60)

    logger.info("Enhanced scheduler loop stopped")


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
