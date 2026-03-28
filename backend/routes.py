"""API routes for the trading application"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional
import uuid as uuid_lib

from fastapi import APIRouter, HTTPException
import asyncio

from models import (
    Stock, TradeRecommendation, TradeApproval, Portfolio, TradeHistory, 
    Settings, AIAnalysisRequest, AIAnalysisResponse
)
from ai_engine import (
    get_ai_stock_analysis, generate_trade_recommendation, generate_portfolio_sell_signal,
    get_active_model, get_available_models, get_preferred_model, set_preferred_model,
)
from trading import UpstoxClient, SYMBOL_OVERRIDES
from indicators import compute_indicators, format_indicators_for_prompt, format_technical_numbers_for_ai
from stock_init import initialize_stocks
from database import db
from candle_cache import get_candles as get_candles_cached

logger = logging.getLogger(__name__)
upstox_client = UpstoxClient()

# Create router
api_router = APIRouter(prefix="/api")


def _current_trade_mode() -> str:
    """Return 'sandbox' or 'live' based on current Upstox configuration."""
    return "sandbox" if upstox_client.sandbox else "live"


async def _get_technical_data(symbol: str) -> tuple:
    """Get candles from cache (or Upstox if stale/missing), compute indicators,
    and patch in the live market price so the AI sees real-time LTP.

    Returns (formatted_string, raw_indicators_dict).
    On failure returns ("", None).
    """
    try:
        candles = await get_candles_cached(symbol, db, upstox_client)
        if candles:
            indicators = compute_indicators(candles)
            if indicators:
                # Patch live price: candle "current_price" is yesterday's close;
                # fetch real-time LTP so the AI uses the actual market price.
                try:
                    quotes = await upstox_client.get_batch_quotes([symbol])
                    live = quotes.get(symbol)
                    if live and live.get("ltp") and float(live["ltp"]) > 0:
                        ltp = round(float(live["ltp"]), 2)
                        candle_close = indicators["current_price"]
                        indicators["current_price"] = ltp
                        indicators["live_ltp"] = ltp
                        indicators["prev_day_close"] = candle_close
                        indicators["live_change_pct"] = round(
                            (ltp - candle_close) / candle_close * 100, 2
                        ) if candle_close else 0
                        logger.debug(
                            f"{symbol}: patched price {candle_close} → {ltp} "
                            f"({indicators['live_change_pct']:+.2f}%)"
                        )
                except Exception as e:
                    logger.debug(f"Could not fetch live price for {symbol}: {e}")

                full_block = format_indicators_for_prompt(indicators)
                numbers_block = format_technical_numbers_for_ai(indicators)
                technical_data = f"{numbers_block}\n\n{full_block}" if numbers_block else full_block
                return technical_data, indicators
    except Exception as e:
        logger.warning(f"Could not get technical data for {symbol}: {e}")
    return "", None


async def _get_risk_settings() -> tuple:
    """Load max_trade_value and risk_per_trade_percent from settings."""
    settings = await db.settings.find_one({"id": "main_settings"}, {"_id": 0})
    if settings:
        return (
            settings.get("max_trade_value", 100000.0),
            settings.get("risk_per_trade_percent", 2.0),
        )
    return 100000.0, 2.0


# ============ ROOT & HEALTH ============
@api_router.get("/")
async def root():
    """API root endpoint"""
    return {"message": "AI Trading Agent API - Indian Stocks", "version": "1.0.0"}


@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        await db.command("ping")
        stock_count = await db.stocks.count_documents({})
        return {
            "status": "healthy",
            "database": "connected",
            "stocks_count": stock_count
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")


# ============ STOCK UNIVERSE ROUTES ============
@api_router.get("/stocks", response_model=list[Stock])
async def get_stocks():
    """Get all stocks in the universe"""
    try:
        stocks = await db.stocks.find({}, {"_id": 0}).to_list(500)
        if not stocks:
            raise HTTPException(status_code=404, detail="No stocks found. Please initialize the stock universe.")
        return stocks
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch stocks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch stocks: {str(e)}")


@api_router.get("/stocks/sector/{sector}")
async def get_stocks_by_sector(sector: str):
    """Get stocks filtered by sector"""
    stocks = await db.stocks.find({"sector": sector}, {"_id": 0}).to_list(500)
    return stocks


@api_router.get("/stocks/sectors")
async def get_sectors():
    """Get all unique sectors with stock counts"""
    pipeline = [
        {"$group": {"_id": "$sector", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    sectors = await db.stocks.aggregate(pipeline).to_list(20)
    return [{"sector": s["_id"], "count": s["count"]} for s in sectors]


@api_router.post("/stocks/initialize")
async def initialize_stock_universe():
    """Reinitialize the stock universe (clears and reloads all stocks)"""
    try:
        count = await initialize_stocks()
        return {"message": f"Reinitialized {count} stocks", "count": count}
    except Exception as e:
        logger.error(f"Failed to reinitialize stocks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reinitialize stocks: {str(e)}")


@api_router.get("/stocks/{symbol}")
async def get_stock(symbol: str):
    """Get a specific stock by symbol"""
    stock = await db.stocks.find_one({"symbol": symbol.upper()}, {"_id": 0})
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    return stock


# ============ MARKET STATUS ROUTES ============
@api_router.get("/market/status")
async def get_market_status():
    """Check if NSE market is currently open or closed"""
    status = upstox_client.is_market_open()
    return status


@api_router.get("/debug/upstox-config")
async def debug_upstox_config():
    """Debug: show which tokens and mode the UpstoxClient is using (masked)."""
    def mask(token: str) -> str:
        if not token:
            return "<EMPTY>"
        return f"...{token[-8:]}"
    return {
        "sandbox_flag": upstox_client.sandbox,
        "env_UPSTOX_USE_SANDBOX": os.environ.get("UPSTOX_USE_SANDBOX", "<unset>"),
        "live_access_token": mask(upstox_client.live_access_token),
        "order_access_token": mask(upstox_client.order_access_token),
        "tokens_are_same": upstox_client.live_access_token == upstox_client.order_access_token,
        "order_base_url": upstox_client.order_base_url,
    }


@api_router.get("/debug/ai-config")
async def debug_ai_config():
    """Show current AI model configuration and active model."""
    from ai_engine import _get_model_priority, _model_mgr, MODEL_COOLDOWN_SECONDS
    import time
    now = time.time()
    models = _get_model_priority()
    cooldowns = {}
    for m in models:
        cd = _model_mgr._cooldowns.get(m)
        if cd:
            remaining = max(0, MODEL_COOLDOWN_SECONDS - (now - cd))
            cooldowns[m] = f"{remaining:.0f}s remaining" if remaining > 0 else "expired"
    return {
        "active_model": get_active_model(),
        "model_priority": models,
        "cooldowns": cooldowns,
        "gemini_key_set": bool(os.environ.get("GOOGLE_GEMINI_KEY")),
    }


@api_router.get("/market/debug-quote/{symbol}")
async def debug_quote(symbol: str):
    """Debug endpoint: show raw Upstox API response for a single stock"""
    import httpx as _httpx
    instrument_key = await upstox_client.resolve_instrument_key(symbol.upper())
    headers = {
        "Authorization": f"Bearer {upstox_client.live_access_token}",
        "Accept": "application/json",
    }
    async with _httpx.AsyncClient() as client:
        resp = await client.get(
            f"{upstox_client.market_quote_url}/market-quote/quotes",
            params={"instrument_key": instrument_key},
            headers=headers,
            timeout=10.0,
        )
    return {
        "symbol": symbol.upper(),
        "resolved_instrument_key": instrument_key,
        "http_status": resp.status_code,
        "raw_response": resp.json() if resp.status_code == 200 else resp.text[:500],
    }


@api_router.post("/stocks/refresh")
async def refresh_stock_prices():
    """Fetch latest prices from Upstox and update all stocks (non-destructive)
    
    Unlike /stocks/initialize which deletes and re-inserts,
    this only updates current_price and change_percent fields.
    """
    try:
        logger.info("📍 /api/stocks/refresh endpoint called")
        # Get all stock symbols
        stocks = await db.stocks.find({}, {"symbol": 1}).to_list(500)
        symbols = [s["symbol"] for s in stocks]
        logger.info(f"📦 Found {len(symbols)} stocks in database")
        
        if not symbols:
            raise HTTPException(status_code=400, detail="No stocks in database")
        
        # Fetch batch quotes from Upstox
        quotes = await upstox_client.get_batch_quotes(symbols)
        
        if not quotes:
            logger.warning("No price data received from Upstox - prices may be unavailable")
        
        # Update each stock with latest price
        updated_count = 0
        for stock in stocks:
            symbol = stock["symbol"]
            
            # Extract price from Upstox response
            price_data = quotes.get(symbol, {})
            
            if price_data:
                # Parse Upstox quote response
                ltp = price_data.get("ltp", 0)  # Last traded price
                net_change = price_data.get("net_change", 0)
                change_percent = price_data.get("change_percent", 0)
                
                update_result = await db.stocks.update_one(
                    {"symbol": symbol},
                    {
                        "$set": {
                            "current_price": float(ltp) if ltp else 0.0,
                            "change_percent": float(change_percent) if change_percent else 0.0,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                    }
                )
                
                if update_result.modified_count > 0:
                    updated_count += 1
        
        # Also update portfolio holdings with the latest prices (current mode only)
        portfolio_updated = 0
        current_mode = _current_trade_mode()
        holdings = await db.portfolio.find({"trade_mode": current_mode}, {"_id": 0}).to_list(100)
        for h in holdings:
            sym = h["stock_symbol"]
            price_data = quotes.get(sym, {})
            ltp = float(price_data.get("ltp", 0)) if price_data else 0

            if not ltp:
                stock_doc = await db.stocks.find_one({"symbol": sym}, {"_id": 0})
                if stock_doc:
                    ltp = stock_doc.get("current_price", 0)

            if ltp > 0:
                qty = h["quantity"]
                invested = h.get("invested_value", 0)
                current_val = qty * ltp
                pnl = current_val - invested
                pnl_pct = (pnl / invested * 100) if invested > 0 else 0.0
                await db.portfolio.update_one(
                    {"stock_symbol": sym, "trade_mode": current_mode},
                    {"$set": {
                        "current_price": ltp,
                        "current_value": round(current_val, 2),
                        "pnl": round(pnl, 2),
                        "pnl_percent": round(pnl_pct, 2),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )
                portfolio_updated += 1

        logger.info(f"Updated prices for {updated_count}/{len(symbols)} stocks, {portfolio_updated} portfolio holdings")
        return {
            "message": f"Updated {updated_count} stock prices, {portfolio_updated} portfolio holdings",
            "updated": updated_count,
            "portfolio_updated": portfolio_updated,
            "total": len(symbols),
            "source": "Upstox API" if quotes else "fallback"
        }
    
    except Exception as e:
        logger.error(f"Failed to refresh prices: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh prices: {str(e)}")


# ============ AI ANALYSIS ROUTES ============
@api_router.post("/ai/analyze", response_model=AIAnalysisResponse)
async def analyze_stock(request: AIAnalysisRequest):
    """Portfolio-aware AI analysis that auto-generates trade signals.

    - Stock NOT in portfolio → ENTRY mode (BUY signal only)
    - Stock IN portfolio → EXIT mode (SELL signal only)
    """
    symbol = request.stock_symbol.upper()
    stock = await db.stocks.find_one({"symbol": symbol}, {"_id": 0})
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    trade_mode = _current_trade_mode()

    # Check if user holds this stock — Upstox in live mode, local DB in sandbox
    holding = None
    if trade_mode == "live":
        try:
            raw_holdings = await upstox_client.get_holdings()
            await upstox_client._ensure_instrument_map()
            isin_to_ts = {ik: ts for ts, ik in upstox_client._instrument_map.items()}
            ts_to_our = {isin_to_ts.get(v, k): k for k, v in SYMBOL_OVERRIDES.items()}
            for h in raw_holdings:
                upstox_sym = h.get("trading_symbol") or h.get("tradingsymbol", "")
                our_sym = ts_to_our.get(upstox_sym, upstox_sym)
                if our_sym == symbol and h.get("quantity", 0) > 0:
                    holding = {
                        "stock_symbol": symbol,
                        "stock_name": h.get("company_name", symbol),
                        "quantity": h["quantity"],
                        "avg_buy_price": float(h.get("average_price", 0)),
                        "current_price": float(h.get("last_price", 0)),
                        "invested_value": float(h.get("average_price", 0)) * h["quantity"],
                        "current_value": float(h.get("last_price", 0)) * h["quantity"],
                        "trade_mode": "live",
                    }
                    break
        except Exception as e:
            logger.warning(f"Could not check Upstox holdings for {symbol}: {e}")
            holding = await db.portfolio.find_one({"stock_symbol": symbol, "trade_mode": trade_mode}, {"_id": 0})
    else:
        holding = await db.portfolio.find_one({"stock_symbol": symbol, "trade_mode": trade_mode}, {"_id": 0})

    mode = "exit" if holding else "entry"

    try:
        technical_data, indicators_raw = await _get_technical_data(symbol)

        analysis = await get_ai_stock_analysis(
            symbol,
            stock["name"],
            stock["sector"],
            request.analysis_type,
            technical_data=technical_data,
        )

        # Persist analysis
        analysis_doc = {
            "id": str(uuid_lib.uuid4()),
            "stock_symbol": symbol,
            "analysis": analysis["analysis"],
            "confidence_score": analysis["confidence_score"],
            "analysis_type": request.analysis_type,
            "trade_horizon": analysis.get("trade_horizon"),
            "key_signals": analysis.get("key_signals", {}),
            "mode": mode,
            "source": "research_page",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.analysis_history.insert_one(analysis_doc)

        # Auto-generate trade signal
        signal_generated = None
        key_signals = analysis.get("key_signals", {})
        action = key_signals.get("action", "HOLD")

        # Normalize: AI analysis may say SELL for bearish — map to SHORT for unheld stocks
        effective_action = action
        if not holding and action == "SELL":
            effective_action = "SHORT"

        if holding and action in ("SELL", "SHORT"):
            # EXIT: sell existing holdings (delivery)
            sell_rec = await generate_portfolio_sell_signal(
                holding=holding, technical_data=technical_data,
            )
            if sell_rec and sell_rec.get("action") == "SELL":
                trade_rec = TradeRecommendation(
                    stock_symbol=symbol,
                    stock_name=stock["name"],
                    sector=stock.get("sector", ""),
                    action="SELL",
                    quantity=sell_rec.get("sell_quantity", holding.get("quantity", 0)),
                    target_price=float(key_signals.get("target_price", 0) or 0),
                    current_price=indicators_raw.get("current_price", 0) if indicators_raw else 0,
                    stop_loss=float(key_signals.get("stop_loss", 0) or 0),
                    ai_reasoning=sell_rec.get("reasoning", "")[:500],
                    confidence_score=sell_rec.get("confidence", analysis["confidence_score"]),
                    trade_horizon=analysis.get("trade_horizon", "short_term"),
                    key_signals=sell_rec.get("key_signals", key_signals),
                    product_type="DELIVERY",
                    trade_mode=trade_mode,
                )
                await db.trade_recommendations.insert_one(trade_rec.model_dump())
                signal_generated = {"action": "SELL", "id": trade_rec.id}
        elif not holding and effective_action in ("BUY", "SHORT"):
            # ENTRY: BUY (delivery) or SHORT (intraday)
            max_val, risk_pct = await _get_risk_settings()
            rec = await generate_trade_recommendation(
                symbol, stock["name"], stock["sector"],
                technical_data=technical_data,
                indicators_raw=indicators_raw,
                max_trade_value=max_val,
                risk_per_trade_pct=risk_pct,
            )
            if rec and rec["action"] in ("BUY", "SHORT"):
                trade_rec = TradeRecommendation(
                    stock_symbol=rec["stock_symbol"],
                    stock_name=rec["stock_name"],
                    sector=stock.get("sector", ""),
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
                    trade_mode=trade_mode,
                )
                await db.trade_recommendations.insert_one(trade_rec.model_dump())
                signal_generated = {"action": rec["action"], "id": trade_rec.id}

        return AIAnalysisResponse(
            stock_symbol=symbol,
            analysis=analysis["analysis"],
            confidence_score=analysis["confidence_score"],
            trade_horizon=analysis.get("trade_horizon"),
            key_signals={
                **analysis.get("key_signals", {}),
                "mode": mode,
                "signal_generated": signal_generated,
            },
        )
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@api_router.get("/ai/analysis/latest/{symbol}")
async def get_latest_analysis(symbol: str):
    """Get the most recent AI analysis for a stock"""
    doc = await db.analysis_history.find_one(
        {"stock_symbol": symbol.upper()},
        {"_id": 0},
        sort=[("created_at", -1)]
    )
    if not doc:
        return None
    return doc


@api_router.get("/ai/analysis/latest")
async def get_latest_analysis_any():
    """Get the most recent AI analysis across all stocks"""
    doc = await db.analysis_history.find_one(
        {},
        {"_id": 0},
        sort=[("created_at", -1)]
    )
    if not doc:
        return None
    return doc


@api_router.get("/ai/analysis/history")
async def get_analysis_history(limit: int = 20):
    """Return the most recent analyses across all stocks."""
    docs = await db.analysis_history.find(
        {},
        {"_id": 0, "analysis": 0},
    ).sort("created_at", -1).to_list(limit)
    return docs


@api_router.post("/ai/generate-recommendation/{symbol}")
async def generate_recommendation(symbol: str):
    """Generate an AI trade recommendation for a stock with real data"""
    stock = await db.stocks.find_one({"symbol": symbol.upper()}, {"_id": 0})
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    try:
        technical_data, indicators_raw = await _get_technical_data(stock["symbol"])
        max_val, risk_pct = await _get_risk_settings()
        
        recommendation = await generate_trade_recommendation(
            stock["symbol"],
            stock["name"],
            stock["sector"],
            technical_data=technical_data,
            indicators_raw=indicators_raw,
            max_trade_value=max_val,
            risk_per_trade_pct=risk_pct,
        )
        
        if not recommendation:
            raise HTTPException(status_code=500, detail="AI returned HOLD or recommendation failed validation")
        
        trade_rec = TradeRecommendation(
            stock_symbol=recommendation["stock_symbol"],
            stock_name=recommendation["stock_name"],
            sector=stock.get("sector", ""),
            action=recommendation["action"],
            quantity=recommendation["quantity"],
            target_price=recommendation["target_price"],
            current_price=recommendation["current_price"],
            stop_loss=recommendation.get("stop_loss"),
            ai_reasoning=recommendation["ai_reasoning"],
            confidence_score=recommendation["confidence_score"],
            trade_horizon=recommendation.get("trade_horizon", "medium_term"),
            horizon_rationale=recommendation.get("horizon_rationale"),
            key_signals=recommendation.get("key_signals", {}),
            trade_mode=_current_trade_mode(),
        )
        
        await db.trade_recommendations.insert_one(trade_rec.model_dump())
        return trade_rec
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate recommendation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendation: {str(e)}")


SCAN_ALL_MAX_CANDIDATES = 15


@api_router.post("/ai/scan-all")
async def scan_all_stocks():
    """Scan the full stock universe using a two-phase approach:

    Phase 1 — Fast screener: score ALL stocks using technical indicators
              (parallel, no AI calls — takes ~30s for 125 stocks).
    Phase 2 — Deep AI analysis: run Gemini on the top N candidates only
              (sequential with 2s sleep — takes ~5 min for 15 stocks).

    Deletes all previous pending recommendations for the current mode,
    then generates fresh trade signals for the top candidates.
    """
    from screener import screen_all_stocks as run_screener

    mode = _current_trade_mode()

    delete_result = await db.trade_recommendations.delete_many({"status": "pending", "trade_mode": mode})
    deleted_count = delete_result.deleted_count
    logger.info(f"Scan All [{mode}]: deleted {deleted_count} pending recommendations")

    # Phase 1: fast technical screening of all stocks
    logger.info("=== SCAN ALL: Phase 1 — Screener ===")
    screener_result = await run_screener()
    buy_candidates = screener_result.get("buy_candidates", [])
    short_candidates = screener_result.get("short_candidates", [])
    total_screened = screener_result.get("total_screened", 0)
    logger.info(
        f"Screener done: {total_screened} screened, "
        f"{len(buy_candidates)} buy + {len(short_candidates)} short candidates"
    )

    # Phase 2: deep AI analysis on top candidates only
    logger.info("=== SCAN ALL: Phase 2 — Deep AI analysis ===")
    top_buys = buy_candidates[:SCAN_ALL_MAX_CANDIDATES]
    top_shorts = short_candidates[:5]

    stocks_map = {
        s["symbol"]: s
        for s in await db.stocks.find({}, {"_id": 0}).to_list(500)
    }

    max_val, risk_pct = await _get_risk_settings()
    generated = 0
    analyzed = 0
    scan_time = datetime.now(timezone.utc).isoformat()

    for candidate in top_buys + top_shorts:
        sym = candidate["symbol"]
        stock = stocks_map.get(sym)
        if not stock:
            continue

        analyzed += 1
        try:
            technical_data, indicators_raw = await _get_technical_data(sym)

            recommendation = await generate_trade_recommendation(
                sym,
                stock["name"],
                stock.get("sector", ""),
                technical_data=technical_data,
                indicators_raw=indicators_raw,
                max_trade_value=max_val,
                risk_per_trade_pct=risk_pct,
            )

            action = recommendation["action"] if recommendation else "HOLD"
            analysis_doc = {
                "id": str(uuid_lib.uuid4()),
                "stock_symbol": sym,
                "analysis": recommendation.get("ai_reasoning", "No actionable signal") if recommendation else "No actionable signal",
                "confidence_score": recommendation.get("confidence_score", 0) if recommendation else 0,
                "analysis_type": "hybrid",
                "trade_horizon": recommendation.get("trade_horizon") if recommendation else None,
                "key_signals": {
                    "action": action,
                    "screener_score": candidate.get("score"),
                    "screener_bias": candidate.get("bias"),
                    **(recommendation.get("key_signals", {}) if recommendation else {}),
                },
                "mode": "entry",
                "source": "scan_all",
                "created_at": scan_time,
            }
            await db.analysis_history.insert_one(analysis_doc)

            if recommendation and recommendation["action"] in ("BUY", "SHORT"):
                trade_rec = TradeRecommendation(
                    stock_symbol=recommendation["stock_symbol"],
                    stock_name=recommendation["stock_name"],
                    sector=stock.get("sector", ""),
                    action=recommendation["action"],
                    quantity=recommendation["quantity"],
                    target_price=recommendation["target_price"],
                    current_price=recommendation["current_price"],
                    stop_loss=recommendation.get("stop_loss"),
                    ai_reasoning=recommendation["ai_reasoning"],
                    confidence_score=recommendation["confidence_score"],
                    trade_horizon=recommendation.get("trade_horizon", "medium_term"),
                    horizon_rationale=recommendation.get("horizon_rationale"),
                    key_signals=recommendation.get("key_signals", {}),
                    product_type=recommendation.get("product_type", "DELIVERY"),
                    trade_mode=mode,
                )
                await db.trade_recommendations.insert_one(trade_rec.model_dump())
                generated += 1

            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error scanning {sym}: {e}")

    scanned_at = datetime.now(timezone.utc).isoformat()
    logger.info(f"Scan All completed at {scanned_at}: {generated} signals from {analyzed} deep-analyzed ({total_screened} screened)")

    return {
        "message": f"Scan complete: {total_screened} screened, {analyzed} deep-analyzed, {generated} new signals. {deleted_count} old pending cleared.",
        "generated": generated,
        "screened": total_screened,
        "analyzed": analyzed,
        "deleted": deleted_count,
        "buy_candidates": len(buy_candidates),
        "short_candidates": len(short_candidates),
        "scanned_at": scanned_at,
    }


# ============ TRADE RECOMMENDATIONS ROUTES ============
@api_router.get("/recommendations")
async def get_recommendations(status: Optional[str] = None, action: Optional[str] = None):
    """Get trade recommendations for the current mode (sandbox/live)."""
    mode = _current_trade_mode()
    query = {"trade_mode": mode}
    if status:
        query["status"] = status
    if action and action.upper() in ("BUY", "SELL", "SHORT"):
        query["action"] = action.upper()
    recommendations = await db.trade_recommendations.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return recommendations


@api_router.get("/recommendations/pending")
async def get_pending_recommendations(action: Optional[str] = None):
    """Get pending trade recommendations for the current mode. Optional action=BUY, SELL, or SHORT."""
    mode = _current_trade_mode()
    query = {"status": "pending", "trade_mode": mode}
    if action and action.upper() in ("BUY", "SELL", "SHORT"):
        query["action"] = action.upper()
    recommendations = await db.trade_recommendations.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return recommendations


@api_router.post("/recommendations/{rec_id}/approve")
async def approve_recommendation(rec_id: str, approval: TradeApproval):
    """Approve or reject a trade recommendation"""
    try:
        rec = await db.trade_recommendations.find_one({"id": rec_id}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        
        if rec["status"] != "pending":
            raise HTTPException(status_code=400, detail="Recommendation is not pending")
        
        new_status = "approved" if approval.approved else "rejected"
        update_data = {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if approval.modified_quantity:
            update_data["quantity"] = approval.modified_quantity
        if approval.modified_price:
            update_data["target_price"] = approval.modified_price
        
        await db.trade_recommendations.update_one(
            {"id": rec_id},
            {"$set": update_data}
        )
        
        # If approved, execute the trade
        if approval.approved:
            quantity = approval.modified_quantity or rec["quantity"]
            price = approval.modified_price or rec["target_price"]

            # Pre-trade fund check in live mode
            mode = _current_trade_mode()
            if mode == "live" and rec["action"] in ("BUY", "SHORT"):
                trade_value = quantity * price
                funds = await upstox_client.get_funds_and_margin()
                if funds:
                    available = float(funds.get("available_margin", 0))
                    if available < trade_value:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Insufficient funds: need Rs.{trade_value:,.2f} but only Rs.{available:,.2f} available"
                        )
                else:
                    logger.warning("Could not verify funds — proceeding with order anyway")

            # SHORT trades: send as SELL with product=I (Intraday) to Upstox
            upstox_action = rec["action"]
            product = rec.get("product_type", "DELIVERY")
            upstox_product = "I" if product == "INTRADAY" else "D"
            if rec["action"] == "SHORT":
                upstox_action = "SELL"
                upstox_product = "I"

            order_result = await upstox_client.place_order(
                rec["stock_symbol"],
                upstox_action,
                quantity,
                price,
                product_type=upstox_product,
            )
            
            trade_mode = order_result.get("trade_mode", "simulated")
            
            await db.trade_recommendations.update_one(
                {"id": rec_id},
                {"$set": {
                    "status": "executed",
                    "trade_mode": trade_mode,
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                    "executed_price": price
                }}
            )
            
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
                ai_recommendation_id=rec_id
            )
            await db.trade_history.insert_one(trade_history.model_dump())
            
            sector = rec.get("sector", "")
            if not sector:
                stock_doc = await db.stocks.find_one({"symbol": rec["stock_symbol"]}, {"sector": 1})
                sector = stock_doc.get("sector", "Unknown") if stock_doc else "Unknown"

            await update_portfolio(
                rec["stock_symbol"], rec["stock_name"], rec["action"], quantity, price,
                sector,
                trade_mode=trade_mode,
                trade_horizon=rec.get("trade_horizon"),
                target_price=rec.get("target_price"),
                stop_loss=rec.get("stop_loss"),
                recommendation_id=rec_id,
            )
        
        updated_rec = await db.trade_recommendations.find_one({"id": rec_id}, {"_id": 0})
        return updated_rec
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve recommendation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to approve recommendation: {str(e)}")


# ============ PORTFOLIO ROUTES ============

async def _get_upstox_portfolio() -> dict:
    """Fetch live portfolio from Upstox (holdings + positions) and normalize."""
    raw_holdings = await upstox_client.get_holdings()
    raw_positions = await upstox_client.get_positions()

    # Build symbol → sector lookup from our stocks DB
    all_stocks = await db.stocks.find({}, {"_id": 0, "symbol": 1, "sector": 1}).to_list(500)
    sector_map = {s["symbol"]: s.get("sector", "Unknown") for s in all_stocks}

    # Also build reverse map: Upstox trading_symbol → our symbol
    await upstox_client._ensure_instrument_map()
    isin_to_ts = {ik: ts for ts, ik in upstox_client._instrument_map.items()}
    ts_to_our = {}
    for our_sym, isin_key in SYMBOL_OVERRIDES.items():
        actual_ts = isin_to_ts.get(isin_key, our_sym)
        ts_to_our[actual_ts] = our_sym
    for ts in upstox_client._instrument_map:
        if ts not in ts_to_our:
            ts_to_our[ts] = ts

    holdings = []
    for h in raw_holdings:
        qty = h.get("quantity", 0)
        if qty <= 0:
            continue
        upstox_sym = h.get("trading_symbol") or h.get("tradingsymbol", "")
        our_sym = ts_to_our.get(upstox_sym, upstox_sym)
        avg = float(h.get("average_price", 0))
        ltp = float(h.get("last_price", 0))
        invested = avg * qty
        current = ltp * qty
        holdings.append({
            "stock_symbol": our_sym,
            "stock_name": h.get("company_name", our_sym),
            "quantity": qty,
            "avg_buy_price": round(avg, 2),
            "current_price": round(ltp, 2),
            "invested_value": round(invested, 2),
            "current_value": round(current, 2),
            "pnl": round(float(h.get("pnl", current - invested)), 2),
            "pnl_percent": round((current - invested) / invested * 100, 2) if invested > 0 else 0,
            "day_change": h.get("day_change", 0),
            "day_change_percentage": h.get("day_change_percentage", 0),
            "sector": sector_map.get(our_sym, "Unknown"),
            "product_type": "CNC",
            "trade_mode": "live",
            "source": "upstox",
        })

    for p in raw_positions:
        qty = p.get("quantity", 0) or p.get("net_quantity", 0)
        if qty == 0:
            continue
        upstox_sym = p.get("trading_symbol") or p.get("tradingsymbol", "")
        our_sym = ts_to_our.get(upstox_sym, upstox_sym)
        buy_price = float(p.get("buy_price", 0) or p.get("average_price", 0))
        ltp = float(p.get("last_price", 0))
        invested = buy_price * abs(qty)
        current = ltp * abs(qty)
        holdings.append({
            "stock_symbol": our_sym,
            "stock_name": our_sym,
            "quantity": qty,
            "avg_buy_price": round(buy_price, 2),
            "current_price": round(ltp, 2),
            "invested_value": round(invested, 2),
            "current_value": round(current, 2),
            "pnl": round(float(p.get("pnl", current - invested)), 2),
            "pnl_percent": round((current - invested) / invested * 100, 2) if invested > 0 else 0,
            "sector": sector_map.get(our_sym, "Unknown"),
            "product_type": "INTRADAY" if p.get("product") == "I" else "CNC",
            "trade_mode": "live",
            "source": "upstox",
        })

    total_invested = sum(h["invested_value"] for h in holdings)
    total_current = sum(h["current_value"] for h in holdings)
    total_pnl = total_current - total_invested
    return {
        "holdings": holdings,
        "summary": {
            "total_invested": round(total_invested, 2),
            "total_current": round(total_current, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_percent": round((total_pnl / total_invested * 100) if total_invested > 0 else 0, 2),
            "holdings_count": len(holdings),
        },
        "trade_mode": "live",
    }


@api_router.get("/portfolio")
async def get_portfolio():
    """Get portfolio holdings.

    Live mode  → fetches actual holdings + positions from Upstox.
    Sandbox    → reads from local MongoDB portfolio collection.
    """
    mode = _current_trade_mode()

    if mode == "live":
        try:
            return await _get_upstox_portfolio()
        except Exception as e:
            logger.error(f"Failed to fetch Upstox portfolio, falling back to local DB: {e}")

    # Sandbox mode (or live fallback)
    holdings = await db.portfolio.find({"trade_mode": mode}, {"_id": 0}).to_list(100)
    for h in holdings:
        if not h.get("sector"):
            stock_doc = await db.stocks.find_one({"symbol": h["stock_symbol"]}, {"sector": 1})
            if stock_doc and stock_doc.get("sector"):
                h["sector"] = stock_doc["sector"]
                await db.portfolio.update_one(
                    {"stock_symbol": h["stock_symbol"], "trade_mode": mode},
                    {"$set": {"sector": stock_doc["sector"]}},
                )

    total_invested = sum(h.get("invested_value", 0) for h in holdings)
    total_current = sum(h.get("current_value", 0) for h in holdings)
    total_pnl = total_current - total_invested
    total_pnl_percent = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    return {
        "holdings": holdings,
        "summary": {
            "total_invested": round(total_invested, 2),
            "total_current": round(total_current, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_percent": round(total_pnl_percent, 2),
            "holdings_count": len(holdings)
        },
        "trade_mode": mode,
    }


@api_router.get("/portfolio/sector-breakdown")
async def get_portfolio_sector_breakdown():
    """Get portfolio breakdown by sector for current mode."""
    mode = _current_trade_mode()

    if mode == "live":
        try:
            data = await _get_upstox_portfolio()
            sector_agg = {}
            for h in data["holdings"]:
                sec = h.get("sector", "Unknown")
                if sec not in sector_agg:
                    sector_agg[sec] = {"value": 0, "count": 0}
                sector_agg[sec]["value"] += h["current_value"]
                sector_agg[sec]["count"] += 1
            breakdown = [
                {"sector": s, "value": round(v["value"], 2), "count": v["count"]}
                for s, v in sector_agg.items()
            ]
            breakdown.sort(key=lambda x: x["value"], reverse=True)
            return breakdown
        except Exception as e:
            logger.error(f"Upstox sector breakdown failed: {e}")

    pipeline = [
        {"$match": {"trade_mode": mode}},
        {"$group": {
            "_id": "$sector",
            "total_value": {"$sum": "$current_value"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"total_value": -1}}
    ]
    breakdown = await db.portfolio.aggregate(pipeline).to_list(20)
    return [{"sector": b["_id"], "value": b["total_value"], "count": b["count"]} for b in breakdown]


@api_router.get("/funds")
async def get_funds():
    """Get available funds/margin.

    Live mode  → real Upstox balance.
    Sandbox    → virtual capital from sandbox account.
    """
    mode = _current_trade_mode()
    if mode == "live":
        funds = await upstox_client.get_funds_and_margin()
        if funds:
            return {
                "available_margin": funds.get("available_margin", 0),
                "used_margin": funds.get("used_margin", 0),
                "payin_amount": funds.get("payin_amount", 0),
                "trade_mode": "live",
                "source": "upstox",
            }
        return {"available_margin": 0, "used_margin": 0, "trade_mode": "live", "error": "Could not fetch funds from Upstox"}

    # Sandbox
    from sandbox import get_or_create_account
    account = await get_or_create_account()
    return {
        "available_margin": account.get("current_capital", 0),
        "used_margin": account.get("initial_capital", 100000) - account.get("current_capital", 0),
        "payin_amount": account.get("initial_capital", 100000),
        "trade_mode": "sandbox",
        "source": "sandbox",
    }


@api_router.post("/portfolio/refresh-prices")
async def refresh_portfolio_prices():
    """Update current prices for portfolio holdings in the current mode.

    In live mode this is a no-op — prices come directly from Upstox.
    In sandbox mode, refreshes local DB from market quotes.
    """
    mode = _current_trade_mode()

    if mode == "live":
        return {"message": "Live portfolio prices come directly from Upstox", "updated": 0}

    holdings = await db.portfolio.find({"trade_mode": mode}, {"_id": 0}).to_list(100)
    if not holdings:
        return {"message": "Portfolio is empty", "updated": 0}

    symbols = [h["stock_symbol"] for h in holdings]
    quotes = await upstox_client.get_batch_quotes(symbols)

    updated = 0
    for h in holdings:
        sym = h["stock_symbol"]
        price_data = quotes.get(sym)
        if not price_data:
            stock_doc = await db.stocks.find_one({"symbol": sym}, {"_id": 0})
            if stock_doc and stock_doc.get("current_price", 0) > 0:
                price_data = {"ltp": stock_doc["current_price"]}

        if price_data and price_data.get("ltp"):
            ltp = float(price_data["ltp"])
            qty = h["quantity"]
            invested = h.get("invested_value", 0)
            current_val = qty * ltp
            pnl = current_val - invested
            pnl_pct = (pnl / invested * 100) if invested > 0 else 0.0

            await db.portfolio.update_one(
                {"stock_symbol": sym, "trade_mode": mode},
                {"$set": {
                    "current_price": ltp,
                    "current_value": round(current_val, 2),
                    "pnl": round(pnl, 2),
                    "pnl_percent": round(pnl_pct, 2),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            updated += 1

    return {"message": f"Updated prices for {updated}/{len(holdings)} holdings", "updated": updated}


@api_router.post("/portfolio/{symbol}/sell")
async def sell_holding(symbol: str, quantity: Optional[int] = None):
    """Directly sell a portfolio holding (full or partial) in the current mode.
    Places an order via Upstox, updates portfolio and trade history."""
    mode = _current_trade_mode()
    holding = await db.portfolio.find_one({"stock_symbol": symbol.upper(), "trade_mode": mode}, {"_id": 0})
    if not holding:
        raise HTTPException(status_code=404, detail=f"No holding found for {symbol}")

    sell_qty = quantity or holding["quantity"]
    if sell_qty > holding["quantity"]:
        raise HTTPException(status_code=400, detail=f"Cannot sell {sell_qty}, only {holding['quantity']} held")

    price = holding.get("current_price", 0)
    if not price:
        quotes = await upstox_client.get_batch_quotes([symbol.upper()])
        price = float(quotes.get(symbol.upper(), {}).get("ltp", 0))

    order_result = await upstox_client.place_order(symbol.upper(), "SELL", sell_qty, price)
    trade_mode = order_result.get("trade_mode", "simulated")

    trade = TradeHistory(
        stock_symbol=symbol.upper(),
        stock_name=holding.get("stock_name", symbol.upper()),
        action="SELL",
        quantity=sell_qty,
        price=price,
        total_value=round(sell_qty * price, 2),
        status="executed",
        order_id=order_result.get("order_id", "MANUAL"),
        trade_mode=trade_mode,
    )
    await db.trade_history.insert_one(trade.model_dump())
    await update_portfolio(
        symbol=symbol.upper(),
        name=holding.get("stock_name", symbol.upper()),
        action="SELL",
        quantity=sell_qty,
        price=price,
        sector=holding.get("sector", ""),
        trade_mode=trade_mode,
    )

    return {
        "message": f"Sold {sell_qty} shares of {symbol.upper()}",
        "order_id": order_result.get("order_id"),
        "trade_mode": trade_mode,
        "price": price,
        "total_value": round(sell_qty * price, 2),
    }


@api_router.post("/portfolio/scan-sells")
async def scan_portfolio_for_sells():
    """Scan all portfolio holdings and generate AI sell signals.
    
    Clears old pending/rejected SELL recommendations before generating fresh ones.
    
    For each holding, the AI evaluates:
    - Whether the original trade horizon has expired
    - Whether target or stop-loss has been hit
    - Current technical indicators
    - Latest news and fundamentals
    
    Returns sell signals and also creates trade recommendations for SELL actions.
    Does not delete any existing recommendations.
    """
    mode = _current_trade_mode()
    holdings = await db.portfolio.find({"trade_mode": mode}, {"_id": 0}).to_list(100)
    if not holdings:
        return {"message": "Portfolio is empty", "signals": [], "sell_count": 0}

    # Refresh portfolio prices first
    symbols = [h["stock_symbol"] for h in holdings]
    quotes = await upstox_client.get_batch_quotes(symbols)
    for h in holdings:
        sym = h["stock_symbol"]
        if sym in quotes and quotes[sym].get("ltp"):
            h["current_price"] = float(quotes[sym]["ltp"])
            h["current_value"] = h["quantity"] * h["current_price"]

    signals = []
    sell_count = 0

    for holding in holdings:
        try:
            technical_data, _ = await _get_technical_data(holding["stock_symbol"])

            signal = await generate_portfolio_sell_signal(
                holding,
                technical_data=technical_data,
            )

            if signal:
                signals.append(signal)

                if signal["action"] == "SELL" and signal.get("sell_quantity", 0) > 0:
                    sell_count += 1
                    sell_qty = min(signal["sell_quantity"], holding["quantity"])
                    trade_rec = TradeRecommendation(
                        stock_symbol=signal["stock_symbol"],
                        stock_name=signal["stock_name"],
                        sector=holding.get("sector", ""),
                        action="SELL",
                        quantity=sell_qty,
                        target_price=holding.get("current_price", 0),
                        current_price=holding.get("current_price", 0),
                        stop_loss=signal.get("revised_stop_loss"),
                        ai_reasoning=f"[PORTFOLIO SELL SIGNAL] {signal['reasoning']} | Horizon: {signal.get('horizon_assessment', 'N/A')}",
                        confidence_score=signal.get("confidence", 60),
                        trade_horizon=holding.get("trade_horizon", "medium_term"),
                        key_signals=signal.get("key_signals", {}),
                        trade_mode=mode,
                    )
                    await db.trade_recommendations.insert_one(trade_rec.model_dump())

            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error scanning {holding['stock_symbol']}: {e}")
            signals.append({
                "stock_symbol": holding["stock_symbol"],
                "action": "ERROR",
                "reasoning": str(e),
            })

    scanned_at = datetime.now(timezone.utc).isoformat()
    logger.info(f"Portfolio Sell Scan completed at {scanned_at}: {sell_count} SELL signals from {len(holdings)} holdings")

    return {
        "message": f"Scanned {len(holdings)} holdings, {sell_count} sell signals generated. No recommendations were deleted.",
        "signals": signals,
        "sell_count": sell_count,
        "total_holdings": len(holdings),
        "scanned_at": scanned_at,
    }


# ============ TRADE HISTORY ROUTES ============
@api_router.get("/trades/history")
async def get_trade_history(limit: int = 50):
    """Get trade execution history for the current mode."""
    mode = _current_trade_mode()
    trades = await db.trade_history.find({"trade_mode": mode}, {"_id": 0}).sort("executed_at", -1).to_list(limit)
    return trades


@api_router.get("/trades/stats")
async def get_trade_stats():
    """Get trading statistics for the current mode."""
    mode = _current_trade_mode()
    mode_filter = {"trade_mode": mode}
    total_trades = await db.trade_history.count_documents(mode_filter)
    buy_trades = await db.trade_history.count_documents({**mode_filter, "action": "BUY"})
    sell_trades = await db.trade_history.count_documents({**mode_filter, "action": "SELL"})
    
    pipeline = [
        {"$match": mode_filter},
        {"$group": {"_id": None, "total_value": {"$sum": "$total_value"}}}
    ]
    result = await db.trade_history.aggregate(pipeline).to_list(1)
    total_value = result[0]["total_value"] if result else 0
    
    return {
        "total_trades": total_trades,
        "buy_trades": buy_trades,
        "sell_trades": sell_trades,
        "total_traded_value": round(total_value, 2),
        "trade_mode": mode,
    }


# ============ SETTINGS ROUTES ============
@api_router.get("/settings")
async def get_settings():
    """Get application settings (risk management and trading parameters only).
    Upstox tokens are managed via .env and never stored in DB."""
    settings = await db.settings.find_one({"id": "main_settings"}, {"_id": 0})
    if not settings:
        default_settings = Settings()
        await db.settings.insert_one(default_settings.model_dump())
        settings = default_settings.model_dump()

    # Strip any legacy token fields that may still be in old DB docs
    for legacy_key in ("upstox_api_key", "upstox_api_secret", "upstox_access_token"):
        settings.pop(legacy_key, None)

    return settings


@api_router.post("/settings")
async def update_settings(settings: Settings):
    """Update risk management and trading parameters."""
    settings_dict = settings.model_dump()
    settings_dict["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.settings.update_one(
        {"id": "main_settings"},
        {
            "$set": settings_dict,
            "$unset": {"upstox_api_key": "", "upstox_api_secret": "", "upstox_access_token": ""},
        },
        upsert=True
    )

    return {"message": "Settings updated successfully"}


@api_router.get("/settings/models")
async def get_models():
    """Return available Gemini models and which one is currently preferred."""
    return {
        "available": get_available_models(),
        "preferred": get_preferred_model(),
        "active": get_active_model(),
    }


@api_router.post("/settings/model")
async def set_model(body: dict):
    """Set the preferred Gemini model. Pass {"model": "gemini-2.5-flash"} or {"model": null} for auto."""
    model = body.get("model")
    available = get_available_models()
    if model and model not in available:
        raise HTTPException(status_code=400, detail=f"Unknown model. Available: {available}")

    set_preferred_model(model)
    await db.settings.update_one(
        {"id": "main_settings"},
        {"$set": {"gemini_model": model, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"message": f"Model set to {model or 'auto'}", "active": get_active_model()}


@api_router.get("/settings/upstox-status")
async def get_upstox_status():
    """Read-only status of Upstox integration.
    Shows which mode is active, whether tokens are present, and connectivity."""
    def mask(token: str) -> str:
        if not token:
            return None
        return f"****{token[-6:]}"

    sandbox = upstox_client.sandbox
    live_token = upstox_client.live_access_token
    order_token = upstox_client.order_access_token

    status = {
        "order_mode": "sandbox" if sandbox else "live",
        "market_data_token": mask(live_token) if live_token else None,
        "order_token": mask(order_token) if order_token else None,
        "market_data_ok": bool(live_token),
        "orders_ok": bool(order_token),
        "tokens_source": ".env file (never stored in database)",
        "env_file_hint": "Update UPSTOX_ACCESS_TOKEN and UPSTOX_SANDBOX_ACCESS_TOKEN in backend/.env, then restart the server.",
    }

    import httpx

    # Market data connectivity — uses live token against live API (v2)
    # This will 401 if the live token is expired, which is expected in sandbox-only setups
    if live_token:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.upstox.com/v2/market/status/NSE",
                    headers={"Authorization": f"Bearer {live_token}", "Accept": "application/json"},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    status["market_data_connectivity"] = "ok"
                elif resp.status_code == 401:
                    status["market_data_connectivity"] = "token expired — regenerate UPSTOX_ACCESS_TOKEN"
                else:
                    status["market_data_connectivity"] = f"HTTP {resp.status_code}"
        except Exception as e:
            status["market_data_connectivity"] = f"error: {e}"
    else:
        status["market_data_connectivity"] = "no token"

    # Order API connectivity — v3 only has POST endpoints (place/cancel),
    # so we check with the v2 order book GET endpoint on the matching base.
    if order_token:
        order_check_url = (
            "https://api-sandbox.upstox.com/v2/order/retrieve-all" if sandbox
            else "https://api.upstox.com/v2/order/retrieve-all"
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    order_check_url,
                    headers={"Authorization": f"Bearer {order_token}", "Accept": "application/json"},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    status["order_connectivity"] = "ok"
                elif resp.status_code == 401:
                    token_label = "UPSTOX_SANDBOX_ACCESS_TOKEN" if sandbox else "UPSTOX_ACCESS_TOKEN"
                    status["order_connectivity"] = f"token expired — regenerate {token_label}"
                else:
                    status["order_connectivity"] = f"HTTP {resp.status_code}"
        except Exception as e:
            status["order_connectivity"] = f"error: {e}"
    else:
        status["order_connectivity"] = "no token"

    return status


# ============ DASHBOARD ROUTES ============
@api_router.get("/dashboard/stats")
async def get_dashboard_stats():
    """Get dashboard overview stats for the current mode."""
    mode = _current_trade_mode()
    mode_filter = {"trade_mode": mode}

    # Portfolio values — Upstox in live mode, local DB in sandbox
    if mode == "live":
        try:
            portfolio_data = await _get_upstox_portfolio()
            summary = portfolio_data["summary"]
            total_invested = summary["total_invested"]
            total_current = summary["total_current"]
            holdings_count = summary["holdings_count"]
        except Exception:
            total_invested = total_current = 0
            holdings_count = 0
    else:
        portfolio = await db.portfolio.find(mode_filter, {"_id": 0}).to_list(100)
        total_invested = sum(h.get("invested_value", 0) for h in portfolio)
        total_current = sum(h.get("current_value", 0) for h in portfolio)
        holdings_count = len(portfolio)

    # Funds — live from Upstox, sandbox from sandbox account
    available_margin = 0
    if mode == "live":
        funds = await upstox_client.get_funds_and_margin()
        if funds:
            available_margin = float(funds.get("available_margin", 0))
    else:
        from sandbox import get_or_create_account
        account = await get_or_create_account()
        available_margin = account.get("current_capital", 0)

    pending_count = await db.trade_recommendations.count_documents({"status": "pending", **mode_filter})

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_trades = await db.trade_history.count_documents({"executed_at": {"$gte": today_start}, **mode_filter})

    stock_count = await db.stocks.count_documents({})

    return {
        "portfolio_value": round(total_current, 2),
        "total_invested": round(total_invested, 2),
        "total_pnl": round(total_current - total_invested, 2),
        "pnl_percent": round((total_current - total_invested) / total_invested * 100, 2) if total_invested > 0 else 0,
        "available_margin": round(available_margin, 2),
        "pending_recommendations": pending_count,
        "today_trades": today_trades,
        "total_stocks": stock_count,
        "holdings_count": holdings_count,
        "trade_mode": mode,
    }


# ============ PORTFOLIO HELPER ============
async def update_portfolio(
    symbol: str, name: str, action: str, quantity: int, price: float, sector: str,
    trade_mode: str = "simulated", trade_horizon: str = None, target_price: float = None,
    stop_loss: float = None, recommendation_id: str = None,
):
    """Update portfolio after a trade, preserving trade context for sell signal generation.
    Queries are scoped by trade_mode so the same stock can exist in both live and sandbox portfolios.
    """
    query = {"stock_symbol": symbol, "trade_mode": trade_mode}
    existing = await db.portfolio.find_one(query, {"_id": 0})
    
    if action == "BUY":
        if existing:
            new_qty = existing["quantity"] + quantity
            new_invested = existing["invested_value"] + (quantity * price)
            new_avg = new_invested / new_qty if new_qty > 0 else 0
            update_fields = {
                "quantity": new_qty,
                "avg_buy_price": new_avg,
                "invested_value": new_invested,
                "current_price": price,
                "current_value": new_qty * price,
                "trade_mode": trade_mode,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if trade_horizon:
                update_fields["trade_horizon"] = trade_horizon
            if target_price:
                update_fields["target_price"] = target_price
            if stop_loss:
                update_fields["stop_loss"] = stop_loss
            if recommendation_id:
                update_fields["ai_recommendation_id"] = recommendation_id
            await db.portfolio.update_one(query, {"$set": update_fields})
        else:
            portfolio = Portfolio(
                stock_symbol=symbol,
                stock_name=name,
                quantity=quantity,
                avg_buy_price=price,
                current_price=price,
                invested_value=quantity * price,
                current_value=quantity * price,
                pnl=0.0,
                pnl_percent=0.0,
                sector=sector,
                trade_mode=trade_mode,
                trade_horizon=trade_horizon,
                target_price=target_price,
                stop_loss=stop_loss,
                bought_at=datetime.now(timezone.utc).isoformat(),
                ai_recommendation_id=recommendation_id,
            )
            await db.portfolio.insert_one(portfolio.model_dump())
    
    elif action == "SELL" and existing:
        new_qty = existing["quantity"] - quantity
        if new_qty <= 0:
            await db.portfolio.delete_one(query)
        else:
            new_invested = new_qty * existing["avg_buy_price"]
            await db.portfolio.update_one(
                query,
                {"$set": {
                    "quantity": new_qty,
                    "invested_value": new_invested,
                    "current_price": price,
                    "current_value": new_qty * price,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
