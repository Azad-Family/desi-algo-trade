# AlgoTrade - AI Trading Agent for Indian Stocks

## Original Problem Statement
Build an AI agent that iteratively researches Indian stocks (NSE/BSE) and executes trades through Upstox API. Features a bucket of 50+ stocks across sectors with hybrid strategy (fundamentals + momentum). Human-in-the-loop approval via web dashboard.

## Architecture
- **Frontend**: React 19 with Tailwind CSS, Framer Motion, Recharts
- **Backend**: FastAPI with MongoDB
- **AI**: Gemini 3 Flash via emergentintegrations library
- **Trading**: Upstox API v2 integration (credentials pending)

## User Personas
- Primary: Indian retail traders seeking AI-assisted trading decisions
- Use Case: Daily market analysis, trade recommendations with human approval

## Core Requirements (Static)
1. 50+ stocks across 10 sectors (IT, Banking, Pharma, Auto, FMCG, Energy, Metal, Infrastructure, Telecom, Consumer)
2. AI-powered stock research (fundamental + momentum analysis)
3. Trade recommendations with confidence scores
4. Human-in-the-loop approval workflow
5. Portfolio tracking with P&L
6. Risk management settings

## What's Been Implemented (Jan 18, 2026)
- [x] Stock Universe: 58 stocks across 10 sectors
- [x] AI Research: Gemini 3 Flash integration for stock analysis
- [x] Trade Recommendations: Auto-generated BUY/SELL signals
- [x] Approval Workflow: Approve/Modify/Reject trades
- [x] Portfolio Management: Holdings with P&L tracking
- [x] Trade History: Execution logging
- [x] Settings: Upstox API config, Risk parameters
- [x] Dashboard: Real-time stats and pending approvals
- [x] Dark theme trading terminal UI

## Prioritized Backlog
### P0 (Blocking)
- None

### P1 (High Priority)
- Real-time market data integration (Upstox market feed)
- Upstox OAuth flow for seamless authentication
- Scheduled AI scans during market hours

### P2 (Medium Priority)
- Historical performance charts
- Sector rotation analysis
- News sentiment integration
- Email/SMS alerts for trade recommendations

## Next Tasks
1. User to provide Upstox API credentials for live trading
2. Implement real-time price updates
3. Add backtesting capability
4. Mobile responsive optimizations
