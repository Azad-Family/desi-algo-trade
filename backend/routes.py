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
from ai_engine import get_ai_stock_analysis, generate_trade_recommendation, generate_portfolio_sell_signal
from trading import UpstoxClient
from indicators import compute_indicators, format_indicators_for_prompt, format_technical_numbers_for_ai
from stock_init import initialize_stocks
from database import db
from candle_cache import get_candles as get_candles_cached

logger = logging.getLogger(__name__)
upstox_client = UpstoxClient()

# Create router
api_router = APIRouter(prefix="/api")


async def _get_technical_data(symbol: str) -> tuple:
    """Get candles from cache (or Upstox if stale/missing), then compute indicators.
    
    Returns (formatted_string, raw_indicators_dict).
    On failure returns ("", None).
    """
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
        stocks = await db.stocks.find({}, {"_id": 0}).to_list(100)
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
    stocks = await db.stocks.find({"sector": sector}, {"_id": 0}).to_list(100)
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
        stocks = await db.stocks.find({}, {"symbol": 1}).to_list(100)
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
        
        # Also update portfolio holdings with the latest prices
        portfolio_updated = 0
        holdings = await db.portfolio.find({}, {"_id": 0}).to_list(100)
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
                    {"stock_symbol": sym},
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
    """Run AI analysis on a stock with real technical data and search grounding"""
    stock = await db.stocks.find_one({"symbol": request.stock_symbol.upper()}, {"_id": 0})
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    try:
        technical_data, _ = await _get_technical_data(stock["symbol"])
        
        analysis = await get_ai_stock_analysis(
            stock["symbol"],
            stock["name"],
            stock["sector"],
            request.analysis_type,
            technical_data=technical_data
        )
        
        analysis_doc = {
            "id": str(uuid_lib.uuid4()),
            "stock_symbol": stock["symbol"],
            "analysis": analysis["analysis"],
            "confidence_score": analysis["confidence_score"],
            "analysis_type": request.analysis_type,
            "trade_horizon": analysis.get("trade_horizon"),
            "key_signals": analysis.get("key_signals", {}),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.analysis_history.insert_one(analysis_doc)
        
        return AIAnalysisResponse(
            stock_symbol=stock["symbol"],
            analysis=analysis["analysis"],
            confidence_score=analysis["confidence_score"],
            trade_horizon=analysis.get("trade_horizon"),
            key_signals=analysis.get("key_signals", {}),
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
        )
        
        await db.trade_recommendations.insert_one(trade_rec.model_dump())
        return trade_rec
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate recommendation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendation: {str(e)}")


# How many stocks to scan per "Scan All" run (to limit API/time). Picked by symbol order for determinism.
SCAN_ALL_BATCH_SIZE = 10


@api_router.post("/ai/scan-all")
async def scan_all_stocks():
    """Run AI scan on a batch of stocks and generate BUY recommendations.
    
    Does not delete any existing recommendations. Adds new BUY recommendations
    to the queue. Reports when the scan completed (scanned_at).
    
    Stock selection: first SCAN_ALL_BATCH_SIZE stocks when ordered by sector
    then symbol, so the same set is scanned each time until the universe changes.
    """
    stocks = await db.stocks.find({}, {"_id": 0}).to_list(100)
    # Deterministic order: by sector, then symbol (same 10 every time)
    stocks_sorted = sorted(stocks, key=lambda s: (s.get("sector", ""), s.get("symbol", "")))
    to_scan = stocks_sorted[:SCAN_ALL_BATCH_SIZE]
    scanned_symbols = [s["symbol"] for s in to_scan]

    max_val, risk_pct = await _get_risk_settings()
    generated = 0
    scanned = 0

    for stock in to_scan:
        scanned += 1
        try:
            technical_data, indicators_raw = await _get_technical_data(stock["symbol"])

            recommendation = await generate_trade_recommendation(
                stock["symbol"],
                stock["name"],
                stock["sector"],
                technical_data=technical_data,
                indicators_raw=indicators_raw,
                max_trade_value=max_val,
                risk_per_trade_pct=risk_pct,
            )
            if recommendation:
                trade_rec = TradeRecommendation(
                    stock_symbol=recommendation["stock_symbol"],
                    stock_name=recommendation["stock_name"],
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
                )
                await db.trade_recommendations.insert_one(trade_rec.model_dump())
                generated += 1
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error scanning {stock['symbol']}: {e}")

    scanned_at = datetime.now(timezone.utc).isoformat()
    logger.info(f"Scan All completed at {scanned_at}: {generated} new BUY recommendations from {scanned} stocks ({scanned_symbols})")

    return {
        "message": f"Scan complete: {generated} new recommendations from {scanned} stocks. No recommendations were deleted.",
        "generated": generated,
        "scanned": scanned,
        "scanned_symbols": scanned_symbols,
        "scanned_at": scanned_at,
    }


# ============ TRADE RECOMMENDATIONS ROUTES ============
@api_router.get("/recommendations")
async def get_recommendations(status: Optional[str] = None, action: Optional[str] = None):
    """Get trade recommendations. Filter by status (pending/executed/rejected) and/or action (BUY/SELL)."""
    query = {}
    if status:
        query["status"] = status
    if action and action.upper() in ("BUY", "SELL"):
        query["action"] = action.upper()
    recommendations = await db.trade_recommendations.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return recommendations


@api_router.get("/recommendations/pending")
async def get_pending_recommendations(action: Optional[str] = None):
    """Get pending trade recommendations awaiting approval. Optional action=BUY or action=SELL."""
    query = {"status": "pending"}
    if action and action.upper() in ("BUY", "SELL"):
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
            
            order_result = await upstox_client.place_order(
                rec["stock_symbol"],
                rec["action"],
                quantity,
                price
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
            
            await update_portfolio(
                rec["stock_symbol"], rec["stock_name"], rec["action"], quantity, price,
                rec.get("sector", ""),
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
@api_router.get("/portfolio")
async def get_portfolio():
    """Get current portfolio holdings"""
    holdings = await db.portfolio.find({}, {"_id": 0}).to_list(100)
    
    # Calculate totals
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
        }
    }


@api_router.get("/portfolio/sector-breakdown")
async def get_portfolio_sector_breakdown():
    """Get portfolio breakdown by sector"""
    pipeline = [
        {"$group": {
            "_id": "$sector",
            "total_value": {"$sum": "$current_value"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"total_value": -1}}
    ]
    breakdown = await db.portfolio.aggregate(pipeline).to_list(20)
    return [{"sector": b["_id"], "value": b["total_value"], "count": b["count"]} for b in breakdown]


@api_router.post("/portfolio/refresh-prices")
async def refresh_portfolio_prices():
    """Update current prices for all portfolio holdings using latest stock data.
    
    Should be called after /stocks/refresh so the stocks collection has fresh prices.
    """
    holdings = await db.portfolio.find({}, {"_id": 0}).to_list(100)
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
                {"stock_symbol": sym},
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
    holdings = await db.portfolio.find({}, {"_id": 0}).to_list(100)
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
                        action="SELL",
                        quantity=sell_qty,
                        target_price=holding.get("current_price", 0),
                        current_price=holding.get("current_price", 0),
                        stop_loss=signal.get("revised_stop_loss"),
                        ai_reasoning=f"[PORTFOLIO SELL SIGNAL] {signal['reasoning']} | Horizon: {signal.get('horizon_assessment', 'N/A')}",
                        confidence_score=signal.get("confidence", 60),
                        trade_horizon=holding.get("trade_horizon", "medium_term"),
                        key_signals=signal.get("key_signals", {}),
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
    """Get trade execution history"""
    trades = await db.trade_history.find({}, {"_id": 0}).sort("executed_at", -1).to_list(limit)
    return trades


@api_router.get("/trades/stats")
async def get_trade_stats():
    """Get trading statistics"""
    total_trades = await db.trade_history.count_documents({})
    buy_trades = await db.trade_history.count_documents({"action": "BUY"})
    sell_trades = await db.trade_history.count_documents({"action": "SELL"})
    
    # Calculate total traded value
    pipeline = [
        {"$group": {"_id": None, "total_value": {"$sum": "$total_value"}}}
    ]
    result = await db.trade_history.aggregate(pipeline).to_list(1)
    total_value = result[0]["total_value"] if result else 0
    
    return {
        "total_trades": total_trades,
        "buy_trades": buy_trades,
        "sell_trades": sell_trades,
        "total_traded_value": round(total_value, 2)
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

    # Quick connectivity check — try hitting a lightweight API
    if live_token:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{upstox_client.base_url}/market/status/exchange",
                    headers={"Authorization": f"Bearer {live_token}", "Accept": "application/json"},
                    timeout=5.0,
                )
                status["market_data_connectivity"] = "ok" if resp.status_code == 200 else f"HTTP {resp.status_code}"
        except Exception as e:
            status["market_data_connectivity"] = f"error: {e}"
    else:
        status["market_data_connectivity"] = "no token"

    return status


# ============ DASHBOARD ROUTES ============
@api_router.get("/dashboard/stats")
async def get_dashboard_stats():
    """Get dashboard overview stats"""
    # Portfolio summary
    portfolio = await db.portfolio.find({}, {"_id": 0}).to_list(100)
    total_invested = sum(h.get("invested_value", 0) for h in portfolio)
    total_current = sum(h.get("current_value", 0) for h in portfolio)
    
    # Pending recommendations
    pending_count = await db.trade_recommendations.count_documents({"status": "pending"})
    
    # Today's trades
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_trades = await db.trade_history.count_documents({"executed_at": {"$gte": today_start}})
    
    # Stock universe count
    stock_count = await db.stocks.count_documents({})
    
    return {
        "portfolio_value": round(total_current, 2),
        "total_invested": round(total_invested, 2),
        "total_pnl": round(total_current - total_invested, 2),
        "pnl_percent": round((total_current - total_invested) / total_invested * 100, 2) if total_invested > 0 else 0,
        "pending_recommendations": pending_count,
        "today_trades": today_trades,
        "total_stocks": stock_count,
        "holdings_count": len(portfolio)
    }


# ============ PORTFOLIO HELPER ============
async def update_portfolio(
    symbol: str, name: str, action: str, quantity: int, price: float, sector: str,
    trade_mode: str = "simulated", trade_horizon: str = None, target_price: float = None,
    stop_loss: float = None, recommendation_id: str = None,
):
    """Update portfolio after a trade, preserving trade context for sell signal generation."""
    existing = await db.portfolio.find_one({"stock_symbol": symbol}, {"_id": 0})
    
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
            await db.portfolio.update_one(
                {"stock_symbol": symbol},
                {"$set": update_fields}
            )
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
            await db.portfolio.delete_one({"stock_symbol": symbol})
        else:
            new_invested = new_qty * existing["avg_buy_price"]
            await db.portfolio.update_one(
                {"stock_symbol": symbol},
                {"$set": {
                    "quantity": new_qty,
                    "invested_value": new_invested,
                    "current_price": price,
                    "current_value": new_qty * price,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
