# Process Flows

End-to-end processes in Desi Algo Trade.

---

## 1. Application Startup

```
Server starts (uvicorn)
    → server.py startup_event()
    → get_stock_count()
    → If count == 0: initialize_stocks()  (load from STOCK_UNIVERSE)
    → Else: log "Stock database ready"
    → Restore preferred Gemini model from DB settings
    → Auto-start sandbox scheduler (if enabled in scheduler_config)
    → Mount routers: api_router, agent_router, sandbox_router
```

Frontend loads → reads `REACT_APP_BACKEND_URL` → calls `/api/health` and `/api/market/status` (sidebar). Agent Chat page loads today's session or creates one.

---

## 2. Conversational Agent (Chat Flow)

**Trigger**: User sends a message on the Agent page (`/`).

**Flow**

1. **POST /api/agent/send** (body: `message`, `session_id`).
2. Load or create today's session from `agent_sessions`.
3. **Intent classification**: `classify_intent(message, session_context)` — Gemini classifies the message into one of: `briefing`, `discover`, `analyze`, `signal`, `approve`, `reject`, `portfolio`, `sell_scan`, `question`.
4. **Route to handler**:
   - `briefing` → Market overview with portfolio summary, key movers.
   - `discover` → Sector/theme-based stock discovery with live quotes and stock cards.
   - `analyze` → Deep AI analysis of a specific stock (technical + fundamental + news).
   - `signal` → Generate trade signal (BUY/SELL/SHORT) with target, stop-loss, horizon.
   - `approve` / `reject` → Execute or reject a pending recommendation from chat.
   - `portfolio` → Portfolio summary with holdings and P&L (mode-scoped).
   - `sell_scan` → Scan portfolio holdings for AI sell signals (mode-scoped).
   - `question` → General market/trading Q&A via Gemini with search grounding.
5. Handler returns structured `MessageBlock` array (text, stock_cards, analysis, trade_signal, suggested_prompts).
6. Persist session with updated messages and context.
7. **Response**: Array of message blocks rendered as rich UI in the chat.

**Session management**: Sessions are date-scoped. Previous sessions are accessible via session list.

---

## 3. Stock Universe and Price Refresh

**Load stocks**

- **GET /api/stocks** → `db.stocks.find()` → list of stocks with symbol, name, sector, current_price, change_percent.
- **POST /api/stocks/initialize** → `initialize_stocks()` → clears and reloads from `stock_data.STOCK_UNIVERSE`.

**Refresh prices**

- **POST /api/stocks/refresh** → `upstox_client.get_batch_quotes(symbols)` (live token) → update `db.stocks` with LTP and change percent. Also refreshes current-mode portfolio holdings with latest prices.
- Used by Research page "Refresh Prices" button and portfolio price refresh.

---

## 4. AI Research (Single-Stock Analysis)

**Trigger**: User selects a stock on the Research page and runs analysis.

**Flow**

1. **POST /api/ai/analyze** (body: `stock_symbol`, optional `analysis_type`).
2. Load stock from `db.stocks` (name, sector).
3. Determine mode: check if stock is in portfolio (mode-scoped) → "exit" mode if held, "entry" mode if not.
4. **Technical data**: `_get_technical_data(symbol)`:
   - `get_candles_cached(symbol)` — fetch from candle cache (MongoDB) or Upstox if stale.
   - `compute_indicators(candles)` → raw dict with 20+ indicators.
   - `format_indicators_for_prompt(indicators)` + `format_technical_numbers_for_ai(indicators)` → formatted strings for prompt.
5. **AI**: `get_ai_stock_analysis(symbol, name, sector, analysis_type, technical_data)`:
   - Gemini with Google Search grounding; prompt includes technical data and asks for analysis, signal, trade horizon, confidence, key signals.
   - Parse confidence, trade_horizon, key_signals from response.
6. **Persist**: Insert into `db.analysis_history`.
7. **Auto-generate trade signal**:
   - If stock held and AI says SELL → generate portfolio sell signal → create SELL recommendation (mode-tagged).
   - If stock not held and AI says BUY/SHORT → `generate_trade_recommendation()` → create BUY/SHORT recommendation (mode-tagged).
8. **Response**: AIAnalysisResponse with analysis text, confidence, trade_horizon, key_signals, signal_generated flag.

---

## 5. Scan All Stocks (Bulk Recommendations)

**Trigger**: User clicks "Scan All Stocks" on the Research page.

**Flow**

1. **POST /api/ai/scan-all**.
2. Determine current mode. **Clean queue**: Delete all pending recommendations for current mode.
3. Load risk settings; load all stocks sorted by sector/symbol.
4. **For each stock**:
   - `_get_technical_data(symbol)` via candle cache.
   - `generate_trade_recommendation(...)` with technical data and risk params.
   - Persist analysis to `analysis_history`.
   - If BUY or SHORT: create `TradeRecommendation` tagged with current mode, insert into DB.
   - 2-second delay between stocks to avoid Gemini rate limits.
5. **Response**: Counts (generated, scanned, deleted).

**Frontend**: Navigates to Trades page after scan completes.

---

