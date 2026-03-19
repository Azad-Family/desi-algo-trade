# Backend — Desi Algo Trade API

FastAPI application providing a conversational AI agent, stock universe, AI analysis, trade recommendations, portfolio management, sandbox paper trading, automated scheduling, and order execution via Upstox.

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
| `MONGO_URL` | Yes | MongoDB connection string |
| `DB_NAME` | No | Database name (default: `trading_db`) |
| `GOOGLE_GEMINI_KEY` | For AI | Google Gemini API key |
| `UPSTOX_USE_SANDBOX` | No | `true` = sandbox orders; `false` = live orders (default: `true`) |
| `UPSTOX_ACCESS_TOKEN` | For market data | Live Upstox token (used for **all market data** and for orders when not sandbox) |
| `UPSTOX_SANDBOX_ACCESS_TOKEN` | For sandbox | Sandbox token (used **only for orders** when `UPSTOX_USE_SANDBOX=true`) |
| `CORS_ORIGINS` | No | Comma-separated origins (default: `*`) |

**Upstox behaviour**:
- **Market quotes** and **historical candle** APIs are not sandbox-enabled. The backend always uses `UPSTOX_ACCESS_TOKEN` for these.
- **Order** APIs support sandbox; when `UPSTOX_USE_SANDBOX=true`, the backend uses the sandbox token for orders only.

---

## MongoDB Collections

| Collection | Description |
|------------|-------------|
| `stocks` | Stock universe (symbol, name, sector, current_price, change_percent). |
| `analysis_history` | AI analysis records (symbol, analysis text, confidence, trade_horizon, key_signals). |
| `trade_recommendations` | BUY/SELL/SHORT signals (status: pending → approved/rejected → executed). Scoped by `trade_mode`. |
| `portfolio` | Current holdings (symbol, quantity, avg price, P&L, trade_horizon, target/stop). Scoped by `trade_mode`. |
| `trade_history` | Executed trades (symbol, action, quantity, price, order_id). Scoped by `trade_mode`. |
| `settings` | Single document `id: "main_settings"` (max_trade_value, risk_per_trade_percent, gemini_model). |
| `agent_sessions` | Chat sessions for the conversational agent (messages, context). |
| `candle_cache` | Incremental cache of historical OHLCV candles per symbol. |
| `screener_results` | Latest technical screener scores and rankings. |
| `scheduler_config` | Scheduler settings (enabled, scan_time, max_positions, etc.). |
| `sandbox_account` | Virtual paper trading account state (capital, P&L stats). |
| `sandbox_holdings` | Current sandbox positions. |
| `sandbox_trades` | Completed sandbox trade records. |

---

## Key Modules

| File | Role |
|------|------|
| `server.py` | FastAPI app entry; startup (stock init, model restore, scheduler auto-start), shutdown, CORS, router mounts. |
| `routes.py` | Core `/api` endpoints — stocks, AI analysis, recommendations, portfolio, trades, settings, dashboard. All query endpoints are **mode-scoped** (sandbox/live). |
| `agent_orchestrator.py` | Conversational AI agent brain — intent classification with Gemini, handler dispatch (briefing, discover, analyze, signal, approve, portfolio, question). |
| `agent_routes.py` | `/api/agent` endpoints — session management, message send/receive. |
| `prompts.py` | Centralized Gemini prompt templates (system prompt, intent classifier, analysis, trade signal, sell signal, discovery, question). |
| `ai_engine.py` | Gemini API calls with model fallback on rate limits, response parsing (confidence, trade_horizon, key_signals, JSON payloads). |
| `trading.py` | `UpstoxClient` — market quotes, batch quotes, historical candles (ISIN resolution), order placement (live/sandbox). |
| `indicators.py` | 20+ technical indicators from OHLCV: Supertrend, Pivot Points, CPR, Fibonacci, EMA/SMA, RSI, MACD, Bollinger, ATR, OBV, ADX, candlestick patterns, weighted signal scorecard. |
| `candle_cache.py` | Incremental MongoDB cache for historical candles — fetches ~1 year on first call, then appends new candles daily. |
| `screener.py` | Fast technical pre-screen: momentum, volume, Supertrend, Bollinger, pivots/Fibonacci scoring to rank stocks before AI analysis. |
| `sandbox.py` | Virtual paper trading engine — ₹1L virtual capital, CNC/intraday support, automated entry/exit, P&L tracking, strategy insights. |
| `sandbox_routes.py` | `/api/sandbox` endpoints — screener, sandbox account/holdings/trades, scheduler control. |
| `scheduler.py` | Automated daily pipeline — pre-market screener → AI analysis → sandbox execution → intraday monitoring → square-off at 15:15 IST. |
| `database.py` | MongoDB client (`AsyncIOMotorClient`) and `db` instance. |
| `models.py` | Pydantic models: Stock, TradeRecommendation, Portfolio, TradeHistory, Settings, SandboxAccount, SandboxHolding, SandboxTrade, SchedulerConfig, AgentSession, MessageBlock, etc. |
| `stock_data.py` | Static `STOCK_UNIVERSE` list (59 stocks, 10 sectors). |
| `stock_init.py` | `initialize_stocks()` — clear and reload stock universe into DB. |

