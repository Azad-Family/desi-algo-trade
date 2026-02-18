from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid as uuid_lib
from datetime import datetime, timezone
from enum import Enum
import asyncio
import httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI(title="AI Trading Agent - Indian Stocks")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    status: str = "pending"
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
    executed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    order_id: Optional[str] = None
    ai_recommendation_id: Optional[str] = None

class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "main_settings"
    upstox_api_key: Optional[str] = None
    upstox_api_secret: Optional[str] = None
    upstox_access_token: Optional[str] = None
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
    key_metrics: Dict[str, Any] = {}

# ============ STOCK UNIVERSE DATA ============
STOCK_UNIVERSE = [
    # IT Sector (10 stocks)
    {"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "IT"},
    {"symbol": "INFY", "name": "Infosys Ltd", "sector": "IT"},
    {"symbol": "WIPRO", "name": "Wipro Ltd", "sector": "IT"},
    {"symbol": "HCLTECH", "name": "HCL Technologies", "sector": "IT"},
    {"symbol": "TECHM", "name": "Tech Mahindra", "sector": "IT"},
    {"symbol": "LTIM", "name": "LTIMindtree Ltd", "sector": "IT"},
    {"symbol": "PERSISTENT", "name": "Persistent Systems", "sector": "IT"},
    {"symbol": "COFORGE", "name": "Coforge Ltd", "sector": "IT"},
    {"symbol": "MPHASIS", "name": "Mphasis Ltd", "sector": "IT"},
    {"symbol": "LTTS", "name": "L&T Technology Services", "sector": "IT"},
    
    # Banking Sector (10 stocks)
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "sector": "Banking"},
    {"symbol": "ICICIBANK", "name": "ICICI Bank", "sector": "Banking"},
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Banking"},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank", "sector": "Banking"},
    {"symbol": "AXISBANK", "name": "Axis Bank", "sector": "Banking"},
    {"symbol": "INDUSINDBK", "name": "IndusInd Bank", "sector": "Banking"},
    {"symbol": "BANDHANBNK", "name": "Bandhan Bank", "sector": "Banking"},
    {"symbol": "PNB", "name": "Punjab National Bank", "sector": "Banking"},
    {"symbol": "BANKBARODA", "name": "Bank of Baroda", "sector": "Banking"},
    {"symbol": "FEDERALBNK", "name": "Federal Bank", "sector": "Banking"},
    
    # Pharma Sector (6 stocks)
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical", "sector": "Pharma"},
    {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories", "sector": "Pharma"},
    {"symbol": "CIPLA", "name": "Cipla Ltd", "sector": "Pharma"},
    {"symbol": "DIVISLAB", "name": "Divi's Laboratories", "sector": "Pharma"},
    {"symbol": "AUROPHARMA", "name": "Aurobindo Pharma", "sector": "Pharma"},
    {"symbol": "BIOCON", "name": "Biocon Ltd", "sector": "Pharma"},
    
    # Auto Sector (6 stocks)
    {"symbol": "TATAMOTORS", "name": "Tata Motors", "sector": "Auto"},
    {"symbol": "MARUTI", "name": "Maruti Suzuki India", "sector": "Auto"},
    {"symbol": "M&M", "name": "Mahindra & Mahindra", "sector": "Auto"},
    {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto", "sector": "Auto"},
    {"symbol": "HEROMOTOCO", "name": "Hero MotoCorp", "sector": "Auto"},
    {"symbol": "EICHERMOT", "name": "Eicher Motors", "sector": "Auto"},
    
    # FMCG Sector (6 stocks)
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever", "sector": "FMCG"},
    {"symbol": "ITC", "name": "ITC Ltd", "sector": "FMCG"},
    {"symbol": "NESTLEIND", "name": "Nestle India", "sector": "FMCG"},
    {"symbol": "BRITANNIA", "name": "Britannia Industries", "sector": "FMCG"},
    {"symbol": "DABUR", "name": "Dabur India", "sector": "FMCG"},
    {"symbol": "MARICO", "name": "Marico Ltd", "sector": "FMCG"},
    
    # Energy Sector (5 stocks)
    {"symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Energy"},
    {"symbol": "ONGC", "name": "Oil & Natural Gas Corp", "sector": "Energy"},
    {"symbol": "BPCL", "name": "Bharat Petroleum", "sector": "Energy"},
    {"symbol": "IOC", "name": "Indian Oil Corporation", "sector": "Energy"},
    {"symbol": "NTPC", "name": "NTPC Ltd", "sector": "Energy"},
    
    # Metal Sector (5 stocks)
    {"symbol": "TATASTEEL", "name": "Tata Steel", "sector": "Metal"},
    {"symbol": "JSWSTEEL", "name": "JSW Steel", "sector": "Metal"},
    {"symbol": "HINDALCO", "name": "Hindalco Industries", "sector": "Metal"},
    {"symbol": "COALINDIA", "name": "Coal India", "sector": "Metal"},
    {"symbol": "VEDL", "name": "Vedanta Ltd", "sector": "Metal"},
    
    # Infrastructure (4 stocks)
    {"symbol": "LT", "name": "Larsen & Toubro", "sector": "Infrastructure"},
    {"symbol": "ADANIPORTS", "name": "Adani Ports & SEZ", "sector": "Infrastructure"},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement", "sector": "Infrastructure"},
    {"symbol": "GRASIM", "name": "Grasim Industries", "sector": "Infrastructure"},
    
    # Telecom (3 stocks)
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel", "sector": "Telecom"},
    {"symbol": "IDEA", "name": "Vodafone Idea", "sector": "Telecom"},
    {"symbol": "TATACOMM", "name": "Tata Communications", "sector": "Telecom"},
    
    # Consumer/Retail (3 stocks)
    {"symbol": "TITAN", "name": "Titan Company", "sector": "Consumer"},
    {"symbol": "TRENT", "name": "Trent Ltd", "sector": "Consumer"},
    {"symbol": "DMART", "name": "Avenue Supermarts", "sector": "Consumer"},
]

# ============ AI RESEARCH AGENT ============
async def get_ai_stock_analysis(stock_symbol: str, stock_name: str, sector: str, analysis_type: str = "hybrid") -> Dict[str, Any]:
    """Use Gemini 3 Flash to analyze a stock"""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="LLM API key not configured")
    
    chat = LlmChat(
        api_key=api_key,
        session_id=f"stock-analysis-{stock_symbol}-{datetime.now(timezone.utc).isoformat()}",
        system_message="""You are an expert Indian stock market analyst specializing in NSE/BSE stocks. 
        You provide detailed analysis combining fundamental and technical/momentum factors.
        Always be specific with numbers, ratios, and actionable insights.
        Focus on Indian market context - FII/DII flows, sector rotation, RBI policies, etc."""
    ).with_model("gemini", "gemini-3-flash-preview")
    
    analysis_prompt = f"""
    Analyze {stock_name} ({stock_symbol}) from the {sector} sector on NSE/BSE.
    
    Analysis Type: {analysis_type.upper()}
    
    Please provide:
    1. **Executive Summary** (2-3 sentences)
    2. **Fundamental Analysis** (if applicable):
       - Revenue & Profit Trends
       - Key Financial Ratios (P/E, P/B, ROE, Debt/Equity)
       - Competitive Position
       - Management Quality
    3. **Technical/Momentum Analysis** (if applicable):
       - Current Trend Direction
       - Key Support & Resistance Levels
       - Volume Analysis
       - RSI/MACD indicators overview
    4. **Sector Outlook**: How is the {sector} sector performing?
    5. **Risk Factors**: Top 3 risks
    6. **Trading Recommendation**: BUY/SELL/HOLD with target price and stop loss
    7. **Confidence Score**: (0-100)
    
    Format the response clearly with sections.
    """
    
    user_message = UserMessage(text=analysis_prompt)
    response = await chat.send_message(user_message)
    
    # Parse confidence score from response (simple extraction)
    confidence = 65.0  # Default
    if "confidence" in response.lower():
        import re
        match = re.search(r'confidence[:\s]+(\d+)', response.lower())
        if match:
            confidence = float(match.group(1))
    
    return {
        "stock_symbol": stock_symbol,
        "analysis": response,
        "confidence_score": min(confidence, 100.0),
        "analysis_type": analysis_type
    }