## 6. Trade Queue and Approval

**List recommendations** (mode-scoped)

- **GET /api/recommendations** → recommendations for the current mode (sandbox or live). Optional filters: status, action.
- **GET /api/recommendations/pending** → pending only, current mode.

**Approve or reject**

1. **POST /api/recommendations/{rec_id}/approve** (body: approved, optional modified_quantity, modified_price).
2. Load recommendation; ensure status is `pending`.
3. Update status to `approved` or `rejected`.
4. **If approved**:
   - Apply quantity/price modifications if provided.
   - **Execute**: `upstox_client.place_order(symbol, action, quantity, price)` → returns `trade_mode` (live/sandbox/simulated).
   - Update recommendation: status `executed`, `trade_mode`, `executed_at`, `executed_price`.
   - **Trade history**: Insert into `db.trade_history` with `trade_mode`.
   - **Portfolio**: `update_portfolio(...)` — mode-aware lookup/insert. If BUY: add or update holding. If SELL: reduce or remove holding.
5. **Response**: Updated recommendation document.

**Agent chat approval**: The conversational agent can also approve/reject recommendations via the `approve`/`reject` intent handlers, which call the same execution logic.

---

## 7. Portfolio and Sell Scan

**View portfolio** (mode-scoped)

- **GET /api/portfolio** → Holdings filtered by current mode + summary (total invested, current, P&L) + `trade_mode` field.
- **GET /api/portfolio/sector-breakdown** → Aggregation by sector, current mode only.

**Refresh portfolio prices**

- **POST /api/portfolio/refresh-prices** → Batch quote for current-mode holdings; update current_price, current_value, pnl, pnl_percent.

**Direct sell**

- **POST /api/portfolio/{symbol}/sell** → Look up holding in current mode, place SELL order via Upstox, update portfolio and trade history.

**Scan for sell signals**

1. **POST /api/portfolio/scan-sells**.
2. Load current-mode holdings; refresh prices.
3. **For each holding**:
   - `_get_technical_data(symbol)`.
   - `generate_portfolio_sell_signal(holding, technical_data)` — Gemini evaluates: horizon expired? Target/stop hit? Technicals bearish?
   - If signal is SELL: create a SELL `TradeRecommendation` (mode-tagged) in DB.
4. **Response**: List of signals and sell_count.

**Result**: SELL recommendations appear in Trade Queue for approval.

---

## 8. Sandbox Paper Trading

**Virtual account**

- **GET /api/sandbox/account** → ₹1L virtual capital account with P&L stats, win rate, trade counts.
- **POST /api/sandbox/account/reset** → Reset to initial state.

**Screener**

1. **POST /api/sandbox/screener/run** → `screen_all_stocks()`.
2. For each stock: fetch candles from cache → compute indicators → score (momentum, volume, Supertrend, Bollinger, pivots/Fibonacci).
3. Rank by score; store in `screener_results`.
4. **Response**: Scored and ranked stock list.

**Holdings and trades**

- **GET /api/sandbox/holdings** → Current open sandbox positions.
- **GET /api/sandbox/trades** → Completed sandbox trades with P&L.
- **GET /api/sandbox/strategy** → Strategy insights (win rate, avg P&L, best/worst).

**Price refresh and exit check**

- **POST /api/sandbox/refresh-prices** → Update current prices for open sandbox holdings.
- **POST /api/sandbox/check-exits** → Check all open positions for exit signals (target hit, stop-loss hit, AI exit signal).

---

## 9. Scheduler (Automated Pipeline)

**Configuration**

- **GET/POST /api/sandbox/scheduler/config** → Manage: enabled, scan_time (IST), exit_scan_time, max_positions, max_trade_value, min_screener_score, auto_execute.

**Daily pipeline** (runs as asyncio background task)

```
09:20 IST — Daily Scan
    → Run screener on all stocks
    → Filter top-N by screener score (above min threshold)
    → Deep AI analysis on filtered stocks
    → Classify trade type (CNC long/short, intraday long/short)
    → Auto-execute in sandbox (if auto_execute_sandbox=true)

09:30–15:15 IST — Intraday Monitor (every ~60s)
    → Check all open sandbox positions
    → Evaluate exit signals (target, stop-loss, AI signal)
    → Auto-exit when conditions met
    → Scan CNC holdings for sell signals

15:15 IST — Intraday Square-off
    → Auto-close all intraday positions (long and short)
```

**Control**

- **POST /api/sandbox/scheduler/start** / **stop** → Start/stop the scheduler background task.
- **POST /api/sandbox/scheduler/scan-now** → Trigger an immediate manual scan.
- **GET /api/sandbox/scheduler/logs** → View scheduler activity logs.

---

## 10. Mode-Aware Data Flow

All core data is partitioned by `trade_mode` (determined by `UPSTOX_USE_SANDBOX`):

```
                    ┌─────────────────────────┐
                    │    UPSTOX_USE_SANDBOX    │
                    │    true → "sandbox"      │
                    │    false → "live"        │
                    └───────────┬─────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
     trade_recommendations   portfolio       trade_history
     (trade_mode filter)   (trade_mode)    (trade_mode filter)
```

