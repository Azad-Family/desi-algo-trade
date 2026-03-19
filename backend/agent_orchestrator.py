"""Conversational trading agent orchestrator.

Receives user messages, classifies intent via Gemini, routes to the
appropriate handler, and returns structured response blocks that the
frontend renders as rich chat content.
"""

import json
import logging
import re
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import db
from trading import UpstoxClient
from ai_engine import (
    get_ai_stock_analysis,
    generate_trade_recommendation,
    generate_portfolio_sell_signal,
    _call_gemini,
    _get_gemini_client,
)
from prompts import (
    INTENT_CLASSIFIER_PROMPT,
    BRIEFING_PROMPT,
    build_discover_prompt,
    build_question_prompt,
)
from indicators import (
    compute_indicators,
    format_indicators_for_prompt,
    format_technical_numbers_for_ai,
)
from candle_cache import get_candles as get_candles_cached
from models import TradeRecommendation

logger = logging.getLogger(__name__)
upstox_client = UpstoxClient()


def _current_trade_mode() -> str:
    """Return 'sandbox' or 'live' based on current Upstox configuration."""
    return "sandbox" if upstox_client.sandbox else "live"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(content: str) -> Dict[str, Any]:
    return {"type": "text", "content": content}


def _prompts(items: List[str]) -> Dict[str, Any]:
    return {"type": "suggested_prompts", "data": items}


def _gemini_client():
    return _get_gemini_client()


async def _get_technical_data(symbol: str):
    """Mirrors routes._get_technical_data — returns (formatted_str, raw_dict)."""
    try:
        candles = await get_candles_cached(symbol, db, upstox_client)
        if candles:
            indicators = compute_indicators(candles)
            if indicators:
                full_block = format_indicators_for_prompt(indicators)
                numbers_block = format_technical_numbers_for_ai(indicators)
                technical_data = f"{numbers_block}\n\n{full_block}" if numbers_block else full_block
                return technical_data, indicators
    except Exception as e:
        logger.warning(f"Could not get technical data for {symbol}: {e}")
    return "", None


async def _get_risk_settings():
    settings = await db.settings.find_one({"id": "main_settings"}, {"_id": 0})
    if settings:
        return (
            settings.get("max_trade_value", 100000.0),
            settings.get("risk_per_trade_percent", 2.0),
        )
    return 100000.0, 2.0


