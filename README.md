# Desi Algo Trade — AI Trading Agent for Indian Stocks

AI-powered stock research, trade signals, and execution for NSE, with a conversational agent interface and human-in-the-loop approval. Combines real-time Upstox market data, 20+ technical indicators (pandas-ta), and Google Gemini with search grounding for analysis. Supports live trading, Upstox sandbox paper trading, and a virtual sandbox with automated scheduling.

---

## Features

- **Conversational AI agent**: Chat-first interface powered by Gemini — ask for briefings, discover stocks, run analysis, generate trade signals, approve/reject trades, and check portfolio, all through natural language.
- **Stock universe**: 125 NSE stocks across 19 sectors (IT, Banking, Pharma, Auto, FMCG, Energy, Metal, Infrastructure, Telecom, Consumer) with live price refresh.
- **AI research**: Per-stock analysis (fundamental, technical, news, macro) with Gemini 2.5 Flash and Google Search grounding.
- **20+ technical indicators**: Supertrend, Pivot Points, CPR, Fibonacci, EMA/SMA, RSI, MACD, Bollinger Bands, ATR, OBV, ADX, candlestick patterns, and a weighted signal scorecard.
- **Trade signals**: BUY/SELL/SHORT with target, stop-loss, trade horizon (short/medium/long term), confidence score, and key signal breakdown.
- **Human-in-the-loop**: Pending signals in the trade queue; approve (with optional quantity/price tweaks), edit, or reject. Approved orders executed via Upstox.
- **Mode-aware data**: All portfolio, recommendations, and trade history are scoped to the current Upstox mode — sandbox data stays separate from live data.
- **Live portfolio from Upstox**: In live mode, portfolio holdings, positions, and available funds are fetched directly from your Upstox DEMAT account (not local DB). Pre-trade fund validation prevents orders exceeding available margin.
- **Portfolio**: Holdings with P&L, sector allocation chart, available funds card, AI sell scan, direct sell with quantity control.
- **Sandbox**: Virtual ₹1L paper trading account with CNC/intraday support, automated AI-driven entry/exit, and strategy insights.
- **Scheduler**: Automated daily screener → AI analysis → sandbox execution pipeline with intraday monitoring and square-off.
- **Screener**: Fast technical pre-screen (momentum, volume, Supertrend, Bollinger, pivots) to rank candidates before expensive AI calls.
- **Candle cache**: Incremental MongoDB cache for historical OHLCV data — fetches once, appends daily.
- **Settings**: Risk parameters, Gemini model selection, Upstox connectivity status.

---

## Tech Stack


| Layer    | Stack                                                                                  |
| -------- | -------------------------------------------------------------------------------------- |
| Frontend | React 19, React Router, Tailwind CSS, shadcn/ui, Framer Motion, Recharts, Lucide icons |
| Backend  | FastAPI, Uvicorn (ASGI)                                                                |
| Database | MongoDB (Motor async driver)                                                           |
| AI       | Google Gemini 2.5 Flash (google-genai SDK), Google Search grounding                    |
| Markets  | Upstox API (V2 quotes, V3 historical candles, V3 orders — live and sandbox)            |
| TA       | pandas, pandas-ta                                                                      |


---

## Quick Start

### Prerequisites

- Python 3.10+
- Node 18+ and Yarn
- MongoDB (local or Atlas)
- Upstox API keys and Google Gemini API key

### Backend

```bash
cd backend
# Create .env (see Environment section below)
pip install -r requirements.txt
uvicorn server:app --reload
```

