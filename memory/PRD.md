# Desi Algo Trade — Product Requirements Document

## Problem Statement

Build an AI-powered trading agent for Indian stocks (NSE) that combines technical analysis, fundamental research, and LLM intelligence to generate trade recommendations. Features a conversational agent interface, human-in-the-loop approval workflow, and multiple execution modes (live, sandbox, virtual paper trading).

## Architecture

- **Frontend**: React 19 with Tailwind CSS, shadcn/ui, Framer Motion, Recharts
- **Backend**: FastAPI with MongoDB (Motor async)
- **AI**: Google Gemini 2.5 Flash with Google Search grounding
- **Market Data**: Upstox API V2 (quotes) + V3 (historical candles, orders)
- **Technical Analysis**: pandas + pandas-ta (20+ indicators)

## User Personas

- **Primary**: Indian retail traders seeking AI-assisted trading decisions
- **Use Case**: Daily market analysis, trade recommendations with human approval, portfolio management, and strategy backtesting via sandbox

## Core Requirements

1. 125 NSE stocks + 11 ETFs across 22 sectors (IT, Banking, Pharma, Auto, FMCG, Energy, Metal, Infrastructure, Telecom, Consumer, Financial Services, Healthcare, Cement, Capital Goods, Defence, Chemicals, Green Energy, Shipping, Logistics, Realty, Conglomerate, ETF)
2. Conversational AI agent as the primary interface
3. AI-powered stock research (fundamental + momentum + news analysis)
4. 20+ technical indicators with weighted signal scorecard
5. Trade recommendations with confidence scores and trade horizons
6. Human-in-the-loop approval workflow (approve/edit/reject)
7. Portfolio tracking with P&L, sector allocation, and sell signals
8. Mode-aware data isolation (sandbox vs live)
9. Virtual paper trading sandbox with automated scheduling
10. Risk management settings

## Implementation Status (March 2026)

### Completed

- [x] **Conversational AI Agent**: Chat-first interface with intent classification (briefing, discover, analyze, signal, approve, reject, portfolio, sell_scan, question). Rich message blocks (text, stock cards, analysis, trade signals, suggested prompts). Session persistence.
- [x] **Stock Universe**: 125 stocks + 11 ETFs across 22 sectors with live price refresh via Upstox.
- [x] **AI Research**: Per-stock analysis with Gemini 2.5 Flash + Google Search grounding. Fundamental, technical, news, and macro analysis. Auto-generates trade signals from analysis.
- [x] **Technical Indicators**: 20+ indicators — Supertrend, Pivot Points, CPR, Fibonacci, EMA/SMA (9/21/50/200), RSI, MACD, Bollinger Bands, ATR, OBV, ADX, Stochastic, candlestick patterns. Weighted signal scorecard.
- [x] **Trade Signals**: BUY/SELL/SHORT with target price, stop-loss, trade horizon (short/medium/long term), confidence score, key signals, product type (delivery/intraday).
- [x] **Approval Workflow**: Pending signals in trade queue. Approve (with quantity/price modification), edit, or reject. Agent-based approval via chat.
- [x] **Portfolio Management**: Mode-scoped holdings with P&L, sector allocation pie chart, AI sell scan, direct sell with quantity control, target/stop-loss tracking, days held.
- [x] **Mode-Aware Data**: All portfolio, recommendations, and trade history scoped to current Upstox mode (sandbox/live). Same stock can exist in both modes independently. UI shows LIVE/SANDBOX badge.
- [x] **Trade Execution**: Upstox live and sandbox order placement. Simulated fallback when no token available. Pre-trade fund validation in live mode.
- [x] **Trade History**: Executed trade log with stats (total trades, buy/sell counts, total traded value). Mode-scoped.
- [x] **Sandbox Paper Trading**: Virtual ₹1L capital account. CNC and intraday trade types. Automated AI-driven entry/exit. Win rate and strategy insights.
- [x] **Screener**: Fast technical pre-screen (momentum, volume, Supertrend, Bollinger, pivots/Fibonacci) to rank stocks before expensive AI calls.
- [x] **Scheduler**: Automated daily pipeline — pre-market screener → AI analysis → sandbox execution → intraday monitoring → 15:15 IST square-off. Configurable.
- [x] **Candle Cache**: Incremental MongoDB cache for Upstox historical candles. Fetch once, append daily.
- [x] **AI Model Management**: Multiple Gemini model support with fallback on rate limits. User-configurable preferred model. Cooldown tracking.
- [x] **Settings**: Risk parameters (max trade value, risk per trade %), Gemini model selection, Upstox connectivity status with token validation.
- [x] **Consolidated UI**: 6 pages — Agent (home), Research, Trades, Portfolio, Sandbox, Settings. Dark theme trading terminal aesthetic.
- [x] **Instrument Resolution**: Dynamic NSE instrument master download with ISIN-based key resolution and symbol overrides.
- [x] **Live Portfolio from Upstox**: In live mode, holdings, positions, and available funds are fetched directly from Upstox DEMAT account APIs. Portfolio page shows Available Funds card. AI analysis checks Upstox holdings for ENTRY/EXIT determination. Pre-trade fund validation rejects orders exceeding available margin.
- [x] **Two-Phase Scan**: "Scan All" uses a fast technical screener (parallel, no AI) to filter 125 stocks to top-N candidates, then runs deep AI analysis only on filtered candidates.

### UI Pages

| Page | Route | Purpose |
|------|-------|---------|
| Agent | `/` | Conversational AI agent (primary interface) |
| Research | `/research` | Stock browser with prices + sector filter + AI analysis |
| Trades | `/trades` | Pending signals (BUY/SHORT/SELL) + rec history + executed trade log |
| Portfolio | `/portfolio` | Mode-scoped holdings + P&L + sector chart + sell |
| Sandbox | `/sandbox` | Virtual paper trading + scheduler + analytics |
| Settings | `/settings` | Risk params + Gemini model + Upstox status |

## Backlog

### P1 (High Priority)

- Upstox OAuth flow for seamless token refresh (currently manual token rotation)
- WebSocket real-time price streaming (currently polling)
- Multi-timeframe analysis (intraday + daily + weekly candles in single analysis)
- Market holiday awareness for scheduler (currently only skips weekends)
- Strategy feedback loop — AI learns from sandbox backtesting performance

### P2 (Medium Priority)

- Historical performance charts and equity curve
- Sector rotation analysis and heatmap
- Email/SMS/push alerts for trade recommendations and portfolio events
- Backtesting framework with historical P&L simulation
- Mobile-responsive layout optimizations

### P3 (Nice to Have)

- Options chain analysis and strategy builder
- Multi-portfolio support (growth, income, momentum portfolios)
- Social sharing of trade ideas and analysis
- Integration with other Indian brokers (Zerodha, Angel One)
