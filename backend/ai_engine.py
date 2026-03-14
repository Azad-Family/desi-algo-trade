"""AI engine for stock analysis and trade recommendations using Google Gemini.

Uses Gemini 2.5 Flash with Google Search grounding for real-time news
and market context. Technical indicators are computed locally from
Upstox historical data and injected into the prompt.
"""
import logging
import os
from typing import Optional, Dict, Any, List
import json
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_gemini_client():
    """Get configured Gemini client using the google.genai SDK."""
    from google import genai
    api_key = os.environ.get('GOOGLE_GEMINI_KEY')
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


SYSTEM_PROMPT = """You are an expert Indian stock market analyst and algorithmic trading strategist 
specializing in NSE/BSE stocks. You combine quantitative technical analysis with fundamental research 
and macro-economic context to generate actionable trade signals.

Your analysis must account for:
- Indian market specifics: FII/DII flows, sector rotation, RBI monetary policy, INR movements
- Corporate governance and promoter holding patterns
- Quarterly earnings trends and management guidance
- Geopolitical risks affecting Indian markets
- Seasonal patterns in Indian equities

Always be specific with numbers, price levels, and timeframes. Never hedge excessively."""


async def get_ai_stock_analysis(
    stock_symbol: str,
    stock_name: str,
    sector: str,
    analysis_type: str = "hybrid",
    technical_data: str = None
) -> Dict[str, Any]:
    """Analyze a stock using Gemini AI with real market data and search grounding.
    
    Args:
        technical_data: Pre-formatted string of technical indicators from indicators.py
    """
    client = _get_gemini_client()
    if not client:
        logger.error("Google Gemini API key not configured")
        return {
            "stock_symbol": stock_symbol,
            "analysis": "AI analysis not available - API key not configured",
            "confidence_score": 0.0,
            "analysis_type": analysis_type
        }

    try:
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

        data_block = ""
        if technical_data:
            data_block = f"""
REAL MARKET DATA (computed from Upstox historical candles):
{technical_data}
"""

        analysis_prompt = f"""{SYSTEM_PROMPT}

Analyze {stock_name} ({stock_symbol}) from the {sector} sector on NSE.

Analysis Type: {analysis_type.upper()}
{data_block}
Use your Google Search capability to find the LATEST information about:
- Recent quarterly results and earnings surprises
- Latest news, corporate announcements, and management commentary
- FII/DII activity in this stock and sector
- RBI policy stance and macro-economic developments affecting {sector}
- Any recent geopolitical events impacting Indian markets
- Peer comparison within the {sector} sector

Provide a comprehensive analysis with these sections:

1. **Executive Summary** (2-3 sentences with clear directional bias)

2. **Fundamental Analysis**:
   - Latest quarterly revenue, profit, and margin trends
   - Key ratios: P/E, P/B, ROE, Debt/Equity (with sector comparison)
   - Competitive position and market share trajectory
   - Management quality and corporate governance

3. **Technical Analysis**:
   - Current trend direction (short, medium, long-term)
   - Key support and resistance levels with specific prices
   - Volume analysis and what it signals
   - Momentum indicators interpretation (RSI, MACD, Bollinger Bands)
   - Chart pattern if any (head & shoulders, flag, wedge, etc.)

4. **News & Sentiment**:
   - Latest material news affecting the stock
   - Market sentiment and analyst consensus
   - Any upcoming catalysts (earnings, AGM, dividends, etc.)

5. **Macro Context**:
   - Sector outlook for {sector}
   - Impact of current RBI policy and interest rates
   - FII/DII flow trends
   - Currency and global macro risks

6. **Risk Factors**: Top 3 specific, quantifiable risks

7. **Trading Recommendation**:
   - Signal: BUY / SELL / HOLD
   - Trade Horizon: SHORT_TERM (1-2 weeks) / MEDIUM_TERM (1-3 months) / LONG_TERM (3-12 months)
   - Horizon Rationale: Why this timeframe
   - Target Price with rationale
   - Stop Loss with rationale
   - Risk-Reward Ratio

8. **Confidence Score**: (0-100) with brief justification

Format with clear **bold headers** for each section."""

        config = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.7,
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=analysis_prompt,
            config=config,
        )
        text_response = response.text

        # Parse confidence score
        confidence = 65.0
        match = re.search(r'confidence[^:]*?[:\s]+(\d+)', text_response.lower())
        if match:
            confidence = float(match.group(1))

        # Parse trade horizon
        trade_horizon = "medium_term"
        if re.search(r'short[\s_-]?term', text_response.lower()):
            if re.search(r'(signal|horizon|recommendation)[^.]*short[\s_-]?term', text_response.lower()):
                trade_horizon = "short_term"
        if re.search(r'long[\s_-]?term', text_response.lower()):
            if re.search(r'(signal|horizon|recommendation)[^.]*long[\s_-]?term', text_response.lower()):
                trade_horizon = "long_term"

        # Parse key signals from the text
        key_signals = {}
        buy_sell = re.search(r'\b(BUY|SELL|HOLD)\b', text_response)
        if buy_sell:
            key_signals["action"] = buy_sell.group(1)

        if "bullish" in text_response.lower():
            key_signals["technical_bias"] = "bullish"
        elif "bearish" in text_response.lower():
            key_signals["technical_bias"] = "bearish"
        else:
            key_signals["technical_bias"] = "neutral"

        return {
            "stock_symbol": stock_symbol,
            "analysis": text_response,
            "confidence_score": min(confidence, 100.0),
            "analysis_type": analysis_type,
            "trade_horizon": trade_horizon,
            "key_signals": key_signals,
        }

    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return {
            "stock_symbol": stock_symbol,
            "analysis": f"Analysis failed: {str(e)}",
            "confidence_score": 0.0,
            "analysis_type": analysis_type
        }


