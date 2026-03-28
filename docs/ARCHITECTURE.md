# Technical Architecture

## Overview

**Desi Algo Trade** is an AI-powered stock analysis and trading application for Indian markets (NSE). It combines a conversational AI agent, real-time and historical market data, 20+ technical indicators, and Google Gemini LLM to produce trade recommendations with a human-in-the-loop approval workflow. Supports live trading, Upstox sandbox, and virtual paper trading with automated scheduling.

---

## High-Level Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 19, React Router, Axios, Tailwind CSS, shadcn/ui, Framer Motion, Recharts, Lucide icons, Sonner (toast) |
| **Backend** | FastAPI, Uvicorn (ASGI) |
| **Database** | MongoDB (Motor async driver) |
| **AI** | Google Gemini 2.5 Flash (google-genai SDK), Google Search grounding |
| **Market / Orders** | Upstox API (V2 market quotes, V3 historical candles, V3 order placement — live and sandbox) |
| **Technical Analysis** | pandas, pandas-ta |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                        │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐ ┌─────────┐ │
│  │  Agent   │ │ Research │ │ Trades │ │Portfolio│ │ Sandbox │ │
│  │  Chat    │ │          │ │        │ │         │ │         │ │
│  └────┬─────┘ └────┬─────┘ └───┬────┘ └────┬────┘ └────┬────┘ │
└───────┼────────────┼───────────┼───────────┼───────────┼───────┘
        │            │           │           │           │
        ▼            ▼           ▼           ▼           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                          │
│                                                                 │
│  ┌─────────────┐  ┌──────────┐  ┌──────────────┐              │
│  │ Agent       │  │ Core     │  │ Sandbox      │              │
│  │ Routes      │  │ Routes   │  │ Routes       │              │
│  └──────┬──────┘  └────┬─────┘  └──────┬───────┘              │
│         │              │               │                       │
│  ┌──────▼──────┐       │        ┌──────▼───────┐              │
│  │ Agent       │       │        │  Scheduler   │              │
│  │ Orchestrator│       │        │  Screener    │              │
│  └──────┬──────┘       │        │  Sandbox     │              │
│         │              │        └──────┬───────┘              │
│         ▼              ▼               ▼                       │
│  ┌─────────────────────────────────────────────────┐           │
│  │          Shared Services Layer                   │           │
│  │  AI Engine │ Trading │ Indicators │ Candle Cache│           │
│  └──────────────────────┬──────────────────────────┘           │
└─────────────────────────┼──────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ MongoDB  │   │  Gemini  │   │  Upstox  │
    │          │   │  (AI)    │   │  (Market) │
    └──────────┘   └──────────┘   └──────────┘
