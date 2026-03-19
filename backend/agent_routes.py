"""API routes for the conversational trading agent."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import db
from models import AgentSession
from agent_orchestrator import process_message

logger = logging.getLogger(__name__)

agent_router = APIRouter(prefix="/api/agent")


class UserMessage(BaseModel):
    message: str
    session_id: Optional[str] = None


async def _get_or_create_session(session_id: Optional[str] = None) -> dict:
    """Load today's session or create a new one.

    If session_id is given, load that specific session.
    Otherwise load the most recent session for today's date.
    If none exists, create a fresh one.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if session_id:
        doc = await db.agent_sessions.find_one({"session_id": session_id}, {"_id": 0})
        if doc:
            return doc

    doc = await db.agent_sessions.find_one(
        {"date": today},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if doc:
        return doc

    session = AgentSession(date=today)
    session_dict = session.model_dump()
    await db.agent_sessions.insert_one(session_dict)
    return session_dict


async def _persist_session(session: dict):
    """Save session back to MongoDB."""
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.agent_sessions.replace_one(
        {"session_id": session["session_id"]},
        {k: v for k, v in session.items() if k != "_id"},
        upsert=True,
    )


@agent_router.post("/message")
async def send_message(body: UserMessage):
    """Send a message to the agent and get a structured response."""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session = await _get_or_create_session(body.session_id)

    now = datetime.now(timezone.utc).isoformat()
    user_msg = {"role": "user", "blocks": [{"type": "text", "content": body.message}], "timestamp": now}
    session.setdefault("messages", []).append(user_msg)

    response_blocks = await process_message(body.message, session)

    agent_msg = {"role": "agent", "blocks": response_blocks, "timestamp": datetime.now(timezone.utc).isoformat()}
    session["messages"].append(agent_msg)

    await _persist_session(session)

    return {
        "session_id": session["session_id"],
        "blocks": response_blocks,
        "context": session.get("context", {}),
    }


@agent_router.get("/session/current")
async def get_current_session():
    """Get today's active session with full message history."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.agent_sessions.find_one(
        {"date": today}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not doc:
        session = AgentSession(date=today)
        doc = session.model_dump()
        await db.agent_sessions.insert_one(doc)
    return doc


@agent_router.get("/sessions")
async def list_sessions(limit: int = 30):
    """List past agent sessions (most recent first)."""
    sessions = await db.agent_sessions.find(
        {},
        {"_id": 0, "session_id": 1, "date": 1, "created_at": 1, "updated_at": 1, "context": 1},
    ).sort("created_at", -1).to_list(limit)

    result = []
    for s in sessions:
        msg_count = len(s.get("messages", []))  # not projected, so 0 here
        result.append({
            "session_id": s["session_id"],
            "date": s["date"],
            "created_at": s.get("created_at", ""),
            "updated_at": s.get("updated_at", ""),
            "focus": s.get("context", {}).get("user_focus", ""),
            "sectors": s.get("context", {}).get("sectors", []),
            "shortlisted_stocks": s.get("context", {}).get("shortlisted_stocks", []),
        })
    return result


@agent_router.post("/session/new")
async def create_new_session():
    """Force-start a fresh session (even if one exists today)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    session = AgentSession(date=today)
    doc = session.model_dump()
    await db.agent_sessions.insert_one(doc)
    return doc


@agent_router.get("/status")
async def get_agent_status():
    """Return live status and recent activity for all agents."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_iso_prefix = today + "T"

    # 1. Orchestrator – today's session info
    session = await db.agent_sessions.find_one(
        {"date": today}, {"_id": 0}, sort=[("created_at", -1)]
    )
    orchestrator = {
        "messages_today": len(session.get("messages", [])) if session else 0,
        "focus": session.get("context", {}).get("user_focus", "") if session else "",
        "sectors": session.get("context", {}).get("sectors", []) if session else [],
        "shortlisted": session.get("context", {}).get("shortlisted_stocks", []) if session else [],
        "analyzed": session.get("context", {}).get("analyzed_stocks", []) if session else [],
    }

    # 2. Stock Analyst – recent analyses
    analyses_today = await db.analysis_history.count_documents(
        {"created_at": {"$gte": today_iso_prefix}}
    )
    recent_analyses = await db.analysis_history.find(
        {},
        {"_id": 0, "stock_symbol": 1, "confidence_score": 1, "trade_horizon": 1,
         "source": 1, "created_at": 1, "analysis_type": 1},
    ).sort("created_at", -1).to_list(8)

    # 3. Buy Signal Agent – recent BUY recommendations
    pending_buys = await db.trade_recommendations.count_documents(
        {"action": "BUY", "status": "pending"}
    )
    recent_buys = await db.trade_recommendations.find(
        {"action": "BUY"},
        {"_id": 0, "stock_symbol": 1, "stock_name": 1, "status": 1,
         "confidence_score": 1, "current_price": 1, "target_price": 1,
         "quantity": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(8)

    # 4. Sell Signal Agent – recent SELL recommendations
    pending_sells = await db.trade_recommendations.count_documents(
        {"action": "SELL", "status": "pending"}
    )
    recent_sells = await db.trade_recommendations.find(
        {"action": "SELL"},
        {"_id": 0, "stock_symbol": 1, "stock_name": 1, "status": 1,
         "confidence_score": 1, "current_price": 1, "target_price": 1,
         "quantity": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(8)

    return {
        "orchestrator": orchestrator,
        "stock_analyst": {
            "analyses_today": analyses_today,
            "recent": recent_analyses,
        },
        "buy_signal": {
            "pending": pending_buys,
            "recent": recent_buys,
        },
        "sell_signal": {
            "pending": pending_sells,
            "recent": recent_sells,
        },
    }