def _validate_recommendation(data: dict, current_price: float) -> Optional[str]:
    """Sanity-check AI output. Returns error string if invalid, None if OK."""
    action = data.get("action")
    target = data.get("target_price", 0)
    stop = data.get("stop_loss", 0)

    if action not in ("BUY", "SELL", "HOLD"):
        return f"invalid action: {action}"

    if current_price <= 0:
        return None  # can't validate without a price

    if action == "BUY":
        if target and target <= current_price:
            return f"BUY target ({target}) must be above current price ({current_price})"
        if stop and stop >= current_price:
            return f"BUY stop-loss ({stop}) must be below current price ({current_price})"
        if target and stop and target <= stop:
            return f"target ({target}) must be above stop-loss ({stop})"
        # Reject absurd targets (>100% upside) or stop-losses (>50% loss)
        if target and (target / current_price) > 2.0:
            return f"target ({target}) is >100% above current price — unrealistic"
        if stop and (stop / current_price) < 0.5:
            return f"stop-loss ({stop}) is >50% below current price — unrealistic"

    if action == "SELL":
        if target and target >= current_price:
            return f"SELL target ({target}) must be below current price ({current_price})"
        if stop and stop <= current_price:
            return f"SELL stop-loss ({stop}) must be above current price ({current_price})"

    conf = data.get("confidence", 0)
    if not (0 <= conf <= 100):
        return f"confidence ({conf}) must be 0-100"

    return None


def _compute_quantity(current_price: float, max_trade_value: float,
                      risk_pct: float, stop_loss: float) -> int:
    """Calculate position size from risk parameters."""
    if current_price <= 0:
        return 1
    # Method 1: max trade value
    qty_by_value = int(max_trade_value / current_price) if current_price else 1
    # Method 2: risk-based sizing (risk only risk_pct of max_trade_value per trade)
    if stop_loss and stop_loss > 0 and current_price > stop_loss:
        risk_per_share = current_price - stop_loss
        risk_budget = max_trade_value * (risk_pct / 100.0)
        qty_by_risk = int(risk_budget / risk_per_share) if risk_per_share > 0 else qty_by_value
        return max(1, min(qty_by_value, qty_by_risk))
    return max(1, min(qty_by_value, 50))