```

---

## Repository Structure

```
desi-algo-trade/
├── backend/
│   ├── server.py              # FastAPI app, startup/shutdown, CORS, router mounts
│   ├── routes.py              # Core /api endpoints (mode-scoped)
│   ├── agent_orchestrator.py  # Conversational agent: intent → handler → response blocks
│   ├── agent_routes.py        # /api/agent endpoints (sessions, messages)
│   ├── prompts.py             # Centralized Gemini prompt templates
│   ├── ai_engine.py           # Gemini calls, model fallback, response parsing
│   ├── trading.py             # UpstoxClient (quotes, candles, orders)
│   ├── indicators.py          # 20+ technical indicators and signal scorecard
│   ├── candle_cache.py        # Incremental MongoDB cache for OHLCV data
│   ├── screener.py            # Fast technical pre-screen for stock ranking
│   ├── sandbox.py             # Virtual paper trading engine
│   ├── sandbox_routes.py      # /api/sandbox endpoints
│   ├── scheduler.py           # Automated daily scan and intraday monitoring
│   ├── models.py              # Pydantic models and enums
│   ├── database.py            # MongoDB connection
│   ├── stock_data.py          # Static stock universe data
│   ├── stock_init.py          # DB initialization
│   ├── requirements.txt
│   └── .env                   # Secrets and config (not committed)
├── frontend/
│   ├── src/
│   │   ├── App.js             # Router, sidebar, navigation
│   │   ├── pages/
│   │   │   ├── AgentChat.jsx  # Conversational AI agent (home page)
│   │   │   ├── AIResearch.jsx # Stock browser + AI analysis
│   │   │   ├── TradeQueue.jsx # Pending signals + history + executed trades
│   │   │   ├── Portfolio.jsx  # Holdings, P&L, sector chart, sell
│   │   │   ├── Sandbox.jsx    # Virtual paper trading dashboard
│   │   │   └── Settings.jsx   # Risk params, model, Upstox status
│   │   └── components/ui/     # shadcn-style UI primitives
│   ├── public/
│   └── package.json
├── docs/
│   ├── ARCHITECTURE.md        # This file
│   └── PROCESS_FLOWS.md       # End-to-end process flows
├── memory/
│   └── PRD.md                 # Product requirements
└── README.md
```

---

## Backend Modules

### 1. `server.py`

- Creates FastAPI app, mounts three routers: `api_router` (`/api`), `agent_router` (`/api/agent`), `sandbox_router` (`/api/sandbox`).
- **Startup**: Initialize stock universe if empty, restore preferred Gemini model from DB, auto-start sandbox scheduler.
- **Shutdown**: Stop scheduler, close MongoDB.
- CORS configurable via `CORS_ORIGINS`.

### 2. `routes.py`

- Single `APIRouter` at `/api`; all core endpoints live here.
- **Mode-scoped**: A `_current_trade_mode()` helper returns `"sandbox"` or `"live"` based on `UpstoxClient.sandbox`. All query endpoints (portfolio, recommendations, trade history, stats) filter by this mode. New recommendations are tagged with the current mode at creation.
- **Live portfolio sourcing**: In live mode, `GET /portfolio`, `GET /portfolio/sector-breakdown`, and `GET /dashboard/stats` fetch real holdings and positions from Upstox APIs via `_get_upstox_portfolio()` — no local DB reads. In sandbox mode, local MongoDB is used as before.
- **Funds**: `GET /funds` returns available margin from Upstox in live mode, or virtual capital in sandbox mode.
- **Pre-trade fund validation**: When approving a trade in live mode, the system checks Upstox available margin and rejects the order if insufficient.
- **Portfolio-aware analysis**: `POST /ai/analyze` checks Upstox holdings in live mode to determine ENTRY vs EXIT analysis (sandbox uses local DB).
- **Helpers**: `_get_technical_data(symbol)` (candle cache + live LTP patch + indicators), `_get_risk_settings()`.
- **Groups**: Root/health, stocks, market, AI (analyze, scan-all), recommendations (list, approve), portfolio (holdings, funds, refresh, scan-sells, sell), trades (history, stats), settings, dashboard.
- `update_portfolio()` is mode-aware: queries match on both `stock_symbol` and `trade_mode`, allowing the same stock in both sandbox and live portfolios.

### 3. `agent_orchestrator.py`

- The conversational agent brain. Takes user messages, classifies intent using Gemini, routes to the appropriate handler.
- **Intent handlers**: `briefing` (morning market overview), `discover` (sector/theme stock discovery), `analyze` (deep AI analysis of a stock), `signal` (generate trade signal), `approve`/`reject` (trade approval from chat), `portfolio` (portfolio summary), `sell_scan` (AI sell scan), `question` (general market Q&A).
- Returns structured `MessageBlock` arrays: text, stock cards, analysis, trade signals, suggested prompts.
- All portfolio queries and recommendation creation are mode-scoped.

### 4. `agent_routes.py`

- `/api/agent` router with session management.
- Sessions are date-scoped (one per day by default) and persisted to `agent_sessions` collection.
- Endpoints: send message, get/create session, list sessions, agent status.

### 5. `prompts.py`

- Centralized prompt catalog for all Gemini interactions.
- Templates: system prompt, intent classifier, briefing, analysis, trade signal, sell signal, discovery, general question.
- Keeps `ai_engine.py` and `agent_orchestrator.py` logic-focused by externalizing prompt text.

### 6. `ai_engine.py`

- Gemini client using `google.genai` SDK with model fallback (rate limit → next model in priority).
- **Functions**: `get_ai_stock_analysis()`, `generate_trade_recommendation()`, `generate_portfolio_sell_signal()`.
- Model management: configurable preferred model, cooldown tracking, available model list.
- Parsing: Regex extraction of confidence, trade_horizon, key_signals; JSON parsing for structured payloads; server-side quantity calculation and validation.

### 7. `trading.py` (UpstoxClient)

- **Credentials**: Live token for all market data; sandbox/live token for orders based on `UPSTOX_USE_SANDBOX`.
- **Instrument resolution**: Downloads NSE instrument master (gzip JSON), builds `trading_symbol` → `instrument_key` (ISIN) map with override support.
- **Market data**: V2 market quotes (single + batch), V3 historical candles (ISIN key), V3 order placement.
- **Account/Portfolio**: `get_funds_and_margin()` (equity segment available margin), `get_holdings()` (DEMAT long-term holdings), `get_positions()` (intraday positions). All use the live Upstox token. Used in live mode to source real portfolio data instead of local DB.
- **Trade mode**: `place_order()` returns `trade_mode` ("live", "sandbox", or "simulated" on failure/no token).

### 8. `indicators.py`

- Converts Upstox OHLCV candles to pandas DataFrame, computes 20+ indicators:
  - **Trend**: Supertrend, EMA (9/21/50/200), SMA (50/200), ADX
  - **Momentum**: RSI, MACD (histogram, signal), Stochastic
  - **Volatility**: Bollinger Bands, ATR, 52-week high/low
  - **Volume**: OBV, volume vs 20-day average
  - **Support/Resistance**: Pivot Points (Classic), CPR (Central Pivot Range), Fibonacci retracement
  - **Patterns**: Candlestick pattern detection
- **Signal scorecard**: Weighted composite score from multiple indicator signals (trend, momentum, volume, volatility, S/R).
- Two formatters: `format_indicators_for_prompt()` (human-readable for AI) and `format_technical_numbers_for_ai()` (compact numerical).

### 9. `candle_cache.py`

- Incremental MongoDB cache for historical candles.
- First call: fetches ~1 year of daily candles from Upstox, stores in `candle_cache` collection.
- Subsequent calls: only appends candles newer than `last_candle_date`.
- Deduplication and old-candle trimming built in.

### 10. `screener.py`

- Fast technical pre-screen to rank the stock universe before expensive AI calls.
- Scoring: momentum trend, volume surge, Supertrend alignment, Bollinger position, pivot/Fibonacci proximity.
- `screen_all_stocks()`: Concurrent screening with configurable concurrency limit; results stored in `screener_results`.

### 11. `sandbox.py`

- Virtual paper trading engine with ₹1L starting capital.
- Four trade types: CNC long (delivery), CNC short, intraday long, intraday short.
- `execute_sandbox_entry()` / `execute_sandbox_exit()`: Manage positions and P&L.
- `squareoff_intraday_positions()`: Auto-close at 15:15 IST.
- `get_strategy_insights()`: Win rate, average P&L, best/worst trades.

### 12. `sandbox_routes.py`

- Unified `/api/sandbox` router for screener, sandbox, and scheduler.
- Screener endpoints: run, get latest.
- Sandbox endpoints: account, holdings, trades, strategy, price refresh, exit check, reset.
- Scheduler endpoints: start, stop, config, manual scan, logs.

### 13. `scheduler.py`

- Automated daily pipeline running as asyncio background tasks.
- **Daily scan** (09:20 IST): Run screener → filter top-N → deep AI analysis → classify trade type → sandbox auto-execute.
- **Intraday monitor** (~60s loop): Check for exit signals on open positions.
- **Square-off** (15:15 IST): Auto-close all intraday positions.
- Configurable via `SchedulerConfig` (scan time, max positions, min screener score, etc.).

### 14. `models.py`

- **Enums**: Sector, TradeAction, TradeStatus, AnalysisType, TradeMode, TradeHorizon, MessageBlockType.
- **Core models**: Stock, TradeRecommendation, TradeApproval, Portfolio, TradeHistory, Settings.
- **Sandbox models**: SandboxAccount, SandboxHolding, SandboxTrade, SchedulerConfig.
- **Agent models**: MessageBlock, AgentMessage, AgentSession.

---

## Data Stores (MongoDB Collections)

| Collection | Purpose |
|------------|---------|
| `stocks` | Stock universe (symbol, name, sector, prices). |
| `analysis_history` | AI analysis records per stock. |
| `trade_recommendations` | BUY/SELL/SHORT signals (pending → executed/rejected). Mode-scoped. |
| `portfolio` | Current holdings (symbol, quantity, avg price, P&L). Mode-scoped. |
| `trade_history` | Executed trades (symbol, action, price, order_id). Mode-scoped. |
| `settings` | Single doc — risk params, preferred model. |
| `agent_sessions` | Conversational agent chat sessions. |
| `candle_cache` | Cached historical OHLCV candles per symbol. |
| `screener_results` | Latest technical screener scores. |
| `scheduler_config` | Scheduler settings. |
| `sandbox_account` | Virtual trading account state. |
| `sandbox_holdings` | Open sandbox positions. |
| `sandbox_trades` | Completed sandbox trades. |

---

## Frontend Pages

| Page | Component | Description |
|------|-----------|-------------|
| Agent | `AgentChat.jsx` | Conversational AI agent — the home page. Rich message blocks (text, stock cards, analysis, trade signals, suggested prompts). Session persistence. |
| Research | `AIResearch.jsx` | Stock browser with live prices and sector filter. AI analysis panel with confidence, signals, and trade horizon. Scan-all-stocks action. |
| Trades | `TradeQueue.jsx` | Three pending tabs (BUY/SHORT/SELL) with approve/edit/reject. Rec History tab. Executed trade log tab with stats bar. Mode badge. |
| Portfolio | `Portfolio.jsx` | Holdings grid with P&L, target/stop-loss, days held, available funds card. Live mode reads from Upstox DEMAT; sandbox from local DB. Sector allocation pie chart. AI sell scan. Direct sell. Mode badge. |
| Sandbox | `Sandbox.jsx` | Virtual paper trading — account overview, holdings, completed trades, strategy insights, scheduler controls. |
| Settings | `Settings.jsx` | Risk parameters, Gemini model selector, Upstox connectivity status with token validation. |

---

## Mode-Aware Architecture

All core data is scoped by the current Upstox mode (`UPSTOX_USE_SANDBOX` env var):

```
UPSTOX_USE_SANDBOX=true  → trade_mode = "sandbox"
UPSTOX_USE_SANDBOX=false → trade_mode = "live"
```

- **Creation**: Every new `TradeRecommendation`, `TradeHistory`, and `Portfolio` entry is tagged with the current mode.
- **Queries**: All read endpoints (GET portfolio, recommendations, trades, stats) filter by `trade_mode`.
- **Live mode data sourcing**: In live mode, portfolio and holdings data is fetched directly from Upstox APIs (`get_holdings()`, `get_positions()`, `get_funds_and_margin()`) instead of the local MongoDB `portfolio` collection. This ensures the UI always reflects the real DEMAT account. Sandbox mode continues to use local MongoDB.
- **Pre-trade validation**: In live mode, trade approval checks Upstox available margin before placing orders, rejecting if insufficient funds.
- **Isolation**: The same stock can exist independently in both sandbox and live portfolios.
- **UI**: Portfolio and Trades pages show a LIVE/SANDBOX badge. Portfolio page includes an Available Funds card sourced from Upstox (live) or virtual capital (sandbox).

---

## External Dependencies

- **Upstox**: Market data (live token only); orders (sandbox or live by config); portfolio/funds (live token, live mode only). Sandbox only supports order APIs, not market data or portfolio APIs.
- **Google Gemini**: AI analysis, recommendations, intent classification, conversational responses. Requires `GOOGLE_GEMINI_KEY`.
- **MongoDB**: All persistent state. Requires `MONGO_URL`.

---

## Security and Configuration

- Secrets in `.env` (backend); frontend only needs `REACT_APP_BACKEND_URL`.
- No authentication on API (assumed behind VPN or trusted network).
- Upstox tokens managed via `.env` — never stored in database. Settings page shows masked connectivity status.
- Gemini model configurable at runtime via Settings or API.
