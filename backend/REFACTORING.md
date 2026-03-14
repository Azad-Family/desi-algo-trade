# Backend Refactoring Documentation

## Overview
The backend has been refactored from a single 943-line `server.py` into a modular, maintainable structure with clear separation of concerns.

## Directory Structure

```
backend/
├── server.py              # Main FastAPI app entry point (clean & minimal)
├── database.py            # MongoDB configuration and utilities
├── models.py              # Pydantic models and enums
├── stock_data.py          # Stock universe data (59 stocks)
├── ai_engine.py           # AI analysis & recommendation engine (Gemini)
├── trading.py             # Upstox trading integration
├── routes.py              # All API route handlers
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (not in repo)
├── .env.example           # Environment variable template
└── server_old.py          # Backup of original single-file version
```

## Module Descriptions

### `server.py` - Main Application (~70 lines)
**Purpose:** Bootstrap the FastAPI application with startup/shutdown events and middleware.

**Key Responsibilities:**
- Initialize FastAPI app
- Setup database connection on startup
- Auto-initialize stock universe if empty
- Configure CORS middleware
- Register routes

**Imports:** database, routes, models, stock_data

---

### `database.py` - Database Layer (~50 lines)
**Purpose:** Handle MongoDB connection and initialization.

**Key Features:**
- Load `.env` environment variables
- Validate `MONGO_URL` and `DB_NAME`
- Provide single `db` instance for all modules
- Close connection on shutdown

**Exports:** `db`, `close_db()`

---

### `models.py` - Data Models (~145 lines)
**Purpose:** Define all Pydantic models and enums.

**Enums:**
- `Sector` - 12 stock sectors
- `TradeAction` - BUY/SELL
- `TradeStatus` - pending, approved, executed, etc.
- `AnalysisType` - fundamental, momentum, hybrid

**Models:**
- `Stock` - Stock universe data
- `TradeRecommendation` - AI trade suggestions
- `Portfolio` - Holdings
- `TradeHistory` - Executed trades
- `Settings` - User preferences
- `AIAnalysisRequest/Response` - AI endpoint contracts

---

### `stock_data.py` - Stock Universe (~60 lines)
**Purpose:** Central repository for all 59 stock definitions.

**Contents:**
- 59 Indian stocks across 12 sectors (IT, Banking, Pharma, Auto, FMCG, Energy, Metal, Infrastructure, Telecom, Consumer, Realty, Cement)

**Usage:**
```python
from stock_data import STOCK_UNIVERSE
for stock in STOCK_UNIVERSE:
    print(stock['symbol'])  # TCS, INFY, WIPRO, etc.
```

---

### `ai_engine.py` - AI Service (~120 lines)
**Purpose:** All AI analysis and recommendation generation logic.

**Functions:**
- `get_ai_stock_analysis()` - Multi-factor analysis using Gemini
  - Fundamental analysis
  - Technical/Momentum analysis
  - Risk assessment
  - Confidence scoring

- `generate_trade_recommendation()` - BUY/SELL/HOLD recommendations
  - Uses Gemini 2.5 Flash
  - Returns structured JSON (action, target price, stop loss, etc.)
  - Handles Gemini API errors gracefully

**Dependencies:** google-generativeai, os, logging

**Configuration:**
- Uses `GOOGLE_GEMINI_KEY` from `.env`
- Falls back to simulations if key missing

---

### `trading.py` - Trading Integration (~80 lines)
**Purpose:** Upstox API integration for order placement and market quotes.

**Class: `UpstoxClient`**
- `is_configured()` - Check if credentials present
- `get_market_quote(symbol)` - Real-time market data
- `place_order(symbol, action, quantity, price)` - Place orders
  - Returns real orders if configured
  - Returns simulated orders if not (for testing)

**Configuration:**
- Uses `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_ACCESS_TOKEN` from `.env`
- Gracefully degrades to simulation mode if misconfigured

---

### `routes.py` - API Handlers (~450 lines)
**Purpose:** All REST API endpoints organized by domain.

**Route Groups:**

1. **Root & Health** (2 endpoints)
   - `GET /api/` - API info
   - `GET /api/health` - Database health check

