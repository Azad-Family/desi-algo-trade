# AlgoTrade — AI Trading Agent for Indian Stocks

AI-powered stock research and trade recommendations for NSE/BSE, with human-in-the-loop approval. Uses real-time and historical Upstox data, technical indicators (pandas-ta), and Google Gemini with search grounding for analysis and signals.

---

## Features

- **Stock universe**: 59 NSE stocks across 10 sectors (IT, Banking, Pharma, Auto, FMCG, Energy, Metal, Infrastructure, Telecom, Consumer).
- **AI research**: Per-stock analysis (fundamental, technical, news, macro) with Gemini 2.5 Flash and Google Search grounding.
- **Trade recommendations**: BUY/SELL/HOLD with target, stop-loss, trade horizon (short/medium/long term), and key signals.
- **Trade queue**: Pending recommendations; approve (with optional quantity/price tweaks) or reject. Approved BUY/SELL executed via Upstox (live or sandbox).
- **Portfolio**: Holdings with P&L; refresh prices; scan for AI-generated sell signals based on horizon and technicals.
- **Trade history**: Log of executed trades.
- **Settings**: Upstox tokens, max trade value, risk per trade; sandbox vs live orders.

---

## Tech Stack

| Layer     | Stack |
|----------|--------|
| Frontend | React 19, React Router, Tailwind, shadcn/ui |
| Backend  | FastAPI, Uvicorn |
| Database | MongoDB (Motor async) |
| AI       | Google Gemini 2.5 Flash (google-genai), Google Search |
| Markets  | Upstox (V2 quotes, V3 historical candles, V3 orders) |
| TA       | pandas, pandas-ta |

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node 18+ and Yarn
- MongoDB (local or Atlas)
- Upstox and Google Gemini API keys

### Backend

```bash
cd backend
# Create .env (see backend/README.md or Environment below)
pip install -r requirements.txt
uvicorn server:app --reload
```

Runs at **http://localhost:8000**. API base: **http://localhost:8000/api**.

### Frontend

```bash
cd frontend
yarn install
# Set backend URL (PowerShell)
$env:REACT_APP_BACKEND_URL = "http://localhost:8000"
yarn start
```

Runs at **http://localhost:3000**.

---

## Environment

### Backend (`.env` in `backend/`)

| Variable | Purpose |
|----------|--------|
| `MONGO_URL` | MongoDB connection string (required) |
| `DB_NAME` | Database name (default: `trading_db`) |
| `GOOGLE_GEMINI_KEY` | Google Gemini API key (for AI analysis) |
| `UPSTOX_USE_SANDBOX` | `true` = sandbox orders; `false` = live orders |
| `UPSTOX_API_KEY` / `UPSTOX_API_SECRET` / `UPSTOX_ACCESS_TOKEN` | Live Upstox (used for **market data** and, when not sandbox, orders) |
| `UPSTOX_SANDBOX_API_KEY` / `UPSTOX_SANDBOX_API_SECRET` / `UPSTOX_SANDBOX_ACCESS_TOKEN` | Sandbox (used **only for order** APIs when `UPSTOX_USE_SANDBOX=true`) |
| `CORS_ORIGINS` | Comma-separated origins (default: `*`) |

**Note**: Upstox market quotes and historical candles are **not** sandbox-enabled; the app always uses the **live** access token for market data. Only order placement uses sandbox when `UPSTOX_USE_SANDBOX=true`.

### Frontend

| Variable | Purpose |
|----------|--------|
| `REACT_APP_BACKEND_URL` | Backend base URL (e.g. `http://localhost:8000`). No `/api` suffix. |

---

## Project Structure

```
desi-algo-trade/
├── backend/          # FastAPI app, routes, AI, trading, indicators
├── frontend/         # React app and UI
├── docs/
│   ├── ARCHITECTURE.md   # Technical architecture
│   └── PROCESS_FLOWS.md  # End-to-end process flows
├── memory/           # PRD and product notes
└── README.md         # This file
```

See **docs/ARCHITECTURE.md** for module and API details, and **docs/PROCESS_FLOWS.md** for analysis, scan-all, approval, and portfolio flows.

---

## Main API Endpoints (prefix `/api`)

| Group | Examples |
|-------|----------|
| Health | `GET /`, `GET /health` |
| Stocks | `GET /stocks`, `POST /stocks/refresh`, `POST /stocks/initialize` |
| Market | `GET /market/status`, `GET /market/debug-quote/{symbol}` |
| AI | `POST /ai/analyze`, `GET /ai/analysis/latest`, `GET /ai/analysis/latest/{symbol}`, `POST /ai/generate-recommendation/{symbol}`, `POST /ai/scan-all` |
| Recommendations | `GET /recommendations`, `GET /recommendations/pending`, `POST /recommendations/{id}/approve` |
| Portfolio | `GET /portfolio`, `POST /portfolio/refresh-prices`, `POST /portfolio/scan-sells` |
| Trades | `GET /trades/history`, `GET /trades/stats` |
| Settings | `GET /settings`, `POST /settings` |
| Dashboard | `GET /dashboard/stats` |

---

## Frontend Routes

| Path | Page |
|------|------|
| `/` | Dashboard |
| `/stocks` | Stock Universe |
| `/research` | AI Research |
| `/queue` | Trade Queue |
| `/portfolio` | Portfolio |
| `/history` | Trade History |
| `/settings` | Settings |

---

## License and Disclaimer

This project is for educational and personal use. Trading in securities involves risk. Ensure you comply with Upstox and exchange terms and local regulations before using for live trading.