async def generate_trade_recommendation(
    stock_symbol: str,
    stock_name: str,
    sector: str,
    technical_data: str = None,
    indicators_raw: Dict[str, Any] = None,
    max_trade_value: float = 100000.0,
    risk_per_trade_pct: float = 2.0,
) -> Optional[Dict[str, Any]]:
    """Generate a structured trade recommendation with trade horizon.

    Args:
        technical_data: Formatted indicator string (includes scorecard & constraints).
        indicators_raw: Raw indicator dict for server-side validation.
        max_trade_value: Max capital to deploy per trade (from Settings).
        risk_per_trade_pct: Max % of trade value to risk (from Settings).
    """
    client = _get_gemini_client()
    if not client:
        logger.warning("Google Gemini API key not configured")
        return None

    current_price = indicators_raw.get("current_price", 0) if indicators_raw else 0

    try:
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

        data_block = ""
        if technical_data:
            data_block = f"""
=== REAL TECHNICAL DATA (computed from Upstox historical candles — treat these numbers as ground truth) ===
The KEY_NUMBERS block below is a compact numeric summary; use it together with the full analysis for your decision.
{technical_data}
"""

        risk_block = f"""
=== RISK PARAMETERS ===
Max trade value: Rs.{max_trade_value:,.0f}
Risk per trade: {risk_per_trade_pct}% of trade value
"""

        prompt = f"""You are a disciplined algorithmic trading system for Indian NSE stocks.
You generate precise, data-driven trade signals. You NEVER guess prices — you use the
REAL TECHNICAL DATA provided below as ground truth for current price, indicators, and
signal scorecard.

RULES:
1. Your current_price MUST exactly match the "Current Price" in the data below.
2. Your target_price and stop_loss MUST fall within the ATR-BASED TRADE CONSTRAINTS 
   provided below for the chosen horizon. Do NOT set targets or stops outside those ranges.
3. Respect the SIGNAL SCORECARD: if net bias is BEARISH, do NOT recommend BUY unless you 
   have very strong fundamental/news reasons (explain them). If net bias is BULLISH, 
   do NOT recommend SELL unless fundamentals are deteriorating.
4. For BUY: target must be ABOVE current price, stop-loss must be BELOW current price.
5. For SELL: target must be BELOW current price, stop-loss must be ABOVE current price.
6. Do NOT include "quantity" — it is calculated server-side from risk parameters.
7. Respond with ONLY valid JSON. No markdown fences, no explanation outside the JSON.

{data_block}
{risk_block}

Use Google Search to check the LATEST news, quarterly results, and market conditions for 
{stock_name} ({stock_symbol}) in the {sector} sector.

JSON response format:
{{
    "action": "BUY" or "SELL" or "HOLD",
    "trade_horizon": "short_term" or "medium_term" or "long_term",
    "horizon_rationale": "1-2 sentence rationale for this timeframe",
    "current_price": {current_price if current_price else "<from data above>"},
    "target_price": <number within the ATR target range for chosen horizon>,
    "stop_loss": <number within the ATR stop-loss range for chosen horizon>,
    "reasoning": "3-4 sentences: what the technicals say + what fundamentals/news say + what the signal scorecard implies",
    "confidence": <0-100>,
    "key_signals": {{
        "technical_bias": "bullish" or "bearish" or "neutral",
        "fundamental_bias": "bullish" or "bearish" or "neutral",
        "news_sentiment": "positive" or "negative" or "neutral",
        "risk_level": "low" or "moderate" or "high"
    }}
}}"""

        config = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.3,
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        text_response = response.text

        # Extract the first complete JSON object (non-greedy to avoid grabbing nested braces incorrectly)
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text_response)
        if not json_match:
            logger.error(f"No JSON found in AI response for {stock_symbol}: {text_response[:200]}")
            return None

        data = json.loads(json_match.group())

        if data.get("action") == "HOLD":
            logger.info(f"AI recommends HOLD for {stock_symbol} — skipping")
            return None

        # Use real price from indicators if AI returned 0 or omitted it
        ai_price = float(data.get("current_price", 0))
        effective_price = ai_price if ai_price > 0 else current_price

        # Validate the output
        validation_error = _validate_recommendation(data, effective_price)
        if validation_error:
            logger.warning(f"AI recommendation for {stock_symbol} failed validation: {validation_error}")
            return None

        target_price = float(data.get("target_price", 0))
        stop_loss_val = float(data.get("stop_loss", 0)) if data.get("stop_loss") else None

        # Calculate quantity server-side from risk params
        quantity = _compute_quantity(effective_price, max_trade_value,
                                    risk_per_trade_pct, stop_loss_val or 0)

        return {
            "stock_symbol": stock_symbol,
            "stock_name": stock_name,
            "action": data["action"],
            "trade_horizon": data.get("trade_horizon", "medium_term"),
            "horizon_rationale": data.get("horizon_rationale", ""),
            "target_price": target_price,
            "current_price": effective_price,
            "stop_loss": stop_loss_val,
            "quantity": quantity,
            "ai_reasoning": data.get("reasoning", "AI generated recommendation"),
            "confidence_score": float(data.get("confidence", 60)),
            "key_signals": data.get("key_signals", {}),
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for {stock_symbol}: {e}")
    except Exception as e:
        logger.error(f"Trade recommendation error for {stock_symbol}: {e}")

    return None


HORIZON_DURATIONS = {
    "short_term": 14,
    "medium_term": 90,
    "long_term": 365,
}


def _compute_holding_age_days(bought_at: str) -> int:
    """Days since position was opened."""
    try:
        buy_dt = datetime.fromisoformat(bought_at)
        if buy_dt.tzinfo is None:
            buy_dt = buy_dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - buy_dt).days
    except Exception:
        return 0


