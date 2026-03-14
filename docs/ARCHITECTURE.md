# Technical Architecture

## Overview

**AlgoTrade** is an AI-powered stock analysis and trading application for Indian markets (NSE/BSE). It combines real-time and historical market data, technical analysis, and an LLM (Google Gemini) to produce trade recommendations with a human-in-the-loop approval workflow.

---

## High-Level Stack

| Layer        | Technology |
|-------------|------------|
| **Frontend** | React 19, React Router, Axios, Tailwind CSS, shadcn/ui, Lucide icons, Sonner (toast) |
| **Backend**  | FastAPI, Uvicorn (ASGI) |
| **Database** | MongoDB (Motor async driver) |
| **AI**       | Google Gemini 2.5 Flash (google-genai SDK), Google Search grounding |
| **Market / Orders** | Upstox API (V2 market quotes, V3 historical candles, V3 order placement) |
| **Technical analysis** | pandas, pandas-ta |

---

## Repository Structure

```
desi-algo-trade/
├── backend/
│   ├── server.py          # FastAPI app entry, CORS, startup/shutdown
│   ├── routes.py          # All API endpoints
│   ├── database.py        # MongoDB connection
│   ├── models.py          # Pydantic models and enums
│   ├── stock_data.py      # Static stock universe (symbol, name, sector)
│   ├── stock_init.py      # DB initialization of stocks from stock_data
│   ├── trading.py         # UpstoxClient (quotes, historical candles, orders)
│   ├── indicators.py      # Technical indicators (pandas-ta) from OHLCV
│   ├── ai_engine.py       # Gemini analysis, recommendations, sell signals
│   ├── requirements.txt
│   └── .env               # Secrets and config (not committed)
├── frontend/
│   ├── src/
│   │   ├── App.js         # Router, sidebar, routes
│   │   ├── pages/         # Dashboard, StockUniverse, AIResearch, TradeQueue, Portfolio, TradeHistory, Settings
│   │   └── components/ui/ # shadcn-style UI components
│   ├── public/
│   └── package.json
├── docs/
│   ├── ARCHITECTURE.md    # This file
│   └── PROCESS_FLOWS.md
├── memory/
│   └── PRD.md
└── README.md
```

---

## Backend Modules

### 1. `server.py`

- Creates FastAPI app, mounts `api_router` at `/api`.
- **Startup**: If `stocks` collection is empty, calls `initialize_stocks()` to load the predefined universe from `stock_data.STOCK_UNIVERSE`.
- **Shutdown**: Closes MongoDB connection.
- CORS: Configurable via `CORS_ORIGINS` (default `*`).

### 2. `routes.py`

- Single `APIRouter` with prefix `/api`; all endpoints live under `/api/*`.
- **Helpers**: `_get_technical_data(symbol)` (historical candles + indicators), `_get_risk_settings()` (from `settings`).
- **Groups**: Root/health, stocks, market, AI (analyze, latest analysis, generate recommendation, scan-all), recommendations (list, approve), portfolio (holdings, refresh prices, scan-sells), trades (history, stats), settings, dashboard stats.
- Uses `UpstoxClient` (singleton), `db` (MongoDB), and AI/indicator functions.

### 3. `database.py`

- Loads `.env` via `python-dotenv`.
- `MONGO_URL`, `DB_NAME` required.
- `AsyncIOMotorClient` → `db = client[DB_NAME]`.
- Exposes `get_db()`, `close_db()`.

### 4. `models.py`

- **Enums**: Sector, TradeAction, TradeStatus, AnalysisType, TradeMode, TradeHorizon.
- **Models**: Stock, StockCreate, TradeRecommendation, TradeApproval, Portfolio, TradeHistory, Settings, AIAnalysisRequest, AIAnalysisResponse.
- All use Pydantic; ids and timestamps have defaults where applicable.

### 5. `stock_data.py`

- `STOCK_UNIVERSE`: list of `{symbol, name, sector}` for ~59 NSE stocks across IT, Banking, Pharma, Auto, FMCG, Energy, Metal, Infrastructure, Telecom, Consumer.

