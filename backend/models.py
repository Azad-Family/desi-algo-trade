"""Data models for the trading application"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime, timezone
import uuid as uuid_lib


# ============ ENUMS ============
class Sector(str, Enum):
    IT = "IT"
    BANKING = "Banking"
    PHARMA = "Pharma"
    AUTO = "Auto"
    FMCG = "FMCG"
    ENERGY = "Energy"
    METAL = "Metal"
    REALTY = "Realty"
    INFRA = "Infrastructure"
    CONSUMER = "Consumer"
    TELECOM = "Telecom"
    CEMENT = "Cement"


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"


class TradeStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class AnalysisType(str, Enum):
    FUNDAMENTAL = "fundamental"
    MOMENTUM = "momentum"
    HYBRID = "hybrid"


class TradeMode(str, Enum):
    """Trading mode: live market, sandbox paper trading, or simulated (no token)"""
    LIVE = "live"
    SANDBOX = "sandbox"
    SIMULATED = "simulated"


class TradeHorizon(str, Enum):
    SHORT_TERM = "short_term"    # 1-2 weeks
    MEDIUM_TERM = "medium_term"  # 1-3 months
    LONG_TERM = "long_term"      # 3-12 months


# ============ MODELS ============
class Stock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid_lib.uuid4()))
    symbol: str
    name: str
    sector: str
    exchange: str = "NSE"
    isin: Optional[str] = None
    current_price: float = 0.0
    change_percent: float = 0.0
    volume: int = 0
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StockCreate(BaseModel):
    symbol: str
    name: str
    sector: str
    exchange: str = "NSE"


class TradeRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid_lib.uuid4()))
    stock_symbol: str
    stock_name: str
    sector: str = ""
    action: str
    quantity: int
    target_price: float
    current_price: float
    stop_loss: Optional[float] = None
    ai_reasoning: str
    confidence_score: float
    analysis_type: str = "hybrid"
    trade_horizon: str = "medium_term"
    horizon_rationale: Optional[str] = None
    product_type: str = "DELIVERY"
    key_signals: Dict[str, str] = {}
    status: str = "pending"
    trade_mode: str = "live"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    executed_at: Optional[str] = None
    executed_price: Optional[float] = None


class TradeApproval(BaseModel):
    approved: bool
    modified_quantity: Optional[int] = None
    modified_price: Optional[float] = None
    notes: Optional[str] = None


class Portfolio(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid_lib.uuid4()))
    stock_symbol: str
    stock_name: str
    quantity: int
    avg_buy_price: float
    current_price: float = 0.0
    invested_value: float = 0.0
    current_value: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    sector: str
    action: str = "BUY"
    product_type: str = "DELIVERY"
    is_short: bool = False
    trade_mode: str = "simulated"
    trade_horizon: Optional[str] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    bought_at: Optional[str] = None
    ai_recommendation_id: Optional[str] = None
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TradeHistory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid_lib.uuid4()))
    stock_symbol: str
    stock_name: str
    action: str
    quantity: int
    price: float
    total_value: float
    pnl: Optional[float] = None
    status: str
    trade_mode: str = "simulated"
    executed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    order_id: Optional[str] = None
    ai_recommendation_id: Optional[str] = None


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "main_settings"
    max_trade_value: float = 100000.0
    max_position_size: int = 100
    risk_per_trade_percent: float = 2.0
    auto_analysis_enabled: bool = True
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AIAnalysisRequest(BaseModel):
    stock_symbol: str
    analysis_type: str = "hybrid"


class AIAnalysisResponse(BaseModel):
    stock_symbol: str
    analysis: str
    recommendation: Optional[str] = None
    confidence_score: float = 0.0
    trade_horizon: Optional[str] = None
    key_signals: Dict[str, Any] = {}
    key_metrics: Dict[str, Any] = {}


# ============ SANDBOX MODELS ============

class SandboxAccount(BaseModel):
    """Virtual trading account for sandbox/paper trading."""
    model_config = ConfigDict(extra="ignore")
    id: str = "sandbox_account"
    starting_capital: float = 100000.0
    current_capital: float = 100000.0
    invested_value: float = 0.0
    current_value: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    avg_trade_pnl: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SandboxHolding(BaseModel):
    """A position held in the sandbox portfolio."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid_lib.uuid4()))
    stock_symbol: str
    stock_name: str
    action: str = "BUY"  # BUY or SHORT
    product_type: str = "CNC"  # CNC (delivery) or INTRADAY
    quantity: int
    entry_price: float
    current_price: float = 0.0
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    sector: str = ""
    ai_reasoning: str = ""
    confidence_score: float = 0.0
    trade_horizon: str = "short_term"
    entered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SandboxTrade(BaseModel):
    """A completed sandbox trade (entry + exit)."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid_lib.uuid4()))
    stock_symbol: str
    stock_name: str
    action: str  # BUY or SHORT
    product_type: str = "CNC"  # CNC or INTRADAY
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    pnl_pct: float
    holding_duration_hours: float = 0.0
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    exit_reason: str = ""  # target_hit, stop_loss_hit, ai_exit, manual, intraday_squareoff
    ai_reasoning: str = ""
    confidence_score: float = 0.0
    entered_at: str = ""
    exited_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SchedulerConfig(BaseModel):
    """Configuration for the automated daily scanner/trader."""
    model_config = ConfigDict(extra="ignore")
    id: str = "scheduler_config"
    enabled: bool = False
    scan_time: str = "09:20"  # IST, 5 minutes after market open
    exit_scan_time: str = "15:00"  # IST, 30 min before close
    max_positions: int = 5
    max_trade_value: float = 20000.0  # per trade for sandbox
    min_screener_score: float = 30.0
    auto_execute_sandbox: bool = True
    screener_concurrency: int = 5
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ============ AGENT / CHAT MODELS ============

class MessageBlockType(str, Enum):
    TEXT = "text"
    MARKET_OVERVIEW = "market_overview"
    STOCK_CARDS = "stock_cards"
    ANALYSIS = "analysis"
    TRADE_SIGNAL = "trade_signal"
    SUGGESTED_PROMPTS = "suggested_prompts"


class MessageBlock(BaseModel):
    type: MessageBlockType
    content: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class AgentMessage(BaseModel):
    role: str = "agent"
    blocks: List[MessageBlock] = []
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str = Field(default_factory=lambda: str(uuid_lib.uuid4()))
    date: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    messages: List[Dict[str, Any]] = []
    context: Dict[str, Any] = Field(default_factory=lambda: {
        "user_focus": "",
        "sectors": [],
        "themes": [],
        "shortlisted_stocks": [],
        "analyzed_stocks": [],
    })
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
