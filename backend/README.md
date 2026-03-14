# Backend — AlgoTrade API

FastAPI application providing stock universe, AI analysis, trade recommendations, portfolio, and order execution via Upstox.

---

## Run

```bash
cd backend
pip install -r requirements.txt
# Configure .env (see below)
uvicorn server:app --reload
```

- **Base URL**: http://localhost:8000  
- **API prefix**: `/api` (e.g. http://localhost:8000/api/health)  
- **Docs**: http://localhost:8000/docs (Swagger)

---

## Environment (`.env`)

Create a `.env` file in the `backend/` directory. Do not commit secrets.

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_URL` | Yes | MongoDB connection string (e.g. `mongodb+srv://...` or `mongodb://localhost:27017`) |
| `DB_NAME` | No | Database name (default: `trading_db`) |
| `GOOGLE_GEMINI_KEY` | For AI | Google Gemini API key |
| `UPSTOX_USE_SANDBOX` | No | `true` = use sandbox for **orders**; `false` = live orders (default: `true`) |
| `UPSTOX_API_KEY` | For live | Live Upstox API key |
| `UPSTOX_API_SECRET` | For live | Live Upstox API secret |
| `UPSTOX_ACCESS_TOKEN` | For market data | Live Upstox access token (used for **all market data** and for orders when not sandbox) |
| `UPSTOX_SANDBOX_API_KEY` | For sandbox | Sandbox API key |
| `UPSTOX_SANDBOX_API_SECRET` | For sandbox | Sandbox API secret |
| `UPSTOX_SANDBOX_ACCESS_TOKEN` | For sandbox | Sandbox access token (used **only for order** APIs when `UPSTOX_USE_SANDBOX=true`) |
| `CORS_ORIGINS` | No | Comma-separated origins (default: `*`) |

**Upstox behaviour**

- **Market quotes** and **historical candle** APIs are **not** sandbox-enabled. The backend always uses `UPSTOX_ACCESS_TOKEN` for these.
- **Order** APIs (place/modify/cancel) support sandbox; when `UPSTOX_USE_SANDBOX=true`, the backend uses the sandbox token for orders only.

---

## MongoDB Collections

| Collection | Description |
|------------|-------------|
| `stocks` | Stock universe (symbol, name, sector, current_price, etc.). Initialized from `stock_data.STOCK_UNIVERSE`. |
| `analysis_history` | Latest AI analysis per stock (symbol, analysis text, confidence, trade_horizon, key_signals). |
| `trade_recommendations` | BUY/SELL recommendations (status: pending → approved/rejected → executed). |
| `portfolio` | Current holdings (symbol, quantity, avg price, P&L, trade_horizon, target/stop). |
| `trade_history` | Executed trades (symbol, action, quantity, price, order_id). |
| `settings` | Single document `id: "main_settings"` (tokens, max_trade_value, risk_per_trade_percent). |

---

## Key Modules

| File | Role |
|------|------|
| `server.py` | FastAPI app, startup (stock init), shutdown (DB close), CORS, router mount. |
| `routes.py` | All `/api` endpoints and helpers (`_get_technical_data`, `_get_risk_settings`, `update_portfolio`). |
| `database.py` | MongoDB client and `db` instance. |
| `models.py` | Pydantic models and enums. |
| `stock_data.py` | Static `STOCK_UNIVERSE` list. |
| `stock_init.py` | `initialize_stocks()`, `get_stock_count()`. |
| `trading.py` | `UpstoxClient`: quotes, historical candles (ISIN resolution), place order. |
| `indicators.py` | OHLCV → technical indicators (pandas-ta) and prompt formatting. |
| `ai_engine.py` | Gemini analysis, trade recommendation generation, portfolio sell signals. |

---

## API Overview

- **Root / health**: `GET /api/`, `GET /api/health`  
- **Stocks**: `GET /api/stocks`, `GET /api/stocks/sector/{sector}`, `GET /api/stocks/sectors`, `POST /api/stocks/initialize`, `GET /api/stocks/{symbol}`, `POST /api/stocks/refresh`  
- **Market**: `GET /api/market/status`, `GET /api/market/debug-quote/{symbol}`  
- **AI**: `POST /api/ai/analyze`, `GET /api/ai/analysis/latest`, `GET /api/ai/analysis/latest/{symbol}`, `POST /api/ai/generate-recommendation/{symbol}`, `POST /api/ai/scan-all`  
- **Recommendations**: `GET /api/recommendations`, `GET /api/recommendations/pending`, `POST /api/recommendations/{id}/approve`  
- **Portfolio**: `GET /api/portfolio`, `GET /api/portfolio/sector-breakdown`, `POST /api/portfolio/refresh-prices`, `POST /api/portfolio/scan-sells`  
- **Trades**: `GET /api/trades/history`, `GET /api/trades/stats`  
- **Settings**: `GET /api/settings`, `POST /api/settings`  
- **Dashboard**: `GET /api/dashboard/stats`  

Full request/response details: run the server and open http://localhost:8000/docs.
