# Process Flows

This document describes the main end-to-end processes in AlgoTrade.

---

## 1. Application Startup

```
Server starts (uvicorn)
    → server.py startup_event()
    → get_stock_count()
    → If count == 0: initialize_stocks()  (clear stocks, insert from STOCK_UNIVERSE)
    → Else: log "Stock database ready"
    → Mount API router at /api
```

Frontend loads → reads `REACT_APP_BACKEND_URL` → calls `/api/health` and `/api/market/status` (sidebar). Dashboard may call `/api/dashboard/stats`, `/api/recommendations/pending`, etc.

---

## 2. Stock Universe and Price Refresh

**Load stocks**

- **GET /api/stocks** → `db.stocks.find()` → list of stocks (symbol, name, sector, current_price, etc.).
- **POST /api/stocks/initialize** → `initialize_stocks()` → clears and reloads from `stock_data.STOCK_UNIVERSE`.

**Refresh prices**

- **POST /api/stocks/refresh** → For each stock, `upstox_client.get_batch_quotes(symbols)` (live token) → update `db.stocks` with LTP and change percent.
- Used by Dashboard and Stock Universe to show latest prices.

---

## 3. AI Research (Single-Stock Analysis)

**Trigger**: User selects a stock on AI Research page and runs analysis.

**Flow**

1. **POST /api/ai/analyze** (body: `stock_symbol`, optional `analysis_type`).
2. Load stock from `db.stocks` (name, sector).
3. **Technical data**: `_get_technical_data(symbol)`:
   - `upstox_client.get_historical_candles(symbol)` (live token, ISIN-resolved key).
   - `compute_indicators(candles)` → raw dict.
   - `format_indicators_for_prompt(indicators)` → string for prompt.
4. **AI**: `get_ai_stock_analysis(symbol, name, sector, analysis_type, technical_data)`:
   - Gemini with Google Search; prompt includes technical data block and asks for analysis, signal, trade horizon, confidence, key signals.
   - Parse confidence, trade_horizon, key_signals from response.
5. **Persist**: Upsert into `db.analysis_history` (by symbol), so “latest analysis” is always available.
6. **Response**: AIAnalysisResponse (analysis text, recommendation, confidence_score, trade_horizon, key_signals).

**Frontend**: Shows analysis; “Generate recommendation” triggers the next flow.

---

## 4. Generate Trade Recommendation (Single Stock)

**Trigger**: User clicks “Generate recommendation” for a stock (e.g. from AI Research).

**Flow**

1. **POST /api/ai/generate-recommendation/{symbol}**.
2. Load stock; `_get_technical_data(symbol)` (historical candles + indicators).
3. **Risk settings**: `_get_risk_settings()` → max_trade_value, risk_per_trade_percent from `db.settings`.
4. **AI**: `generate_trade_recommendation(symbol, name, sector, technical_data, indicators_raw, max_trade_value, risk_per_trade_pct)`:
   - Gemini with technical data and risk block; asks for JSON: action, trade_horizon, target_price, stop_loss, reasoning, confidence, key_signals.
   - Server computes quantity from price, stop-loss, and risk params.
   - Validates target/stop vs current price and horizon constraints.
5. **Persist**: Build `TradeRecommendation` (including trade_horizon, key_signals) → `db.trade_recommendations.insert_one`.
6. **Response**: Created recommendation (or error).

**Result**: One new pending BUY/SELL/HOLD recommendation in the trade queue.

---

## 5. Scan All Stocks (Bulk Recommendations)

**Trigger**: User clicks “Scan all stocks” (e.g. on AI Research). Used to populate the Trade Queue with fresh signals.

**Flow**

1. **POST /api/ai/scan-all**.
2. **Clean queue**: Delete all `trade_recommendations` with status `pending` or `rejected`. Optionally delete old executed/rejected (e.g. >30 days).
3. Load risk settings; load all stocks from `db.stocks` (scan currently limited to first 10 in code).
4. **For each stock**:
   - `_get_technical_data(symbol)`.
   - `generate_trade_recommendation(...)` with technical_data and risk settings.
   - If recommendation returned: build `TradeRecommendation`, insert into `db.trade_recommendations`.
   - Short delay (e.g. 2s) between stocks to avoid rate limits.
5. **Response**: Counts (generated, scanned, cleared).

**Frontend**: Often navigates to Trade Queue after scan completes.

---

## 6. Trade Queue and Approval

**List recommendations**