- **Write**: New recommendations tagged with mode. Portfolio entries scoped by mode. Trade history records include mode from order result.
- **Read**: All GET endpoints filter by current mode. Dashboard stats scoped by mode.
- **Isolation**: Same stock can exist in both sandbox and live portfolios independently.
- **UI indicator**: Portfolio and Trades pages show a LIVE/SANDBOX badge.

---

## 11. Settings and Configuration

**Settings**

- **GET /api/settings** → Risk management parameters (max_trade_value, risk_per_trade_percent). Upstox tokens are in `.env`, never in DB.
- **POST /api/settings** → Update risk parameters.

**Gemini model**

- **GET /api/settings/models** → Available models, preferred model, active model.
- **POST /api/settings/model** → Set preferred model (or `null` for auto).

**Upstox status**

- **GET /api/settings/upstox-status** → Read-only status: order mode (sandbox/live), token presence, market data connectivity, order API connectivity.

---

## 12. Data Flow Summary

| User Action | API | Data Read/Write |
|-------------|-----|----------------|
| Chat with agent | POST /api/agent/send | agent_sessions, stocks, portfolio, analysis_history, trade_recommendations, Upstox, Gemini |
| Open app | GET /health, /market/status | DB read, Upstox |
| Browse stocks | GET /stocks | stocks collection |
| Refresh prices | POST /stocks/refresh | Upstox batch quotes → stocks + portfolio update |
| Run AI analysis | POST /ai/analyze | candle_cache → indicators → Gemini → analysis_history + trade_recommendations |
| Scan all stocks | POST /ai/scan-all | Delete pending recs → candle_cache → indicators → Gemini → trade_recommendations |
| Approve trade | POST /recommendations/{id}/approve | trade_recommendations update → Upstox place_order → trade_history + portfolio |
| View portfolio | GET /portfolio | portfolio (mode-filtered) |
| AI sell scan | POST /portfolio/scan-sells | portfolio → candle_cache → Gemini → trade_recommendations |
| Direct sell | POST /portfolio/{symbol}/sell | portfolio → Upstox order → trade_history + portfolio |
| Run screener | POST /sandbox/screener/run | candle_cache → indicators → screener_results |
| Scheduler scan | Automated (09:20 IST) | screener → Gemini → sandbox entry |

All market data and historical candle calls use the **live** Upstox token. Only **order** placement uses sandbox or live token per config.

---

## 13. UI ↔ Backend Field Mapping

### Research Page

| UI Element | Backend Field | Meaning |
|------------|--------------|---------|
| Stock list price | `current_price` | LTP from last refresh |
| Day change % | `change_percent` | Percentage change from previous close |
| Sector filter | `sector` | Stock sector |
| Analysis text | `analysis` | Full AI analysis (markdown) |
| Confidence bar | `confidence_score` | 0–100 |
| Horizon badge | `trade_horizon` | short_term / medium_term / long_term |
| Key signals | `key_signals` | Signal labels (action, technical_bias, etc.) |

### Trades Page

| UI Column | Backend Field | Meaning |
|-----------|--------------|---------|
| Stock | `stock_symbol`, `stock_name` | — |
| Action | `action` | BUY / SELL / SHORT |
| Qty | `quantity` | Recommended quantity |
| Price | `current_price` | Price when recommendation was generated |
| Target | `target_price` | AI target price |
| Stop Loss | `stop_loss` | AI stop-loss |
| Confidence | `confidence_score` | 0–100 |
| Horizon | `trade_horizon` | Short / Medium / Long |
| Status | `status` | pending / executed / rejected |
| Mode badge | `trade_mode` | LIVE / SANDBOX (page header) |
| Scan at | `created_at` | When the recommendation was generated |

### Portfolio Page

| UI Element | Backend Field | Meaning |
|------------|--------------|---------|
| Mode badge | `trade_mode` | LIVE / SANDBOX (page header, from API response) |
| Symbol / Name | `stock_symbol`, `stock_name` | — |
| Sector badge | `sector` | — |
| Horizon badge | `trade_horizon` | Short / Med / Long |
| Qty | `quantity` | Shares held |
| Buy Price | `avg_buy_price` | Average purchase price |
| LTP | `current_price` | Last traded price |
| Invested | `invested_value` | Total cost basis |
| P&L | `pnl`, `pnl_percent` | Unrealized profit/loss |
| Days held | `bought_at` | Computed client-side |
| Target | `target_price` | AI target |
| SL | `stop_loss` | AI stop-loss |

### Executed Trades (Trade Log)

| UI Column | Backend Field | Meaning |
|-----------|--------------|---------|
| Date/Time | `executed_at` | When the trade was executed |
| Stock | `stock_symbol`, `stock_name` | — |
| Action | `action` | BUY / SELL |
| Qty | `quantity` | Executed quantity |
| Price | `price` | Execution price |
| Total Value | `total_value` | quantity × price |
| Order ID | `order_id` | Upstox order ID (or SIM-xxx) |
| Mode | `trade_mode` | LIVE / SANDBOX / SIMULATED |
| Status | `status` | executed |
