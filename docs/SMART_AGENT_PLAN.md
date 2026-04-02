# Smart Trading Agent: From Tool to Autonomous Advisor

## Problem Summary

The current system has three fundamental weaknesses:

1. **One-shot analysis**: Each stock gets a single Gemini call with daily candle data — no verification, no cross-referencing, no iterative deepening.
2. **No market context**: Stocks are analyzed in isolation — no Nifty/Sensex trend, no sector rotation, no correlation awareness, no news/earnings calendar.
3. **Data gaps**: No fundamentals (PE, market cap, earnings), no intraday candles, no corporate actions, no structured news feed — the LLM relies on Google Search which is unreliable for real-time market data.

Below is a phased plan to fix each layer.

---

## Phase 1: Rich Data Foundation

**Goal**: Give the AI everything a good investor would look at before trading.

### 1a. Market Context Layer — new `market_context.py`

Add a daily "market pulse" that runs once before any stock analysis:

- **Nifty 50 + Nifty Bank index data**: Fetch via Upstox (already have instrument resolution). Compute trend (above/below 20 EMA), RSI, day change.
- **India VIX**: Fetch from Upstox or NSE. High VIX = reduce position sizes, tighten SLs.
- **Sector performance**: Aggregate day-change of all stocks per sector from our universe. Rank sectors by momentum (1d, 5d, 20d).
- **FII/DII flow**: Scrape from NSE's daily published data (available as CSV at `nse-india.com`).
- **Advance/Decline ratio**: From our 125-stock universe as a proxy.

This context block gets prepended to every AI prompt so the model knows the macro regime.

### 1b. Fundamental Data — enhance `stock_data.py` and `stock_init.py`

Use the free `india-corp-actions` Python package (no API key needed) plus scraping:

- **Earnings calendar**: `get_upcoming_results()` — know when a stock is about to report. Never trade into earnings without flagging it.
- **Corporate actions**: Dividends, splits, bonuses — these cause price gaps that break technical analysis.
- **Basic fundamentals**: PE ratio, market cap, 52-week high/low, promoter holding — store in `db.stocks` and refresh weekly. Source from Upstox instrument data or free NSE endpoints.

Add to `Stock` model fields (most already exist but are unpopulated): `pe_ratio`, `market_cap`, `promoter_holding_pct`, `next_earnings_date`, `upcoming_corporate_actions`.

### 1c. Dynamic Stock Universe — `stock_discovery.py`

Replace the fixed 125-stock universe with a **Core + Dynamic** approach:

- **Core watchlist** (~125 stocks): The current universe in `stock_data.py`. Always tracked, candles cached, indicators computed daily. Screener always runs on these.
- **Dynamic watchlist**: Stocks discovered by the agent and added at runtime. Stored in `db.dynamic_watchlist` with fields: `symbol`, `name`, `sector`, `discovered_by` (agent/user/news), `discovered_at`, `reason`, `last_active`, `status` (active/pruned).

**How stocks enter the dynamic watchlist**:

1. **Agent discovery during briefing**: Morning Gemini + Google Search call returns news mentioning a stock not in our universe. Agent resolves it on Upstox instrument master, fetches initial history, adds to watchlist.
2. **User conversation**: User asks "What about Ola Electric?" — agent checks if it's in the universe, if not, auto-adds it and begins tracking.
3. **Sector expansion**: When sector rotation analysis shows a hot sector, agent queries Upstox instrument master for other NSE stocks in that sector and adds high-volume ones.
4. **Correlation discovery**: If a core stock's top correlated peer is not in our universe, agent adds it.

**Lifecycle**:

- New stock: `resolve_instrument()` → `fetch_initial_candles()` → `compute_indicators()` → add to `db.dynamic_watchlist`
- Active: Included in daily candle refresh, screener runs, and correlation matrix
- Pruned: If not analyzed or traded for 30 days, moved to `status: "pruned"` (candle data kept, excluded from daily scans)

**Impact on existing code**:

- `screener.py` `screen_all_stocks()`: Query both `db.stocks` and `db.dynamic_watchlist` (where `status == "active"`)
- `candle_cache.py`: No change — it already works per-symbol
- `scheduler.py`: Universe = core + active dynamic stocks
- `correlation.py`: Include dynamic stocks in the matrix

### 1d. Correlation and Sector Analysis — new `correlation.py`