async def generate_trade_recommendation(stock_symbol: str, stock_name: str, sector: str) -> Optional[Dict[str, Any]]:
    """Generate a trade recommendation using AI analysis"""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    import json
    import re
    
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        return None
    
    chat = LlmChat(
        api_key=api_key,
        session_id=f"trade-rec-{stock_symbol}-{datetime.now(timezone.utc).isoformat()}",
        system_message="""You are a trading algorithm that generates specific BUY or SELL recommendations.
        You MUST respond ONLY with valid JSON. No markdown, no explanations outside JSON.
        Consider both fundamentals and momentum for Indian stocks."""
    ).with_model("gemini", "gemini-3-flash-preview")
    
    prompt = f"""
    Generate a trade recommendation for {stock_name} ({stock_symbol}) - {sector} sector.
    
    Respond with ONLY this JSON format (no other text):
    {{
        "action": "BUY" or "SELL" or "HOLD",
        "target_price": <number>,
        "current_price": <estimated current price>,
        "stop_loss": <number>,
        "quantity": <suggested quantity between 1-50>,
        "reasoning": "<2-3 sentence explanation>",
        "confidence": <0-100>
    }}
    """
    
    user_message = UserMessage(text=prompt)
    response = await chat.send_message(user_message)
    
    try:
        # Try to extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            data = json.loads(json_match.group())
            if data.get("action") in ["BUY", "SELL"]:
                return {
                    "stock_symbol": stock_symbol,
                    "stock_name": stock_name,
                    "action": data["action"],
                    "target_price": float(data.get("target_price", 0)),
                    "current_price": float(data.get("current_price", 0)),
                    "stop_loss": float(data.get("stop_loss", 0)) if data.get("stop_loss") else None,
                    "quantity": int(data.get("quantity", 10)),
                    "ai_reasoning": data.get("reasoning", "AI generated recommendation"),
                    "confidence_score": float(data.get("confidence", 60))
                }
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error(f"Failed to parse AI recommendation: {e}")
    
    return None