2. **Stock Universe** (5 endpoints)
   - `GET /api/stocks` - All stocks
   - `GET /api/stocks/{symbol}` - Single stock
   - `GET /api/stocks/sector/{sector}` - By sector
   - `GET /api/stocks/sectors` - Sector summary
   - `POST /api/stocks/initialize` - Reinitialize universe

3. **AI Analysis** (3 endpoints)
   - `POST /api/ai/analyze` - Deep analysis (saves to history)
   - `POST /api/ai/generate-recommendation/{symbol}` - Trade suggestion
   - `POST /api/ai/scan-all` - Background scan of top 5 stocks

4. **Trade Recommendations** (3 endpoints)
   - `GET /api/recommendations` - All recommendations (filterable by status)
   - `GET /api/recommendations/pending` - Pending approvals
   - `POST /api/recommendations/{rec_id}/approve` - Execute or reject

5. **Portfolio** (2 endpoints)
   - `GET /api/portfolio` - Holdings + summary
   - `GET /api/portfolio/sector-breakdown` - Sector allocation

6. **Trade History** (2 endpoints)
   - `GET /api/trades/history` - Execution log
   - `GET /api/trades/stats` - Total traded value, counts

7. **Settings** (2 endpoints)
   - `GET /api/settings` - User preferences (masked sensitive data)
   - `POST /api/settings` - Update preferences

8. **Dashboard** (1 endpoint)
   - `GET /api/dashboard/stats` - KPIs (portfolio value, P&L, pending trades, etc.)

**Helper Functions:**
- `update_portfolio()` - Updates holdings after a trade execution (BUY/SELL)

---

## Import Dependencies

```
server.py
├── database (db instance)
├── routes (api_router)
├── models (Stock)
└── stock_data (STOCK_UNIVERSE)

routes.py
├── models (all Pydantic models)
├── stock_data (STOCK_UNIVERSE)
├── ai_engine (analysis & recommendations)
├── trading (UpstoxClient)
└── database (db instance)

ai_engine.py
├── google.generativeai
├── os, logging, json, re

trading.py
├── httpx (async HTTP)
├── os, logging, uuid
```

---

## Running the Application

### Setup
```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Configuration
Create `.env` in workspace root:
```
MONGO_URL=mongodb+srv://user:pass@host/db
DB_NAME=desi_algo_trade
GOOGLE_GEMINI_KEY=AIzaSy...
UPSTOX_API_KEY=optional
UPSTOX_API_SECRET=optional
UPSTOX_ACCESS_TOKEN=optional
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

### Start Server
```bash
set REACT_APP_BACKEND_URL=http://localhost:8000
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Visit: http://localhost:8000/docs (Swagger UI)

---

## Benefits of Refactoring

| Metric | Before | After |
|--------|--------|-------|
| Single File Lines | 943 | ~70 (main) |
| Module Complexity | Very High | Low (each ~50-450 lines) |
| Code Reusability | Poor | High (ai_engine, trading isolated) |
| Testing | Difficult | Easy (can mock database/AI) |
| Maintenance | Error-prone | Clear structure |
| Onboarding | Hard to understand | Clear module directories |

---

## Future Enhancements

1. **Split routes.py** - Separate into sub-routers: stocks.py, ai.py, trades.py, portfolio.py, settings.py
2. **Add services layer** - Portfolio service, TradeService, StockService for business logic
3. **Add tests** - Unit tests for each module, API integration tests
4. **Add caching** - Redis for frequently accessed stock data
5. **Add async job queue** - Celery for background analysis tasks
6. **Add WebSocket** - Real-time price updates to frontend
7. **Add database migrations** - Alembic for schema management
8. **Add logging** - Structured logging with correlation IDs

---

## File Sizes & Dependencies

```
models.py         ~145 lines   (no external deps)
stock_data.py     ~60 lines    (no external deps)
ai_engine.py      ~120 lines   → google-generativeai
trading.py        ~80 lines    → httpx
database.py       ~50 lines    → motor, pymongo
routes.py         ~450 lines   → fastapi, all models
server.py         ~70 lines    → fastapi, starlette
```

**Total:** ~975 lines (slightly more due to better documentation and error handling)
**Improvement:** Clear separation beats line count gain

---

Generated: 2026-02-23  
Original file: server_old.py (kept as backup)