Using our cached 365-day candle data (already in MongoDB):

- **Correlation matrix**: Compute pairwise correlation of daily returns across all tracked stocks (core + dynamic). Store top 5 correlated peers per stock.
- **Beta vs Nifty**: Each stock's beta to Nifty 50 (rolling 60-day).
- **Sector rotation score**: Which sectors are gaining momentum relative to the market (relative strength).

Runs once daily (post-candle-cache refresh) and is cached in `db.correlation_data`.

**How correlation data flows to the agent**:

1. **Prompt injection**: When analyzing any stock, its correlation context is included in the prompt:

```
CORRELATED PEERS:
- TCS (corr: 0.82, today: +1.2%, 5d: +3.1%) — CONFIRMING bullish
- WIPRO (corr: 0.75, today: -0.3%, 5d: +1.8%) — NEUTRAL
- HCLTECH (corr: 0.71, today: +0.9%, 5d: +2.5%) — CONFIRMING bullish
SECTOR: IT sector rank #2/22 (5d momentum: +2.8%)
BETA: 0.95 vs Nifty 50
```

2. **Agent briefing**: Morning briefing includes "Top 3 diverging pairs" and "Sector rotation leaders/laggards".
3. **Validation layer**: Before generating a BUY signal, check if the stock's top correlated peers are bearish (divergence warning).

### 1e. Full Pairs Trading Engine — new `pairs_engine.py`

A dedicated quantitative strategy module that uses correlation data for systematic trading:

**Daily pre-market — Pair identification**:

1. From the correlation matrix, find all pairs with **correlation > 0.75 sustained over 60+ days** (not a one-week fluke).
2. For each stable pair, compute the **price ratio spread** and its **z-score** (how many standard deviations from the 60-day mean).
3. Store stable pairs in `db.pairs_data` with: `stock_a`, `stock_b`, `correlation`, `mean_spread`, `spread_std`, `current_z_score`.

**During market hours — Divergence detection** (every 5 minutes):

1. Refresh live prices for all stocks in stable pairs.
2. Recompute z-score of the spread.
3. **Entry signal**: When z-score crosses +/-2.0:
   - z > +2.0: Stock A is relatively overvalued → SHORT A + BUY B
   - z < -2.0: Stock B is relatively overvalued → SHORT B + BUY A
4. Generate a `PairTradeRecommendation` with both legs:

```
PAIR TRADE: BUY JSWSTEEL + SHORT TATASTEEL
Correlation: 0.85 (60-day stable)
Spread z-score: -2.3 (mean: 0, std: 1.0)
Expected convergence: 2-5 trading days
Entry: JSWSTEEL @ Rs.890 / TATASTEEL @ Rs.145
Target: z-score returns to 0 (spread normalizes)
Stop-loss: z-score reaches -3.0 (spread widens further)
Confidence: 78%
```

**Exit rules**:

- **Target hit**: z-score returns to within +/-0.5 of mean → close both legs (profit)
- **Stop-loss**: z-score widens beyond +/-3.0 → close both legs (cut loss)
- **Time decay**: If no convergence after 10 trading days → close both legs
- **Correlation breakdown**: If rolling 20-day correlation drops below 0.5 → emergency exit (the relationship broke)

**New trade type**: `PAIR_TRADE` in the trade queue, displayed with both legs linked. Approving a pair trade executes both orders atomically.

**Agent integration**: The agent can proactively surface pair opportunities:

> "I noticed HDFCBANK and ICICIBANK (correlation 0.87) have diverged significantly. HDFCBANK is up 2.5% this week while ICICIBANK is flat. The spread z-score is at -2.1. This is a potential pair trade — buy the laggard ICICIBANK, short the leader HDFCBANK. Historical convergence rate for this pair: 78% within 5 days."

### 1f. Multi-Timeframe Candles

Currently only daily candles are cached. Add:

- **Weekly candles**: Aggregate from daily (simple — group by ISO week). Already approximated in `indicators.py` but not properly.
- **Intraday (15-min) candles**: Fetch from Upstox for the current day only (not cached overnight). Used for entry timing during the scheduler's intraday monitor.

---

## Phase 2: Multi-Iteration Deep Research Agent

**Goal**: Replace single-shot Gemini calls with an iterative research loop that gathers data, reasons, verifies, and only then produces a signal.