async def _stock_universe_summary() -> str:
    """Compact list of all stocks in the universe for Gemini context."""
    stocks = await db.stocks.find({}, {"_id": 0, "symbol": 1, "name": 1, "sector": 1, "current_price": 1}).to_list(500)
    lines = []
    for s in sorted(stocks, key=lambda x: (x.get("sector", ""), x.get("symbol", ""))):
        price_str = f"Rs.{s['current_price']:.2f}" if s.get("current_price") else "price N/A"
        lines.append(f"  {s['symbol']} — {s['name']} [{s.get('sector', '?')}] ({price_str})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Intent Classification
# ---------------------------------------------------------------------------


def _fast_classify(message: str) -> Optional[Dict[str, Any]]:
    """Keyword-based pre-classifier to avoid Gemini call for obvious intents."""
    lower = message.lower().strip()

    if any(w in lower for w in ["good morning", "morning briefing", "what's happening", "market update", "start"]):
        return {"intent": "briefing", "symbols": [], "sectors": [], "themes": [], "detail": message}
    if any(w in lower for w in ["portfolio", "my holdings", "my positions", "how are my stocks"]):
        return {"intent": "portfolio", "symbols": [], "sectors": [], "themes": [], "detail": message}
    if any(w in lower for w in ["approve all", "execute all"]):
        return {"intent": "approve", "symbols": [], "sectors": [], "themes": [], "detail": message}
    if any(w in lower for w in ["reject all", "pass on all", "skip all"]):
        return {"intent": "reject", "symbols": [], "sectors": [], "themes": [], "detail": message}

    # Check for "approve SYMBOL" / "reject SYMBOL"
    approve_match = re.match(r"^(?:approve|execute|go ahead with)\s+(\w+)", lower)
    if approve_match:
        sym = approve_match.group(1).upper()
        return {"intent": "approve", "symbols": [sym], "sectors": [], "themes": [], "detail": message}
    reject_match = re.match(r"^(?:reject|skip|pass on)\s+(\w+)", lower)
    if reject_match:
        sym = reject_match.group(1).upper()
        return {"intent": "reject", "symbols": [sym], "sectors": [], "themes": [], "detail": message}

    # Check for "analyze SYMBOL"
    analyze_match = re.match(r"^(?:analyze|analyse|research|check|look at)\s+(.+)", lower)
    if analyze_match:
        raw = analyze_match.group(1)
        syms = [s.strip().upper() for s in re.split(r"[,\s]+and\s+|[,\s]+", raw) if s.strip()]
        if syms:
            return {"intent": "analyze", "symbols": syms, "sectors": [], "themes": [], "detail": message}

    # "generate signal for SYMBOL"
    signal_match = re.match(r"^(?:generate\s+)?(?:signal|signals|recommendation)s?\s+(?:for\s+)?(.+)", lower)
    if signal_match:
        raw = signal_match.group(1)
        syms = [s.strip().upper() for s in re.split(r"[,\s]+and\s+|[,\s]+", raw) if s.strip()]
        if syms:
            return {"intent": "signal", "symbols": syms, "sectors": [], "themes": [], "detail": message}

    return None


async def classify_intent(message: str, session_context: Dict[str, Any]) -> Dict[str, Any]:
    fast = _fast_classify(message)
    if fast:
        return fast

    client = _gemini_client()
    if not client:
        return {"intent": "question", "symbols": [], "sectors": [], "themes": [], "detail": message}

    ctx_summary = {
        "user_focus": session_context.get("user_focus", ""),
        "sectors": session_context.get("sectors", []),
        "shortlisted": session_context.get("shortlisted_stocks", []),
    }

    try:
        from google.genai.types import GenerateContentConfig

        prompt = f"""{INTENT_CLASSIFIER_PROMPT}

Conversation context: {json.dumps(ctx_summary)}
User message: {message}"""

        resp = _call_gemini(client, prompt, GenerateContentConfig(temperature=0.1))
        match = re.search(r"\{[\s\S]*\}", resp.text)
        if match:
            data = json.loads(match.group())
            data.setdefault("symbols", [])
            data.setdefault("sectors", [])
            data.setdefault("themes", [])
            return data
    except Exception as e:
        logger.error(f"Intent classification error: {e}")

    return {"intent": "question", "symbols": [], "sectors": [], "themes": [], "detail": message}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_briefing(session_ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Morning market briefing using Google Search for live data."""
    client = _gemini_client()
    blocks: List[Dict[str, Any]] = []

    if not client:
        blocks.append(_text("AI not configured — please set GOOGLE_GEMINI_KEY in .env."))
        return blocks

    try:
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

        prompt = BRIEFING_PROMPT
        config = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.4,
        )
        resp = _call_gemini(client, prompt, config)
        blocks.append(_text(resp.text))

    except Exception as e:
        logger.error(f"Briefing error: {e}")
        blocks.append(_text(f"Could not fetch market briefing: {e}"))

    blocks.append(_prompts([
        "I'm bullish on IT sector today",
        "Show me banking stocks",
        "What looks good for a short-term trade?",
        "Check my portfolio",
    ]))
    return blocks


async def handle_set_focus(
    message: str, intent_data: Dict[str, Any], session_ctx: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Store user thesis and confirm understanding, then auto-discover."""
    sectors = intent_data.get("sectors", [])
    themes = intent_data.get("themes", [])
    symbols = intent_data.get("symbols", [])

    session_ctx["user_focus"] = message
    if sectors:
        session_ctx["sectors"] = list(set(session_ctx.get("sectors", []) + sectors))
    if themes:
        session_ctx["themes"] = list(set(session_ctx.get("themes", []) + themes))
    if symbols:
        session_ctx["shortlisted_stocks"] = list(
            set(session_ctx.get("shortlisted_stocks", []) + symbols)
        )

    blocks: List[Dict[str, Any]] = []
    focus_parts = []
    if sectors:
        focus_parts.append(f"**Sectors:** {', '.join(sectors)}")
    if themes:
        focus_parts.append(f"**Themes:** {', '.join(themes)}")
    if symbols:
        focus_parts.append(f"**Stocks mentioned:** {', '.join(symbols)}")

    blocks.append(_text(
        "Got it, here's what I'm working with:\n\n"
        + "\n".join(focus_parts)
        + "\n\nLet me find the most interesting stocks based on your thesis and today's news..."
    ))

    discovery_blocks = await handle_discover(message, intent_data, session_ctx)
    blocks.extend(discovery_blocks)
    return blocks


async def handle_discover(
    message: str, intent_data: Dict[str, Any], session_ctx: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """AI-driven stock discovery from the universe based on user context + news."""
    client = _gemini_client()
    blocks: List[Dict[str, Any]] = []

    if not client:
        blocks.append(_text("AI not configured."))
        return blocks

    universe = await _stock_universe_summary()
    user_focus = session_ctx.get("user_focus", "no specific focus")
    focus_sectors = session_ctx.get("sectors", [])
    focus_themes = session_ctx.get("themes", [])

    try:
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

        prompt = build_discover_prompt(user_focus, focus_sectors, focus_themes, universe)

        config = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.4,
        )
        resp = _call_gemini(client, prompt, config)
        match = re.search(r"\{[\s\S]*\}", resp.text)
        if match:
            data = json.loads(match.group())
            picks = data.get("picks", [])
            market_ctx = data.get("market_context", "")

            if market_ctx:
                blocks.append(_text(f"**Market Context:** {market_ctx}"))

            if picks:
                picked_symbols = [p["symbol"] for p in picks]
                session_ctx["shortlisted_stocks"] = list(
                    set(session_ctx.get("shortlisted_stocks", []) + picked_symbols)
                )

                # Fetch live prices for the picked stocks
                quotes = await upstox_client.get_batch_quotes(picked_symbols)
                stock_cards = []
                for p in picks:
                    sym = p["symbol"]
                    price_data = quotes.get(sym, {})
                    ltp = float(price_data.get("ltp", 0)) if price_data else 0
                    change = float(price_data.get("change_percent", 0)) if price_data else 0
                    stock_cards.append({
                        "symbol": sym,
                        "name": p.get("name", sym),
                        "sector": p.get("sector", ""),
                        "price": ltp,
                        "change_percent": change,
                        "rationale": p.get("rationale", ""),
                    })
                blocks.append({"type": "stock_cards", "data": stock_cards})
                blocks.append(_text("Click on any stock to analyze it, or tell me which ones to dig deeper on."))
            else:
                blocks.append(_text("I couldn't identify strong picks right now. Try giving me more specific sectors or themes."))

            blocks.append(_prompts([
                f"Analyze {picks[0]['symbol']}" if picks else "Analyze TCS",
                "Analyze all of these",
                "Focus on top 3 only",
                "Show me different stocks",
            ]))
        else:
            blocks.append(_text("I had trouble parsing the stock picks. Let me try differently — which sector interests you?"))

    except Exception as e:
        logger.error(f"Discovery error: {e}")
        blocks.append(_text(f"Stock discovery failed: {e}"))

    return blocks


async def _check_portfolio(symbol: str) -> Optional[Dict[str, Any]]:
    """Return the portfolio holding for a symbol in the current mode, or None if not held."""
    return await db.portfolio.find_one(
        {"stock_symbol": symbol.upper(), "trade_mode": _current_trade_mode()}, {"_id": 0}
    )


async def _auto_signal_from_analysis(
    sym: str, stock: Dict[str, Any],
    technical_data: str, indicators_raw: Dict[str, Any],
    analysis: Dict[str, Any], holding: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Generate a trade signal directly from analysis — portfolio-aware.

    If stock is in portfolio → only SELL/HOLD (exit evaluation).
    If stock is NOT in portfolio → only BUY/HOLD (entry evaluation).
    Returns the signal_data dict for the chat block, or None.
    """
    max_val, risk_pct = await _get_risk_settings()
    key_signals = analysis.get("key_signals", {})
    action = key_signals.get("action", "HOLD")

    # Normalize: SELL on unheld stock → SHORT
    effective_action = action
    if not holding and action == "SELL":
        effective_action = "SHORT"

    if holding:
        # --- EXIT evaluation ---
        if action in ("SELL", "SHORT"):
            rec = await generate_portfolio_sell_signal(
                holding=holding,
                technical_data=technical_data,
            )
            if rec and rec.get("action") == "SELL":
                mode = _current_trade_mode()
                trade_rec = TradeRecommendation(
                    stock_symbol=sym,
                    stock_name=stock.get("name", sym),
                    action="SELL",
                    quantity=rec.get("sell_quantity", holding.get("quantity", 0)),
                    target_price=float(key_signals.get("target_price", 0) or 0),
                    current_price=indicators_raw.get("current_price", 0) if indicators_raw else 0,
                    stop_loss=float(key_signals.get("stop_loss", 0) or 0),
                    ai_reasoning=rec.get("reasoning", analysis.get("analysis", "")[:300]),
                    confidence_score=rec.get("confidence", analysis.get("confidence_score", 50)),
                    trade_horizon=analysis.get("trade_horizon", "short_term"),
                    key_signals=rec.get("key_signals", key_signals),
                    product_type="DELIVERY",
                    trade_mode=mode,
                )
                await db.trade_recommendations.insert_one(trade_rec.model_dump())
                return _build_signal_block(trade_rec, stock)
        return None
    else:
        # --- ENTRY evaluation: BUY (delivery) or SHORT (intraday) ---
        if effective_action in ("BUY", "SHORT"):
            rec = await generate_trade_recommendation(
                stock_symbol=sym,
                stock_name=stock.get("name", sym),
                sector=stock.get("sector", "Unknown"),
                technical_data=technical_data,
                indicators_raw=indicators_raw,
                max_trade_value=max_val,
                risk_per_trade_pct=risk_pct,
            )
            if rec and rec["action"] in ("BUY", "SHORT"):
                mode = _current_trade_mode()
                trade_rec = TradeRecommendation(
                    stock_symbol=rec["stock_symbol"],
                    stock_name=rec["stock_name"],
                    action=rec["action"],
                    quantity=rec["quantity"],
                    target_price=rec["target_price"],
                    current_price=rec["current_price"],
                    stop_loss=rec.get("stop_loss"),
                    ai_reasoning=rec["ai_reasoning"],
                    confidence_score=rec["confidence_score"],
                    trade_horizon=rec.get("trade_horizon", "short_term"),
                    horizon_rationale=rec.get("horizon_rationale"),
                    key_signals=rec.get("key_signals", {}),
                    product_type=rec.get("product_type", "DELIVERY"),
                    trade_mode=mode,
                )
                await db.trade_recommendations.insert_one(trade_rec.model_dump())
                return _build_signal_block(trade_rec, stock)
        return None


def _build_signal_block(trade_rec: TradeRecommendation, stock: Dict[str, Any]) -> Dict[str, Any]:
    """Build a trade_signal chat block from a TradeRecommendation."""
    return {
        "type": "trade_signal",
        "data": {
            "rec_id": trade_rec.id,
            "symbol": trade_rec.stock_symbol,
            "name": stock.get("name", trade_rec.stock_symbol),
            "action": trade_rec.action,
            "quantity": trade_rec.quantity,
            "current_price": trade_rec.current_price,
            "target_price": trade_rec.target_price,
            "stop_loss": trade_rec.stop_loss,
            "confidence": trade_rec.confidence_score,
            "trade_horizon": trade_rec.trade_horizon,
            "reasoning": trade_rec.ai_reasoning,
            "key_signals": trade_rec.key_signals,
        },
    }


async def handle_analyze(
    symbols: List[str], session_ctx: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Portfolio-aware analysis that auto-generates entry/exit signals.

    - Not in portfolio → ENTRY analysis → BUY signal if actionable
    - In portfolio → EXIT analysis → SELL signal if actionable
    - Every analysis is persisted to analysis_history
    - Every actionable signal is auto-inserted into trade_recommendations
    """
    blocks: List[Dict[str, Any]] = []

    if not symbols:
        shortlisted = session_ctx.get("shortlisted_stocks", [])
        if shortlisted:
            symbols = shortlisted[:3]
            blocks.append(_text(f"Analyzing your shortlisted stocks: **{', '.join(symbols)}**"))
        else:
            blocks.append(_text("Which stocks should I analyze? Give me symbols like TCS, INFY, etc."))
            return blocks

    for sym in symbols:
        sym = sym.upper()
        stock = await db.stocks.find_one({"symbol": sym}, {"_id": 0})
        if not stock:
            blocks.append(_text(f"**{sym}** is not in the stock universe. Skipping."))
            continue

        holding = await _check_portfolio(sym)
        mode = "EXIT" if holding else "ENTRY"
        blocks.append(_text(
            f"{'Evaluating exit for' if holding else 'Scanning entry for'} "
            f"**{stock.get('name', sym)} ({sym})** — {mode} mode"
        ))

        technical_data, indicators_raw = await _get_technical_data(sym)

        analysis = await get_ai_stock_analysis(
            stock_symbol=sym,
            stock_name=stock.get("name", sym),
            sector=stock.get("sector", "Unknown"),
            analysis_type="hybrid",
            technical_data=technical_data,
        )

        if not analysis or not analysis.get("analysis"):
            blocks.append(_text(f"Analysis for {sym} failed or returned empty."))
            continue

        session_ctx.setdefault("analyzed_stocks", [])
        if sym not in session_ctx["analyzed_stocks"]:
            session_ctx["analyzed_stocks"].append(sym)

        # Persist to analysis_history
        analysis_doc = {
            "id": str(uuid_lib.uuid4()),
            "stock_symbol": sym,
            "analysis": analysis["analysis"],
            "confidence_score": analysis.get("confidence_score", 0),
            "analysis_type": "hybrid",
            "trade_horizon": analysis.get("trade_horizon"),
            "key_signals": analysis.get("key_signals", {}),
            "mode": mode,
            "source": "agent_chat",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.analysis_history.insert_one(analysis_doc)

        # Show the analysis block
        analysis_data = {
            "symbol": sym,
            "name": stock.get("name", sym),
            "sector": stock.get("sector", ""),
            "analysis_text": analysis["analysis"],
            "confidence_score": analysis.get("confidence_score", 0),
            "trade_horizon": analysis.get("trade_horizon", "short_term"),
            "key_signals": analysis.get("key_signals", {}),
        }
        blocks.append({"type": "analysis", "data": analysis_data})

        # Auto-generate trade signal (portfolio-aware)
        signal_block = await _auto_signal_from_analysis(
            sym, stock, technical_data, indicators_raw, analysis, holding
        )
        if signal_block:
            blocks.append(signal_block)
        else:
            verdict = analysis.get("key_signals", {}).get("action", "HOLD")
            if holding and verdict != "SELL":
                blocks.append(_text(f"**{sym}** — HOLD. No exit signal. Your position is intact."))
            elif not holding and verdict != "BUY":
                blocks.append(_text(f"**{sym}** — No entry signal. Waiting for a better setup."))

    blocks.append(_prompts([
        "Approve all pending signals",
        "Analyze more stocks",
        "Check my portfolio",
        "What sectors look strong?",
    ]))
    return blocks


async def handle_signal(
    symbols: List[str], session_ctx: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Generate trade signals — delegates to handle_analyze which now auto-generates signals."""
    return await handle_analyze(symbols, session_ctx)


async def handle_approve(
    message: str, intent_data: Dict[str, Any], session_ctx: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Approve pending recommendations. Supports 'approve all' or specific rec_id."""
    blocks: List[Dict[str, Any]] = []
    rec_id = intent_data.get("rec_id")
    lower = message.lower()

    if "all" in lower:
        pending = await db.trade_recommendations.find({"status": "pending"}, {"_id": 0}).to_list(50)
        if not pending:
            blocks.append(_text("No pending recommendations to approve."))
            return blocks
        approved = 0
        for rec in pending:
            try:
                await _execute_approval(rec["id"], approved=True)
                approved += 1
            except Exception as e:
                logger.error(f"Approve error for {rec['id']}: {e}")
        blocks.append(_text(f"Approved and executed **{approved}** pending recommendations."))
    elif rec_id:
        try:
            result = await _execute_approval(rec_id, approved=True)
            blocks.append(_text(f"Approved **{result.get('stock_symbol', '')}** {result.get('action', '')} — order placed."))
        except Exception as e:
            blocks.append(_text(f"Approval failed: {e}"))
    else:
        # Try to find symbols in the message and match to pending recs
        symbols = intent_data.get("symbols", [])
        if symbols:
            approved = 0
            for sym in symbols:
                rec = await db.trade_recommendations.find_one(
                    {"stock_symbol": sym.upper(), "status": "pending"}, {"_id": 0}
                )
                if rec:
                    try:
                        await _execute_approval(rec["id"], approved=True)
                        approved += 1
                        blocks.append(_text(f"Approved **{sym.upper()}** {rec['action']}."))
                    except Exception as e:
                        blocks.append(_text(f"Failed to approve {sym}: {e}"))
                else:
                    blocks.append(_text(f"No pending recommendation found for {sym.upper()}."))
            if not approved:
                blocks.append(_text("No recommendations were approved."))
        else:
            pending = await db.trade_recommendations.find({"status": "pending"}, {"_id": 0}).to_list(10)
            if pending:
                blocks.append(_text(
                    f"You have **{len(pending)}** pending recommendations. "
                    "Say 'approve all' or specify a stock symbol like 'approve TCS'."
                ))
            else:
                blocks.append(_text("No pending recommendations."))

    blocks.append(_prompts(["Check my portfolio", "Find more stocks", "Morning briefing"]))
    return blocks


async def handle_reject(
    message: str, intent_data: Dict[str, Any], session_ctx: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Reject pending recommendations."""
    blocks: List[Dict[str, Any]] = []
    rec_id = intent_data.get("rec_id")
    lower = message.lower()

    if "all" in lower:
        result = await db.trade_recommendations.update_many(
            {"status": "pending"},
            {"$set": {"status": "rejected", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        blocks.append(_text(f"Rejected **{result.modified_count}** pending recommendations."))
    elif rec_id:
        await db.trade_recommendations.update_one(
            {"id": rec_id},
            {"$set": {"status": "rejected", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        blocks.append(_text("Recommendation rejected."))
    else:
        symbols = intent_data.get("symbols", [])
        for sym in symbols:
            rec = await db.trade_recommendations.find_one(
                {"stock_symbol": sym.upper(), "status": "pending"}, {"_id": 0}
            )
            if rec:
                await db.trade_recommendations.update_one(
                    {"id": rec["id"]},
                    {"$set": {"status": "rejected", "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
                blocks.append(_text(f"Rejected recommendation for **{sym.upper()}**."))
            else:
                blocks.append(_text(f"No pending recommendation for {sym.upper()}."))

    blocks.append(_prompts(["Find new stocks", "Morning briefing", "Check portfolio"]))
    return blocks


async def handle_portfolio(session_ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Show portfolio summary for the current mode and optionally scan for sell signals."""
    blocks: List[Dict[str, Any]] = []
    mode = _current_trade_mode()

    holdings = await db.portfolio.find({"trade_mode": mode}, {"_id": 0}).to_list(100)
    if not holdings:
        blocks.append(_text(f"Your **{mode}** portfolio is empty. Let's find some stocks to buy!"))
        blocks.append(_prompts(["Morning briefing", "Find stocks to buy"]))
        return blocks

    # Refresh prices
    symbols = [h["stock_symbol"] for h in holdings]
    quotes = await upstox_client.get_batch_quotes(symbols)
    total_invested = 0
    total_current = 0
    holding_cards = []

    for h in holdings:
        sym = h["stock_symbol"]
        price_data = quotes.get(sym, {})
        ltp = float(price_data.get("ltp", 0)) if price_data else h.get("current_price", 0)
        qty = h["quantity"]
        invested = h.get("invested_value", 0)
        current_val = qty * ltp if ltp else h.get("current_value", 0)
        pnl = current_val - invested
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0

        total_invested += invested
        total_current += current_val

        holding_cards.append({
            "symbol": sym,
            "name": h.get("stock_name", sym),
            "quantity": qty,
            "avg_buy_price": h.get("avg_buy_price", 0),
            "current_price": ltp,
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl_pct, 2),
            "trade_horizon": h.get("trade_horizon", ""),
            "target_price": h.get("target_price"),
            "stop_loss": h.get("stop_loss"),
        })

    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    overview = (
        f"**Portfolio Summary**\n\n"
        f"- Holdings: **{len(holdings)}** stocks\n"
        f"- Invested: **Rs.{total_invested:,.2f}**\n"
        f"- Current Value: **Rs.{total_current:,.2f}**\n"
        f"- P&L: **Rs.{total_pnl:,.2f}** ({total_pnl_pct:+.2f}%)\n"
    )
    blocks.append(_text(overview))
    blocks.append({"type": "stock_cards", "data": [
        {
            "symbol": c["symbol"],
            "name": c["name"],
            "price": c["current_price"],
            "change_percent": c["pnl_percent"],
            "rationale": (
                f"Qty: {c['quantity']} | Avg: Rs.{c['avg_buy_price']:.2f} | "
                f"P&L: Rs.{c['pnl']:,.2f} ({c['pnl_percent']:+.1f}%)"
            ),
        }
        for c in holding_cards
    ]})

    blocks.append(_prompts([
        "Scan for sell signals",
        "Analyze my worst performer",
        "Find more stocks to buy",
        "Morning briefing",
    ]))
    return blocks


async def handle_portfolio_sell_scan(session_ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan current-mode portfolio for sell signals using the existing sell-signal logic."""
    blocks: List[Dict[str, Any]] = []
    mode = _current_trade_mode()

    holdings = await db.portfolio.find({"trade_mode": mode}, {"_id": 0}).to_list(100)
    if not holdings:
        blocks.append(_text(f"**{mode.title()}** portfolio is empty — nothing to scan."))
        return blocks

    symbols = [h["stock_symbol"] for h in holdings]
    quotes = await upstox_client.get_batch_quotes(symbols)
    for h in holdings:
        sym = h["stock_symbol"]
        if sym in quotes and quotes[sym].get("ltp"):
            h["current_price"] = float(quotes[sym]["ltp"])
            h["current_value"] = h["quantity"] * h["current_price"]

    blocks.append(_text(f"Scanning **{len(holdings)}** holdings for sell signals..."))

    import asyncio
    sell_signals = []
    for holding in holdings:
        try:
            technical_data, _ = await _get_technical_data(holding["stock_symbol"])
            signal = await generate_portfolio_sell_signal(holding, technical_data=technical_data)
            if signal:
                if signal["action"] == "SELL" and signal.get("sell_quantity", 0) > 0:
                    sell_signals.append(signal)
                    sell_qty = min(signal["sell_quantity"], holding["quantity"])
                    trade_rec = TradeRecommendation(
                        stock_symbol=signal["stock_symbol"],
                        stock_name=signal["stock_name"],
                        action="SELL",
                        quantity=sell_qty,
                        target_price=holding.get("current_price", 0),
                        current_price=holding.get("current_price", 0),
                        stop_loss=signal.get("revised_stop_loss"),
                        ai_reasoning=f"[SELL SIGNAL] {signal['reasoning']} | {signal.get('horizon_assessment', '')}",
                        confidence_score=signal.get("confidence", 60),
                        trade_horizon=holding.get("trade_horizon", "medium_term"),
                        key_signals=signal.get("key_signals", {}),
                        trade_mode=_current_trade_mode(),
                    )
                    await db.trade_recommendations.insert_one(trade_rec.model_dump())
                    blocks.append({"type": "trade_signal", "data": {
                        "rec_id": trade_rec.id,
                        "symbol": signal["stock_symbol"],
                        "name": signal["stock_name"],
                        "action": "SELL",
                        "quantity": sell_qty,
                        "current_price": holding.get("current_price", 0),
                        "target_price": holding.get("current_price", 0),
                        "stop_loss": signal.get("revised_stop_loss"),
                        "confidence": signal.get("confidence", 60),
                        "trade_horizon": holding.get("trade_horizon", "medium_term"),
                        "reasoning": signal["reasoning"],
                        "key_signals": signal.get("key_signals", {}),
                    }})
                else:
                    blocks.append(_text(
                        f"**{holding['stock_symbol']}**: HOLD — {signal.get('reasoning', 'No sell trigger.')}"
                    ))
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Sell scan error for {holding['stock_symbol']}: {e}")

    if not sell_signals:
        blocks.append(_text("No sell signals generated. All positions look okay for now."))

    blocks.append(_prompts(["Approve sell signals", "Find more stocks", "Morning briefing"]))
    return blocks


async def handle_question(
    message: str, session_ctx: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """General-purpose conversational response using Gemini + Google Search."""
    client = _gemini_client()
    blocks: List[Dict[str, Any]] = []

    if not client:
        blocks.append(_text("AI not configured."))
        return blocks

    try:
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

        prompt = build_question_prompt(message, session_ctx)

        config = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.5,
        )
        resp = _call_gemini(client, prompt, config)
        blocks.append(_text(resp.text))
    except Exception as e:
        logger.error(f"Question handler error: {e}")
        blocks.append(_text(f"Sorry, I couldn't process that: {e}"))

    blocks.append(_prompts(["Morning briefing", "Find stocks", "Check portfolio"]))
    return blocks


# ---------------------------------------------------------------------------
# Approval helper (reuses routes.py logic)
# ---------------------------------------------------------------------------

async def _execute_approval(rec_id: str, approved: bool = True) -> Dict[str, Any]:
    """Execute approval/rejection for a recommendation and optionally place order."""
    rec = await db.trade_recommendations.find_one({"id": rec_id}, {"_id": 0})
    if not rec:
        raise ValueError(f"Recommendation {rec_id} not found")
    if rec["status"] != "pending":
        raise ValueError(f"Recommendation is not pending (status={rec['status']})")

    now = datetime.now(timezone.utc).isoformat()

    if not approved:
        await db.trade_recommendations.update_one(
            {"id": rec_id}, {"$set": {"status": "rejected", "updated_at": now}}
        )
        return rec

    quantity = rec["quantity"]
    price = rec["target_price"]

    # SHORT trades: send as SELL with product=I (Intraday) to Upstox
    upstox_action = rec["action"]
    product = rec.get("product_type", "DELIVERY")
    upstox_product = "I" if product == "INTRADAY" else "D"
    if rec["action"] == "SHORT":
        upstox_action = "SELL"
        upstox_product = "I"

    order_result = await upstox_client.place_order(
        rec["stock_symbol"], upstox_action, quantity, price,
        product_type=upstox_product,
    )
    trade_mode = order_result.get("trade_mode", "simulated")

    await db.trade_recommendations.update_one(
        {"id": rec_id},
        {"$set": {
            "status": "executed",
            "trade_mode": trade_mode,
            "executed_at": now,
            "executed_price": price,
        }},
    )

    from models import TradeHistory
    trade_history = TradeHistory(
        stock_symbol=rec["stock_symbol"],
        stock_name=rec["stock_name"],
        action=rec["action"],
        quantity=quantity,
        price=price,
        total_value=quantity * price,
        status="executed",
        trade_mode=trade_mode,
        order_id=order_result.get("order_id"),
        ai_recommendation_id=rec_id,
    )
    await db.trade_history.insert_one(trade_history.model_dump())

    # Import update_portfolio from routes
    from routes import update_portfolio
    await update_portfolio(
        rec["stock_symbol"], rec["stock_name"], rec["action"], quantity, price,
        rec.get("sector", ""),
        trade_mode=trade_mode,
        trade_horizon=rec.get("trade_horizon"),
        target_price=rec.get("target_price"),
        stop_loss=rec.get("stop_loss"),
        recommendation_id=rec_id,
    )

    return rec


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

INTENT_HANDLERS = {
    "briefing": "briefing",
    "set_focus": "set_focus",
    "discover": "discover",
    "analyze": "analyze",
    "signal": "signal",
    "approve": "approve",
    "reject": "reject",
    "portfolio": "portfolio",
    "question": "question",
}


async def process_message(
    user_text: str, session: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Process a user message and return a list of response blocks."""
    ctx = session.get("context", {})

    intent_data = await classify_intent(user_text, ctx)
    intent = intent_data.get("intent", "question")
    logger.info(f"Intent: {intent} | Symbols: {intent_data.get('symbols')} | Detail: {intent_data.get('detail')}")

    # Check for sell scan request inside portfolio intent
    lower = user_text.lower()
    if intent == "portfolio" and any(w in lower for w in ["sell", "scan", "exit", "cut"]):
        return await handle_portfolio_sell_scan(ctx)

    if intent == "briefing":
        return await handle_briefing(ctx)
    elif intent == "set_focus":
        return await handle_set_focus(user_text, intent_data, ctx)
    elif intent == "discover":
        return await handle_discover(user_text, intent_data, ctx)
    elif intent == "analyze":
        symbols = intent_data.get("symbols", [])
        return await handle_analyze(symbols, ctx)
    elif intent == "signal":
        symbols = intent_data.get("symbols", [])
        return await handle_signal(symbols, ctx)
    elif intent == "approve":
        return await handle_approve(user_text, intent_data, ctx)
    elif intent == "reject":
        return await handle_reject(user_text, intent_data, ctx)
    elif intent == "portfolio":
        return await handle_portfolio(ctx)
    else:
        return await handle_question(user_text, ctx)