---

## API Overview

### Core (`/api`)

- **Root / health**: `GET /`, `GET /health`
- **Stocks**: `GET /stocks`, `GET /stocks/sector/{sector}`, `GET /stocks/sectors`, `POST /stocks/initialize`, `GET /stocks/{symbol}`, `POST /stocks/refresh`
- **Market**: `GET /market/status`
- **AI**: `POST /ai/analyze`, `GET /ai/analysis/latest`, `GET /ai/analysis/latest/{symbol}`, `GET /ai/analysis/history`, `POST /ai/generate-recommendation/{symbol}`, `POST /ai/scan-all`
- **Recommendations**: `GET /recommendations`, `GET /recommendations/pending`, `POST /recommendations/{id}/approve`
- **Portfolio**: `GET /portfolio`, `GET /portfolio/sector-breakdown`, `POST /portfolio/refresh-prices`, `POST /portfolio/scan-sells`, `POST /portfolio/{symbol}/sell`
- **Trades**: `GET /trades/history`, `GET /trades/stats`
- **Settings**: `GET /settings`, `POST /settings`, `GET /settings/models`, `POST /settings/model`, `GET /settings/upstox-status`
- **Dashboard**: `GET /dashboard/stats`
- **Debug**: `GET /debug/upstox-config`, `GET /debug/ai-config`, `GET /market/debug-quote/{symbol}`

### Agent (`/api/agent`)

- `POST /send` — Send user message, returns structured response blocks
- `GET /session` — Get or create today's session
- `GET /sessions` — List recent sessions
- `POST /session/new` — Start a new session
- `GET /status` — Agent status (model, mode, market)

### Sandbox (`/api/sandbox`)

- **Screener**: `POST /screener/run`, `GET /screener/latest`
- **Account**: `GET /account`, `POST /account/reset`
- **Holdings**: `GET /holdings`
- **Trades**: `GET /trades`
- **Strategy**: `GET /strategy`
- **Prices**: `POST /refresh-prices`, `POST /check-exits`
- **Scheduler**: `POST /scheduler/start`, `POST /scheduler/stop`, `GET /scheduler/config`, `POST /scheduler/config`, `POST /scheduler/scan-now`, `GET /scheduler/logs`

## Mode-Aware Filtering

All core data endpoints (portfolio, recommendations, trade history, trade stats, dashboard stats) are filtered by the current Upstox mode:

- **Sandbox mode** (`UPSTOX_USE_SANDBOX=true`): Only entries with `trade_mode: "sandbox"` are returned.
- **Live mode** (`UPSTOX_USE_SANDBOX=false`): Only entries with `trade_mode: "live"` are returned.

New recommendations are tagged with the current mode at creation time. The same stock can exist independently in both sandbox and live portfolios.

Full request/response details: run the server and open http://localhost:8000/docs.