### 2a. Research Loop — refactor `ai_engine.py`

Replace `get_ai_stock_analysis` + `generate_trade_recommendation` (two separate one-shot calls) with a single **multi-step research function**:

```
async def deep_research(symbol, context) -> ResearchResult:
    """
    Step 1: SCREEN  — Quick technical check (existing screener score)
    Step 2: CONTEXT — Gather market pulse, sector rank, correlated peers,
                      earnings calendar, corporate actions
    Step 3: ANALYZE — First Gemini call: "Given all this data, what is
                      your initial assessment? What additional info do
                      you need?"
    Step 4: VERIFY  — Second Gemini call with the model's own questions
                      answered (e.g. peer comparison, sector trend,
                      news sentiment). Explicitly ask: "Does your
                      analysis contradict any of these facts?"
    Step 5: SIGNAL  — Third Gemini call (if Step 4 confirms actionable):
                      Generate precise entry/exit with strict JSON schema.
                      Include confidence breakdown by category.
    Step 6: VALIDATE — Server-side validation (price sanity, ATR bounds,
                       fund availability, position limits, correlation
                       risk check — don't buy 3 highly correlated stocks)
    """
```

Key principles:

- **3 Gemini calls per stock** (not 1) — but only for stocks that pass the screener, so total API usage is controlled.
- **Self-correction**: Step 4 explicitly asks the model to challenge its own thesis.
- **Structured confidence**: Instead of a single 0-100 score, break into: technical (0-100), fundamental (0-100), sentiment (0-100), timing (0-100). Overall = weighted average. Minimum threshold to generate a signal.

### 2b. Confidence Gating — no trade without conviction

Add configurable thresholds in scheduler config:

- `min_confidence_to_trade`: 70 (default). Below this, log the analysis but don't generate a signal.
- `min_confidence_for_live`: 80. Only push to live trade queue if confidence is very high.
- `max_correlated_positions`: 3. Don't hold more than 3 stocks with >0.7 correlation.
- `earnings_blackout_days`: 3. Don't enter new positions within 3 days of earnings.

### 2c. Prompt Engineering Upgrades — `prompts.py`

Current prompts are structured but don't enforce verification. Add:

- **Devil's advocate prompt** (Step 4): "You recommended BUY. Now argue the bear case. What could go wrong? If the bear case is stronger, change your verdict."
- **Peer comparison prompt**: "Compare this stock's setup to its top 3 correlated peers. Are they confirming or diverging?"
- **Regime awareness**: "Current market regime: [bull/bear/sideways based on Nifty trend]. How does this affect your recommendation?"

---

## Phase 3: LLM Strategy

### Current Models

The system uses `gemini-3.1-flash-lite, gemini-2.5-flash, gemini-2.5-flash-lite, gemini-3-flash-preview` — all Flash-tier models optimized for speed and cost, not maximum reasoning accuracy.

### Recommendation: Tiered Model Strategy

For real-money decisions, use the best model where it matters most:

| Stage                           | Model              | Why                                        |
| ------------------------------- | ------------------ | ------------------------------------------ |
| Intent classification, screener | `gemini-2.5-flash` | Fast, cheap, good enough for routing       |
| Deep analysis (Step 3)          | `gemini-2.5-pro`   | Best reasoning for financial analysis      |
| Verification (Step 4)           | `gemini-2.5-pro`   | Critical — this catches errors             |
| Signal generation (Step 5)      | `gemini-2.5-flash` | Structured JSON output, well-defined rules |
| Agent chat (Q&A, briefing)      | `gemini-2.5-flash` | Interactive, cost-sensitive                |

This means adding `gemini-2.5-pro` to the model priority list and using it selectively (not for every call). The Pro model costs ~4x more per token but is significantly better at complex financial reasoning.

**Alternative if budget allows**: Add `gpt-4o` as a secondary verification model — cross-model consensus increases reliability. This requires adding an OpenAI client alongside the existing Gemini client.

---

## Phase 4: Smarter Scheduler Pipeline

### Enhanced Daily Pipeline in `scheduler.py`