- **GET /api/recommendations** (optional query: status, action) → list of trade recommendations (pending, executed, rejected).
- **GET /api/recommendations/pending** → pending only.

**Approve or reject**

1. **POST /api/recommendations/{rec_id}/approve** (body: approved, optional modified_quantity, modified_price).
2. Load recommendation; ensure status is `pending`.
3. Update status to `approved` or `rejected` (and apply quantity/price modifications if any).
4. **If approved**:
   - **Execute**: `upstox_client.place_order(symbol, action, quantity, price)` (uses order token: sandbox or live per config).
   - Update recommendation: status `executed`, executed_at, executed_price.
   - **Trade history**: Insert into `db.trade_history` (symbol, action, quantity, price, order_id, recommendation_id).
   - **Portfolio**: `update_portfolio(...)` — if BUY: add or update holding (quantity, avg price, sector, trade_horizon, target, stop_loss, ai_recommendation_id); if SELL: reduce quantity or remove holding.
5. **Response**: Updated recommendation document.

**Result**: Pending item moves to executed (and portfolio + trade history updated) or rejected.

---

## 7. Portfolio and Sell Scan

**View portfolio**

- **GET /api/portfolio** → `db.portfolio` holdings + summary (total invested, current, P&L).
- **GET /api/portfolio/sector-breakdown** → aggregation by sector.

**Refresh portfolio prices**

- **POST /api/portfolio/refresh-prices** → Batch quote for all portfolio symbols; update each holding’s current_price, current_value, pnl, pnl_percent.

**Scan for sell signals**

1. **POST /api/portfolio/scan-sells**.
2. Load all holdings; optionally clear old pending/rejected SELL recommendations.
3. Refresh holding prices (batch quote).
4. **For each holding**:
   - `_get_technical_data(symbol)`.
   - `generate_portfolio_sell_signal(holding, technical_data)` (Gemini: horizon met?, target/stop hit?, technicals, news → SELL or HOLD).
   - If signal is SELL: create a new SELL `TradeRecommendation` and insert into `db.trade_recommendations`.
5. **Response**: List of signals and sell_count.

**Result**: New SELL recommendations appear in Trade Queue for user to approve; approval flow is the same as above (execute SELL → update portfolio and trade history).

---

## 8. Settings and Dashboard

**Settings**

- **GET /api/settings** → Single document from `db.settings` (id `main_settings`); tokens masked in response.
- **POST /api/settings** → Update settings; if Upstox token provided, update `UPSTOX_ACCESS_TOKEN` in process env for subsequent market/order calls.

**Dashboard**

- **GET /api/dashboard/stats** → Aggregates: portfolio value, pending recommendation count, today’s trade count, stock count (from DB and portfolio/trade_history).

---

## 9. Data Flow Summary

| User action           | API                          | Main data read/write                          |
|-----------------------|------------------------------|-----------------------------------------------|
| Open app              | GET /api/health, /market/status, /stocks | DB read, Upstox (market)              |
| Run AI analysis       | POST /api/ai/analyze         | Upstox historical → indicators; Gemini; analysis_history |
| Generate recommendation | POST /api/ai/generate-recommendation/{symbol} | Same + trade_recommendations insert |
| Scan all              | POST /api/ai/scan-all       | trade_recommendations delete + insert         |
| Approve trade         | POST /api/recommendations/{id}/approve | trade_recommendations update; Upstox place_order; trade_history insert; portfolio update |
| Portfolio sell scan  | POST /api/portfolio/scan-sells | portfolio read; indicators + Gemini; trade_recommendations insert |
| Refresh prices        | POST /api/stocks/refresh, /portfolio/refresh-prices | Upstox batch quotes; stocks/portfolio update |

All market data and historical candle calls use the **live** Upstox token; only **order** placement uses sandbox or live token depending on `UPSTOX_USE_SANDBOX`.

---

## 10. Trade Mode (live / sandbox / simulated)

Every trade carries a `trade_mode` field that indicates how (or if) the order was actually placed:

| Mode | Meaning | How it happens |
|------|--------|----------------|
| **live** | Real order placed on Upstox via live credentials | `UPSTOX_USE_SANDBOX=false` and live `UPSTOX_ACCESS_TOKEN` is present |
| **sandbox** | Paper trade via Upstox sandbox API | `UPSTOX_USE_SANDBOX=true` and `UPSTOX_SANDBOX_ACCESS_TOKEN` is present |
| **simulated** | No Upstox API call — order is simulated locally | No order token available, or Upstox API call failed |