Runs at **[http://localhost:8000](http://localhost:8000)**. API docs: **[http://localhost:8000/docs](http://localhost:8000/docs)**.

### Frontend

```bash
cd frontend
yarn install
# Set backend URL (PowerShell)
$env:REACT_APP_BACKEND_URL = "http://localhost:8000"
yarn start
```

Runs at **[http://localhost:3000](http://localhost:3000)**.

---

## Environment

### Backend (`.env` in `backend/`)


| Variable                      | Purpose                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------ |
| `MONGO_URL`                   | MongoDB connection string (required)                                                 |
| `DB_NAME`                     | Database name (default: `trading_db`)                                                |
| `GOOGLE_GEMINI_KEY`           | Google Gemini API key (for AI analysis and agent)                                    |
| `UPSTOX_USE_SANDBOX`          | `true` = sandbox orders; `false` = live orders                                       |
| `UPSTOX_ACCESS_TOKEN`         | Live Upstox token (used for **market data** always, and for orders when not sandbox) |
| `UPSTOX_SANDBOX_ACCESS_TOKEN` | Sandbox token (used **only for orders** when `UPSTOX_USE_SANDBOX=true`)              |
| `CORS_ORIGINS`                | Comma-separated origins (default: `*`)                                               |


**Note**: Upstox market quotes and historical candles are **not** sandbox-enabled; the app always uses the live access token for market data. Only order placement uses the sandbox token.

### Frontend


| Variable                | Purpose                                                            |
| ----------------------- | ------------------------------------------------------------------ |
| `REACT_APP_BACKEND_URL` | Backend base URL (e.g. `http://localhost:8000`). No `/api` suffix. |


---

## Project Structure

```
desi-algo-trade/
├── backend/
│   ├── server.py              # FastAPI app, startup, shutdown, CORS, routers
│   ├── routes.py              # Core /api endpoints (stocks, AI, recommendations, portfolio, trades)
│   ├── agent_orchestrator.py  # Conversational agent: intent classification, handler dispatch
│   ├── agent_routes.py        # /api/agent endpoints (sessions, messages)
│   ├── prompts.py             # Centralized Gemini prompt templates
│   ├── ai_engine.py           # Gemini calls, model fallback, response parsing
│   ├── trading.py             # UpstoxClient (quotes, candles, orders)
│   ├── indicators.py          # 20+ technical indicators and signal scorecard
│   ├── candle_cache.py        # MongoDB cache for historical candle data
│   ├── screener.py            # Fast technical pre-screen for stock ranking
│   ├── sandbox.py             # Virtual paper trading engine
│   ├── sandbox_routes.py      # /api/sandbox endpoints (screener, sandbox, scheduler)
│   ├── scheduler.py           # Automated daily scan and intraday monitoring
│   ├── models.py              # Pydantic models and enums
│   ├── database.py            # MongoDB connection
│   ├── stock_data.py          # Static stock universe data
│   └── stock_init.py          # DB initialization of stocks
├── frontend/
│   ├── src/
│   │   ├── App.js             # Router, sidebar, navigation
│   │   ├── pages/
│   │   │   ├── AgentChat.jsx  # Conversational AI agent (home page)
│   │   │   ├── AIResearch.jsx # Stock browser + AI analysis (Research)
│   │   │   ├── TradeQueue.jsx # Pending signals + rec history + executed trades (Trades)
│   │   │   ├── Portfolio.jsx  # Holdings, P&L, sector chart, sell (Portfolio)
│   │   │   ├── Sandbox.jsx    # Virtual paper trading dashboard
│   │   │   └── Settings.jsx   # Risk params, Gemini model, Upstox status
│   │   └── components/ui/     # shadcn-style UI components
│   └── public/
├── docs/
│   ├── ARCHITECTURE.md        # Technical architecture
│   └── PROCESS_FLOWS.md       # End-to-end process flows
├── memory/
│   └── PRD.md                 # Product requirements
└── README.md                  # This file
```

---

## Frontend Routes


| Path         | Page      | Description                                                                |
| ------------ | --------- | -------------------------------------------------------------------------- |
| `/`          | Agent     | Conversational AI agent — the primary interface                            |
| `/research`  | Research  | Stock browser with live prices, sector filter, and AI analysis panel       |
| `/trades`    | Trades    | Pending BUY/SHORT/SELL signals, recommendation history, executed trade log |
| `/portfolio` | Portfolio | Mode-scoped holdings, P&L, sector allocation, AI sell scan                 |
| `/sandbox`   | Sandbox   | Virtual paper trading account with automated strategy                      |
| `/settings`  | Settings  | Risk parameters, Gemini model, Upstox connectivity                         |


---

## Main API Endpoints

### Core (`/api`)


| Group           | Endpoints                                                                                                         |
| --------------- | ----------------------------------------------------------------------------------------------------------------- |
| Health          | `GET /`, `GET /health`                                                                                            |
| Stocks          | `GET /stocks`, `POST /stocks/refresh`, `POST /stocks/initialize`, `GET /stocks/sectors`                           |
| Market          | `GET /market/status`                                                                                              |
| AI              | `POST /ai/analyze`, `GET /ai/analysis/latest/{symbol}`, `POST /ai/scan-all`                                       |
| Recommendations | `GET /recommendations`, `GET /recommendations/pending`, `POST /recommendations/{id}/approve`                      |
| Portfolio       | `GET /portfolio`, `GET /funds`, `POST /portfolio/refresh-prices`, `POST /portfolio/scan-sells`, `POST /portfolio/{symbol}/sell` |
| Trades          | `GET /trades/history`, `GET /trades/stats`                                                                        |
| Settings        | `GET /settings`, `POST /settings`, `GET /settings/upstox-status`, `GET/POST /settings/model`                      |
| Dashboard       | `GET /dashboard/stats`                                                                                            |


### Agent (`/api/agent`)


| Endpoint            | Description                                               |
| ------------------- | --------------------------------------------------------- |
| `POST /send`        | Send a message to the AI agent; returns structured blocks |
| `GET /session`      | Get or create today's session                             |
| `GET /sessions`     | List recent sessions                                      |
| `POST /session/new` | Start a new session                                       |
| `GET /status`       | Agent status (model, mode, market)                        |


### Sandbox (`/api/sandbox`)


| Endpoint                                          | Description                          |
| ------------------------------------------------- | ------------------------------------ |
| `POST /screener/run`                              | Run technical screener on all stocks |
| `GET /screener/latest`                            | Get latest screener results          |
| `GET /account`                                    | Virtual account summary              |
| `GET /holdings`                                   | Current sandbox holdings             |
| `GET /trades`                                     | Completed sandbox trades             |
| `POST /scheduler/start`, `POST /scheduler/stop`   | Control automated scheduler          |
| `GET /scheduler/config`, `POST /scheduler/config` | Scheduler configuration              |


---

## Trade Modes

Every trade, recommendation, and portfolio entry carries a `trade_mode` field:


| Mode          | Meaning                                                   |
| ------------- | --------------------------------------------------------- |
| **live**      | Real order placed on Upstox via live credentials          |
| **sandbox**   | Orders placed via Upstox sandbox API                      |
| **simulated** | Paper trade via separate API - Upstox used only for price |


All data endpoints (portfolio, recommendations, trade history, dashboard stats) are **mode-scoped** — when running in sandbox mode, only sandbox data is shown; when in live mode, only live data is shown. The current mode is determined by `UPSTOX_USE_SANDBOX` in `.env`.

**Live mode specifics**: In live mode, portfolio data (holdings, positions, funds) is fetched directly from Upstox APIs rather than the local MongoDB. Pre-trade fund validation checks available margin before placing orders. Sandbox mode continues to use the local DB for its virtual portfolio.

---

## License and Disclaimer

This project is for educational and personal use. Trading in securities involves risk. Ensure you comply with Upstox and exchange terms and local regulations before using for live trading.