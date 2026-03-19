"""API routes for sandbox trading, screener, and scheduler."""
import logging
from fastapi import APIRouter, HTTPException
from database import db
from screener import screen_all_stocks
from sandbox import (
    get_or_create_account,
    execute_sandbox_exit,
    check_sandbox_exits,
    update_sandbox_prices,
    reset_sandbox,
    get_strategy_insights,
)
from scheduler import (
    run_daily_scan,
    start_scheduler,
    stop_scheduler,
    is_scheduler_running,
)

logger = logging.getLogger(__name__)

sandbox_router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])


# ============ SCREENER ============

@sandbox_router.post("/screener/run")
async def run_screener(min_score: float = 25.0):
    """Run the fast technical screener on all stocks."""
    try:
        results = await screen_all_stocks(min_score=min_score)
        return {
            "total_screened": results["total_screened"],
            "buy_candidates": results["buy_candidates"][:30],
            "short_candidates": results["short_candidates"][:30],
            "scan_time": results["scan_time"],
        }
    except Exception as e:
        logger.error(f"Screener failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@sandbox_router.get("/screener/latest")
async def get_latest_screener():
    """Get the most recent screener results."""
    result = await db.screener_results.find_one(
        {}, {"_id": 0}, sort=[("scan_time", -1)]
    )
    if not result:
        return {"message": "No screener results yet. Run a scan first."}
    return result


# ============ SANDBOX ACCOUNT ============

@sandbox_router.get("/account")
async def get_sandbox_account():
    """Get sandbox account overview (capital, P&L, stats)."""
    account = await get_or_create_account()
    return account


@sandbox_router.post("/reset")
async def reset_sandbox_account():
    """Reset sandbox to starting state (Rs.1,00,000)."""
    account = await reset_sandbox()
    return {"message": "Sandbox reset successfully", "account": account}


# ============ SANDBOX HOLDINGS ============

@sandbox_router.get("/holdings")
async def get_sandbox_holdings():
    """Get all current sandbox holdings."""
    holdings = await db.sandbox_holdings.find({}, {"_id": 0}).to_list(100)
    return holdings


@sandbox_router.post("/holdings/{symbol}/exit")
async def exit_sandbox_holding(symbol: str):
    """Manually exit a sandbox position at current market price."""
    from trading import UpstoxClient
    client = UpstoxClient()
    quotes = await client.get_batch_quotes([symbol.upper()])
    price_data = quotes.get(symbol.upper())

    if not price_data or not price_data.get("ltp"):
        raise HTTPException(status_code=400, detail=f"Could not get price for {symbol}")

    ltp = float(price_data["ltp"])
    result = await execute_sandbox_exit(symbol.upper(), ltp, exit_reason="manual")

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return result["trade"]


@sandbox_router.post("/holdings/refresh-prices")
async def refresh_sandbox_prices():
    """Update current prices on all sandbox holdings."""
    updated = await update_sandbox_prices()
    return {"updated": updated}


@sandbox_router.post("/holdings/check-exits")
async def trigger_exit_check():
    """Manually trigger stop-loss/target check on all holdings."""
    exits = await check_sandbox_exits()
    return {"exits_triggered": len(exits), "exits": exits}


# ============ SANDBOX TRADE HISTORY ============

@sandbox_router.get("/trades")
async def get_sandbox_trades(limit: int = 50):
    """Get sandbox trade history (completed trades)."""
    trades = await db.sandbox_trades.find(
        {}, {"_id": 0}
    ).sort("exited_at", -1).to_list(limit)
    return trades


# ============ STRATEGY INSIGHTS ============

@sandbox_router.get("/strategy")
async def get_sandbox_strategy():
    """Get AI strategy insights from sandbox performance."""
    insights = await get_strategy_insights()
    return insights


# ============ SCHEDULER ============

@sandbox_router.get("/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status and config."""
    config = await db.scheduler_config.find_one({"id": "scheduler_config"}, {"_id": 0})
    return {
        "running": is_scheduler_running(),
        "config": config or {},
    }


@sandbox_router.post("/scheduler/start")
async def start_scheduler_endpoint():
    """Start the automated daily scanner."""
    result = await start_scheduler()
    return result


@sandbox_router.post("/scheduler/stop")
async def stop_scheduler_endpoint():
    """Stop the automated daily scanner."""
    result = await stop_scheduler()
    return result


@sandbox_router.post("/scheduler/config")
async def update_scheduler_config(
    max_positions: int = 5,
    max_trade_value: float = 20000.0,
    min_screener_score: float = 30.0,
    scan_time: str = "09:20",
):
    """Update scheduler configuration."""
    update = {
        "max_positions": max_positions,
        "max_trade_value": max_trade_value,
        "min_screener_score": min_screener_score,
        "scan_time": scan_time,
    }
    await db.scheduler_config.update_one(
        {"id": "scheduler_config"},
        {"$set": update},
        upsert=True,
    )
    return {"message": "Config updated", **update}


@sandbox_router.post("/scheduler/run-now")
async def run_scan_now():
    """Manually trigger a full daily scan right now."""
    try:
        result = await run_daily_scan()
        return result
    except Exception as e:
        logger.error(f"Manual scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@sandbox_router.get("/scheduler/logs")
async def get_scheduler_logs(limit: int = 20):
    """Get recent scheduler run logs."""
    logs = await db.scheduler_logs.find(
        {}, {"_id": 0}
    ).sort("started_at", -1).to_list(limit)
    return logs
