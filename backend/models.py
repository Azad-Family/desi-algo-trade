"""Data models for the trading application"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
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
    key_signals: Dict[str, str] = {}
    key_metrics: Dict[str, Any] = {}