`trade_mode` is set by `UpstoxClient.place_order()` and propagated into:
- `trade_recommendations.trade_mode` (set on execution)
- `trade_history.trade_mode`
- `portfolio.trade_mode`

The UI shows a color-coded badge: green **LIVE**, yellow **SANDBOX**, grey **SIM** / **SIMULATED**.

---

## 11. UI ↔ Backend field mapping

### Stock Universe

| UI label    | Backend field     | Meaning |
|------------|-------------------|--------|
| Price (LTP) | `current_price`   | Last traded price from Upstox; updated on **Refresh**. |
| Day Chg %   | `change_percent`  | Percentage change from previous close; from last **Refresh**. |

### Trade Queue (Recommendations)

| UI column   | Backend field      | Meaning |
|-------------|--------------------|--------|
| Stock       | `stock_symbol`, `stock_name` | — |
| Action      | `action`           | BUY / SELL |
| Qty         | `quantity`         | Recommended quantity |
| Price       | `current_price`    | Price when the recommendation was generated (scan time). |
| Target      | `target_price`     | AI target price |
| Stop Loss   | `stop_loss`        | AI stop-loss |
| Confidence  | `confidence_score` | 0–100 |
| Horizon     | `trade_horizon`    | short_term / medium_term / long_term |
| Status      | `status`           | pending / approved / rejected / executed / failed. Executed rows also show trade_mode badge. |
| Scan at     | `created_at`       | When the recommendation was created (scan date and time). |
| Actions     | —                  | Approve / Edit / Reject for pending; for others, `updated_at` date. |

### Trade History

| UI column   | Backend field      | Meaning |
|-------------|--------------------|--------|
| Date/Time   | `executed_at`      | When the trade was executed. |
| Stock       | `stock_symbol`, `stock_name` | — |
| Action      | `action`           | BUY / SELL |
| Qty         | `quantity`         | Executed quantity |
| Price       | `price`            | Execution price |
| Total Value | `total_value`      | quantity × price |
| Order ID    | `order_id`         | Upstox order ID (or SIM-xxx for simulated) |
| Mode        | `trade_mode`       | **live** / **sandbox** / **simulated** — whether the order was real. |
| Status      | `status`           | executed |

### Portfolio

| UI element  | Backend field      | Meaning |
|-------------|-------------------|--------|
| Symbol / Name | `stock_symbol`, `stock_name` | — |
| Sector badge | `sector`          | — |
| Horizon badge | `trade_horizon`  | short_term / medium_term / long_term |
| Mode badge   | `trade_mode`      | **LIVE** / **SANDBOX** / **SIM** — how the holding was acquired. |
| Quantity     | `quantity`         | Shares held |
| Avg Price    | `avg_buy_price`    | Average purchase price |
| Invested     | `invested_value`   | Total cost basis |
| Current      | `current_value`    | Quantity × current_price |
| P&L          | `pnl`, `pnl_percent` | Unrealized profit/loss |
| Days held    | `bought_at`        | Computed client-side from purchase date |
| Target       | `target_price`     | AI target |
| SL           | `stop_loss`        | AI stop-loss |

### AI Research

| UI element     | Backend field      | Meaning |
|----------------|-------------------|--------|
| Analysis text  | `analysis`        | Full AI analysis text (markdown). |
| Confidence bar | `confidence_score` | 0–100 |
| Horizon badge  | `trade_horizon`   | short_term / medium_term / long_term |
| Key signals    | `key_signals`     | Dict of signal labels (technical_bias, action, etc.). |
| Analyzed at    | `created_at`      | When the analysis was run. |
| Analysis type  | `analysis_type`   | fundamental / momentum / hybrid |

### Dashboard

| UI card            | Backend field               | Meaning |
|--------------------|---------------------------|--------|
| Portfolio Value    | `portfolio_value`          | Sum of portfolio current_value |
| Total P&L          | `total_pnl`, `pnl_percent` | Unrealized P&L |
| Pending Approvals  | `pending_recommendations`  | Count of pending recommendations |
| Today's Trades     | `today_trades`             | Trades executed today |
| Stock Universe     | `total_stocks`             | Count of stocks in universe |
| Holdings           | `holdings_count`           | Active portfolio positions |
| Recommendation cards | from `/api/recommendations/pending` | Same fields as Trade Queue |