### 6. `stock_init.py`

- `initialize_stocks()`: Locked, clears `stocks`, inserts from `STOCK_UNIVERSE`.
- `get_stock_count()`: Returns count for startup check.

### 7. `trading.py` (UpstoxClient)

- **Credentials**:  
  - **Market data** (quotes, historical candles): always `UPSTOX_ACCESS_TOKEN` (live).  
  - **Orders**: `UPSTOX_SANDBOX_ACCESS_TOKEN` when `UPSTOX_USE_SANDBOX=true`, else live token.
- **Instrument resolution**: Downloads NSE instrument master (gzip JSON), builds `trading_symbol` → `instrument_key` (ISIN) map; used for historical candle API (which requires ISIN-based keys).
- **Endpoints used**:  
  - Market quotes: `api.upstox.com` v2 full market quotes.  
  - Historical candles: `api.upstox.com` v3 (ISIN key).  
  - Order place: `api-hft.upstox.com` v3.
- Methods: `get_market_quote`, `get_batch_quotes`, `get_historical_candles`, `place_order`, `is_market_open`, `resolve_instrument_key`, `_ensure_instrument_map`.

### 8. `indicators.py`

- **Input**: List of Upstox candles `[timestamp, open, high, low, close, volume, oi]`.
- **Output**: Dict of indicators (e.g. current_price, SMA/EMA, RSI, MACD, Bollinger, ATR, 52w high/low, scorecard) and a formatted string for the AI prompt.
- Uses `pandas` + `pandas_ta`; `candles_to_dataframe`, `compute_indicators`, `format_indicators_for_prompt`.

### 9. `ai_engine.py`

- **Gemini**: `google.genai` client, model `gemini-2.5-flash`, with Google Search tool for grounded research.
- **Functions**:  
  - `get_ai_stock_analysis(...)`: Full analysis (fundamental, technical, news, macro), returns analysis text, confidence, trade_horizon, key_signals.  
  - `generate_trade_recommendation(...)`: Structured BUY/SELL/HOLD with target, stop-loss, horizon, key_signals; uses technical_data + risk params; quantity computed server-side.  
  - `generate_portfolio_sell_signal(...)`: For a portfolio holding, evaluates whether to SELL (horizon, target/stop, technicals, news).
- Parsing: Regex for confidence, trade_horizon, key_signals from model text; JSON parsing for recommendation payloads; validation and quantity calculation.

---

## Data Stores (MongoDB Collections)

| Collection | Purpose |
|------------|--------|
| `stocks` | Stock universe (symbol, name, sector, prices from refresh). |
| `analysis_history` | Latest AI analysis per stock (symbol, analysis text, confidence, trade_horizon, key_signals, timestamp). |
| `trade_recommendations` | BUY/SELL recommendations (pending → approved/rejected → executed). |
| `portfolio` | Current holdings (symbol, quantity, avg price, current price, P&L, trade_horizon, target/stop, ai_recommendation_id). |
| `trade_history` | Executed trades (symbol, action, quantity, price, order_id, recommendation_id). |
| `settings` | Single doc `id: "main_settings"` (Upstox token, max_trade_value, risk_per_trade_percent, etc.). |

---

## External Dependencies

- **Upstox**: Market data (live token only); orders (sandbox or live by config).  
  - Sandbox: only order APIs are supported; market and historical data require live token.
- **Google Gemini**: Analysis and recommendation generation; requires `GOOGLE_GEMINI_KEY`.
- **MongoDB**: All persistent state; requires `MONGO_URL` and `DB_NAME`.

---

## Security and Configuration

- Secrets and feature flags in `.env` (backend); frontend only needs `REACT_APP_BACKEND_URL` for API base URL.
- No authentication on API in current design (assumed behind VPN or trusted network).
- Upstox tokens: live for market data; sandbox/live for orders to avoid using sandbox for non–sandbox APIs.