# ============ UPSTOX INTEGRATION ============
class UpstoxClient:
    def __init__(self):
        self.api_key = os.environ.get('UPSTOX_API_KEY', '')
        self.api_secret = os.environ.get('UPSTOX_API_SECRET', '')
        self.access_token = os.environ.get('UPSTOX_ACCESS_TOKEN', '')
        self.base_url = "https://api.upstox.com/v2"
    
    def is_configured(self) -> bool:
        return bool(self.access_token)
    
    async def get_market_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get real-time market quote for a stock"""
        if not self.is_configured():
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json"
                }
                instrument_key = f"NSE_EQ|{symbol}"
                response = await client.get(
                    f"{self.base_url}/market-quote/quotes",
                    params={"instrument_key": instrument_key},
                    headers=headers
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Upstox API error: {e}")
        return None
    
    async def place_order(self, symbol: str, action: str, quantity: int, price: float) -> Optional[Dict[str, Any]]:
        """Place an order through Upstox"""
        if not self.is_configured():
            return {"status": "simulated", "order_id": f"SIM-{uuid_lib.uuid4().hex[:8].upper()}"}
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
                order_data = {
                    "quantity": quantity,
                    "product": "D",  # Delivery
                    "validity": "DAY",
                    "price": price,
                    "instrument_token": f"NSE_EQ|{symbol}",
                    "order_type": "LIMIT",
                    "transaction_type": action,
                    "disclosed_quantity": 0,
                    "trigger_price": 0,
                    "is_amo": False
                }
                response = await client.post(
                    f"{self.base_url}/order/place",
                    json=order_data,
                    headers=headers
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Upstox order error: {e}")
        
        return {"status": "simulated", "order_id": f"SIM-{uuid_lib.uuid4().hex[:8].upper()}"}

upstox_client = UpstoxClient()

# ============ ROUTES ============

@api_router.get("/")
async def root():
    return {"message": "AI Trading Agent API - Indian Stocks", "version": "1.0.0"}

# Stock Universe Routes
@api_router.get("/stocks", response_model=List[Stock])
async def get_stocks():
    """Get all stocks in the universe"""
    stocks = await db.stocks.find({}, {"_id": 0}).to_list(100)
    return stocks

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
    """Initialize the stock universe with predefined stocks"""
    # Clear existing stocks
    await db.stocks.delete_many({})
    
    # Insert all stocks
    stocks = []
    for stock_data in STOCK_UNIVERSE:
        stock = Stock(
            symbol=stock_data["symbol"],
            name=stock_data["name"],
            sector=stock_data["sector"],
            current_price=0.0,
            change_percent=0.0
        )
        stocks.append(stock.model_dump())
    
    if stocks:
        await db.stocks.insert_many(stocks)
    
    return {"message": f"Initialized {len(stocks)} stocks", "count": len(stocks)}

@api_router.get("/stocks/{symbol}")
async def get_stock(symbol: str):
    """Get a specific stock by symbol"""
    stock = await db.stocks.find_one({"symbol": symbol.upper()}, {"_id": 0})
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    return stock

# AI Analysis Routes
@api_router.post("/ai/analyze", response_model=AIAnalysisResponse)
async def analyze_stock(request: AIAnalysisRequest):
    """Run AI analysis on a stock"""
    stock = await db.stocks.find_one({"symbol": request.stock_symbol.upper()}, {"_id": 0})
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    analysis = await get_ai_stock_analysis(
        stock["symbol"],
        stock["name"],
        stock["sector"],
        request.analysis_type
    )
    
    # Save analysis to history
    analysis_doc = {
        "id": str(uuid_lib.uuid4()),
        "stock_symbol": stock["symbol"],
        "analysis": analysis["analysis"],
        "confidence_score": analysis["confidence_score"],
        "analysis_type": request.analysis_type,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.analysis_history.insert_one(analysis_doc)
    
    return AIAnalysisResponse(
        stock_symbol=stock["symbol"],
        analysis=analysis["analysis"],
        confidence_score=analysis["confidence_score"]
    )

@api_router.post("/ai/generate-recommendation/{symbol}")
async def generate_recommendation(symbol: str):
    """Generate an AI trade recommendation for a stock"""
    stock = await db.stocks.find_one({"symbol": symbol.upper()}, {"_id": 0})
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    recommendation = await generate_trade_recommendation(
        stock["symbol"],
        stock["name"],
        stock["sector"]
    )
    
    if not recommendation:
        raise HTTPException(status_code=500, detail="Failed to generate recommendation")
    
    # Create trade recommendation
    trade_rec = TradeRecommendation(
        stock_symbol=recommendation["stock_symbol"],
        stock_name=recommendation["stock_name"],
        action=recommendation["action"],
        quantity=recommendation["quantity"],
        target_price=recommendation["target_price"],
        current_price=recommendation["current_price"],
        stop_loss=recommendation.get("stop_loss"),
        ai_reasoning=recommendation["ai_reasoning"],
        confidence_score=recommendation["confidence_score"]
    )
    
    await db.trade_recommendations.insert_one(trade_rec.model_dump())
    
    return trade_rec

@api_router.post("/ai/scan-all")
async def scan_all_stocks(background_tasks: BackgroundTasks):
    """Trigger AI scan for all stocks (runs in background)"""
    async def scan_stocks():
        stocks = await db.stocks.find({}, {"_id": 0}).to_list(100)
        for stock in stocks[:5]:  # Limit to 5 stocks per scan to avoid rate limits
            try:
                recommendation = await generate_trade_recommendation(
                    stock["symbol"],
                    stock["name"],
                    stock["sector"]
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
                        confidence_score=recommendation["confidence_score"]
                    )
                    await db.trade_recommendations.insert_one(trade_rec.model_dump())
                await asyncio.sleep(2)  # Rate limiting
            except Exception as e:
                logger.error(f"Error scanning {stock['symbol']}: {e}")
    
    background_tasks.add_task(scan_stocks)
    return {"message": "Stock scan initiated", "status": "running"}

# Trade Recommendations Routes
@api_router.get("/recommendations")
async def get_recommendations(status: Optional[str] = None):
    """Get all trade recommendations"""
    query = {}
    if status:
        query["status"] = status
    recommendations = await db.trade_recommendations.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return recommendations

@api_router.get("/recommendations/pending")
async def get_pending_recommendations():
    """Get pending trade recommendations awaiting approval"""
    recommendations = await db.trade_recommendations.find(
        {"status": "pending"}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return recommendations

@api_router.post("/recommendations/{rec_id}/approve")
async def approve_recommendation(rec_id: str, approval: TradeApproval):
    """Approve or reject a trade recommendation"""
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
        
        # Execute trade through Upstox (or simulate)
        order_result = await upstox_client.place_order(
            rec["stock_symbol"],
            rec["action"],
            quantity,
            price
        )
        
        # Update recommendation with execution details
        await db.trade_recommendations.update_one(
            {"id": rec_id},
            {"$set": {
                "status": "executed",
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "executed_price": price
            }}
        )
        
        # Record trade history
        trade_history = TradeHistory(
            stock_symbol=rec["stock_symbol"],
            stock_name=rec["stock_name"],
            action=rec["action"],
            quantity=quantity,
            price=price,
            total_value=quantity * price,
            status="executed",
            order_id=order_result.get("order_id"),
            ai_recommendation_id=rec_id
        )
        await db.trade_history.insert_one(trade_history.model_dump())
        
        # Update portfolio
        await update_portfolio(rec["stock_symbol"], rec["stock_name"], rec["action"], quantity, price, rec.get("sector", ""))
    
    updated_rec = await db.trade_recommendations.find_one({"id": rec_id}, {"_id": 0})
    return updated_rec

async def update_portfolio(symbol: str, name: str, action: str, quantity: int, price: float, sector: str):
    """Update portfolio after a trade"""
    existing = await db.portfolio.find_one({"stock_symbol": symbol}, {"_id": 0})
    
    if action == "BUY":
        if existing:
            # Update existing position
            new_qty = existing["quantity"] + quantity
            new_invested = existing["invested_value"] + (quantity * price)
            new_avg = new_invested / new_qty if new_qty > 0 else 0
            await db.portfolio.update_one(
                {"stock_symbol": symbol},
                {"$set": {
                    "quantity": new_qty,
                    "avg_buy_price": new_avg,
                    "invested_value": new_invested,
                    "current_value": new_qty * price,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        else:
            # Create new position
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
                sector=sector
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
                    "current_value": new_qty * price,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )

# Portfolio Routes
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

# Trade History Routes
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

# Settings Routes
@api_router.get("/settings")
async def get_settings():
    """Get application settings"""
    settings = await db.settings.find_one({"id": "main_settings"}, {"_id": 0})
    if not settings:
        default_settings = Settings()
        await db.settings.insert_one(default_settings.model_dump())
        settings = default_settings.model_dump()
    
    # Mask sensitive data
    if settings.get("upstox_api_key"):
        settings["upstox_api_key"] = "****" + settings["upstox_api_key"][-4:] if len(settings["upstox_api_key"]) > 4 else "****"
    if settings.get("upstox_api_secret"):
        settings["upstox_api_secret"] = "****"
    if settings.get("upstox_access_token"):
        settings["upstox_access_token"] = "****" + settings["upstox_access_token"][-4:] if len(settings["upstox_access_token"]) > 4 else "****"
    
    return settings

@api_router.post("/settings")
async def update_settings(settings: Settings):
    """Update application settings"""
    settings_dict = settings.model_dump()
    settings_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.settings.update_one(
        {"id": "main_settings"},
        {"$set": settings_dict},
        upsert=True
    )
    
    # Update environment variables if Upstox credentials provided
    if settings.upstox_api_key:
        os.environ['UPSTOX_API_KEY'] = settings.upstox_api_key
    if settings.upstox_api_secret:
        os.environ['UPSTOX_API_SECRET'] = settings.upstox_api_secret
    if settings.upstox_access_token:
        os.environ['UPSTOX_ACCESS_TOKEN'] = settings.upstox_access_token
    
    return {"message": "Settings updated successfully"}

# Dashboard Stats
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

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