async def generate_portfolio_sell_signal(
    holding: Dict[str, Any],
    technical_data: str = None,
) -> Optional[Dict[str, Any]]:
    """Evaluate whether a portfolio holding should be sold.
    
    Unlike generic analysis, this prompt is specifically given:
    - Buy price, quantity, invested value
    - Trade horizon from the original buy recommendation
    - How long the position has been held vs the horizon window
    - Target price and stop-loss from the original recommendation
    - Current P&L
    
    The AI must decide: SELL now, HOLD longer, or set a trailing stop.
    """
    client = _get_gemini_client()
    if not client:
        return None

    symbol = holding["stock_symbol"]
    name = holding.get("stock_name", symbol)
    sector = holding.get("sector", "Unknown")
    qty = holding.get("quantity", 0)
    avg_buy = holding.get("avg_buy_price", 0)
    current = holding.get("current_price", avg_buy)
    invested = holding.get("invested_value", avg_buy * qty)
    current_value = holding.get("current_value", current * qty)
    pnl = current_value - invested
    pnl_pct = (pnl / invested * 100) if invested > 0 else 0

    trade_horizon = holding.get("trade_horizon", "medium_term")
    target_price = holding.get("target_price")
    stop_loss = holding.get("stop_loss")
    bought_at = holding.get("bought_at")

    horizon_label = trade_horizon.replace("_", " ").title()
    horizon_max_days = HORIZON_DURATIONS.get(trade_horizon, 90)
    days_held = _compute_holding_age_days(bought_at) if bought_at else 0
    horizon_remaining = max(horizon_max_days - days_held, 0)
    horizon_expired = days_held > horizon_max_days

    try:
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

        position_block = f"""
=== YOUR POSITION ===
Stock: {name} ({symbol}) — {sector}
Quantity: {qty} shares
Buy Price: Rs.{avg_buy:.2f}
Current Price: Rs.{current:.2f}
Invested: Rs.{invested:.2f}
Current Value: Rs.{current_value:.2f}
Unrealized P&L: Rs.{pnl:.2f} ({pnl_pct:+.2f}%)

=== TRADE PLAN ===
Original Trade Horizon: {horizon_label} ({horizon_max_days} days)
Days Held: {days_held}
Horizon Remaining: {horizon_remaining} days {"** EXPIRED **" if horizon_expired else ""}
Original Target Price: {"Rs." + f"{target_price:.2f}" if target_price else "Not set"}
Original Stop-Loss: {"Rs." + f"{stop_loss:.2f}" if stop_loss else "Not set"}
Target Hit: {"YES" if target_price and current >= target_price else "NO" if target_price else "N/A"}
Stop-Loss Hit: {"YES" if stop_loss and current <= stop_loss else "NO" if stop_loss else "N/A"}
"""

        tech_block = ""
        if technical_data:
            tech_block = f"""
=== CURRENT TECHNICAL DATA (treat as ground truth) ===
{technical_data}
"""

        prompt = f"""You are a disciplined algorithmic trading system evaluating whether to SELL 
an existing portfolio holding. This is NOT a general analysis — you must decide based on 
the position context, the SIGNAL SCORECARD, and whether the trade horizon has been exhausted.

{position_block}
{tech_block}

HARD RULES (follow in order):
1. STOP-LOSS HIT (current price <= stop-loss) → action=SELL, urgency=immediate, sell_quantity=ALL
2. TARGET HIT (current price >= target) → action=SELL, urgency=immediate, sell_quantity=ALL 
   (unless SIGNAL SCORECARD is strongly bullish AND momentum is accelerating — then HOLD with revised target)
3. TRADE HORIZON EXPIRED:
   - Short-term held >14 days → action=SELL unless P&L > +5% and scorecard is bullish
   - Medium-term held >90 days → action=SELL unless fundamentals improved materially
   - Long-term held >365 days → reassess; SELL if thesis is broken
4. SIGNAL SCORECARD is BEARISH (majority bearish signals) → strong bias toward SELL
5. P&L worse than -10% → evaluate if thesis is broken; SELL if no catalyst for recovery
6. If none of the above apply → action=HOLD with tighter revised_stop_loss

Use Google Search to check LATEST news, earnings, and material events for {symbol}.

Respond with ONLY valid JSON (no markdown, no text outside JSON):
{{
    "action": "SELL" or "HOLD",
    "urgency": "immediate" or "soon" or "monitor",
    "reasoning": "3-4 sentences: reference specific signal scorecard results, P&L, horizon status, and any news",
    "revised_target": <new target price if HOLD, null if SELL>,
    "revised_stop_loss": <tighter stop-loss if HOLD, null if SELL>,
    "sell_quantity": <number of shares to sell, {qty} for full exit, 0 if HOLD>,
    "confidence": <0-100>,
    "horizon_assessment": "1-2 sentences on whether original trade thesis is intact and horizon status",
    "key_signals": {{
        "technical_bias": "bullish" or "bearish" or "neutral",
        "fundamental_bias": "bullish" or "bearish" or "neutral",
        "news_sentiment": "positive" or "negative" or "neutral",
        "risk_level": "low" or "moderate" or "high"
    }}
}}"""

        config = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.3,
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        text_response = response.text

        json_match = re.search(r'\{[\s\S]*\}', text_response)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "stock_symbol": symbol,
                "stock_name": name,
                "action": data.get("action", "HOLD"),
                "urgency": data.get("urgency", "monitor"),
                "reasoning": data.get("reasoning", ""),
                "sell_quantity": int(data.get("sell_quantity", 0)),
                "revised_target": data.get("revised_target"),
                "revised_stop_loss": data.get("revised_stop_loss"),
                "confidence": float(data.get("confidence", 50)),
                "horizon_assessment": data.get("horizon_assessment", ""),
                "key_signals": data.get("key_signals", {}),
                "position_context": {
                    "avg_buy_price": avg_buy,
                    "current_price": current,
                    "pnl_percent": round(pnl_pct, 2),
                    "days_held": days_held,
                    "trade_horizon": trade_horizon,
                    "horizon_expired": horizon_expired,
                },
            }

    except Exception as e:
        logger.error(f"Portfolio sell signal error for {symbol}: {e}")

    return None