```
05:30 IST — Pre-market data refresh
    - Refresh candle cache for all stocks (core + dynamic watchlist)
    - Compute correlation matrix and identify stable pairs
    - Fetch earnings calendar, corporate actions
    - Fetch FII/DII flows, India VIX
    - Agent discovers new stocks from overnight news (dynamic universe)

09:15 IST — Market open context
    - Compute market pulse (Nifty/Bank Nifty opening gap, VIX)
    - Run sector rotation analysis
    - Identify overnight gap stocks
    - Compute opening z-scores for all stable pairs

09:20 IST — Screening + Deep Research
    - Phase 1: Technical screener on full universe (core + dynamic, ~30s)
    - Phase 2: Deep research on top 10 candidates (3 calls each, ~3 min)
    - Phase 3: Portfolio correlation check (don't over-concentrate)
    - Phase 4: Pairs divergence scan — generate pair trade signals
    - Generate signals with confidence breakdown

10:00 IST — Second-chance scan
    - Re-screen stocks that opened with unusual volume
    - Check if morning gap-up/gap-down stocks are reversing
    - Re-check pair z-scores after first hour of trading

12:00 IST — Mid-day review
    - Re-evaluate open positions against current price action
    - Check if any SL/targets need adjustment based on intraday action
    - Pairs monitor: check for convergence/divergence on open pairs

14:30 IST — Exit preparation
    - Final check on intraday positions before squareoff window
    - Identify CNC positions that may need exit tomorrow
    - Close any pairs with time-decay exit (>10 days)

15:15 IST — Intraday squareoff (existing, includes intraday pair legs)
15:30 IST — End of day
    - Log daily P&L (individual + pairs)
    - Update strategy insights
    - Prune inactive dynamic watchlist stocks (>30 days unused)
    - Prepare next-day watchlist
```

### Intraday Price Monitoring Enhancement

Currently checks every 60s for SL/target hits. Enhance:

- **Trailing stop-loss**: If a position is up >1%, trail the SL to breakeven. If up >2%, trail SL to lock in 1% profit.
- **Time-based exits**: If an intraday trade is flat (< 0.3% move) after 2 hours, consider exiting to free capital.
- **Momentum reversal detection**: If RSI on 15-min candles crosses below 30 (for longs) or above 70 (for shorts), flag for early exit.

---

## Phase 5: Error Prevention and Reliability

### Server-Side Validation Layer — new `validator.py`

Every signal must pass these checks before reaching the trade queue:

- **Price sanity**: Target and SL must be within 2x ATR of current price.
- **Direction consistency**: If AI says BUY, target must be above current price and SL below.
- **Correlation limit**: Don't hold >3 stocks with >0.7 pairwise correlation.
- **Earnings proximity**: Warn (or block) if stock reports earnings within 3 days.
- **Capital allocation**: Single trade can't exceed 20% of available capital.
- **Daily loss limit**: If total realized + unrealized loss exceeds a threshold (e.g. 2% of capital), pause new entries.
- **Double-entry prevention**: Don't generate a BUY signal for a stock already held.
- **Pair trade validation**: Both legs must be executable (instrument resolved, sufficient capital for both). Correlation must still be above 0.6 at time of execution. Z-score must still be beyond threshold.

### Audit Trail

Log every decision point:

- What data was available when the signal was generated.
- The full 3-step reasoning chain (not just the final signal).
- Why the signal passed/failed validation.
- Store in `db.research_logs` for post-mortem analysis.

---

## New Dependencies

- `india-corp-actions` — Free NSE/BSE corporate actions and earnings calendar (no API key).
- `numpy` — Already implicitly available via pandas, but needed explicitly for correlation matrix computation.
- Optionally: `openai` — If adding GPT-4o as a cross-verification model.

---

## What This Does NOT Change

- Frontend UI pages remain the same (Agent, Research, Trades, Portfolio, Sandbox, Settings).
- Upstox order execution remains the same.
- Human-in-the-loop approval for live trades remains mandatory.

## What DOES Change in UI

- **Trade Queue**: New `PAIR_TRADE` tab showing linked pair trade recommendations (both legs together). Approving a pair executes both orders.
- **Agent Briefing**: Morning briefing includes market context, diverging pairs, and dynamic watchlist additions.
- **Research Page**: Correlation peers section in analysis report. Pair divergence alerts in history list.
- **Sandbox**: Pair trades tracked as linked positions with combined P&L.
- **Settings**: New configuration for pairs trading thresholds (min correlation, z-score entry/exit, max pairs).

The bulk of changes are in the data layer and AI reasoning pipeline — making the brain smarter while extending the body only where needed.
