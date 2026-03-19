"""AI engine for stock analysis and trade recommendations using Google Gemini.

Uses Gemini models with Google Search grounding for real-time news
and market context. Technical indicators are computed locally from
Upstox historical data and injected into the prompt.

Model priority is configured via the GEMINI_MODEL_PRIORITY env var
(comma-separated). When a model hits a rate limit (429), the engine
automatically falls back to the next model in the list and applies a
cooldown before retrying the rate-limited model.
"""
import logging
import os
import time
from typing import Optional, Dict, Any, List
import json
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PRIORITY = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite-preview"]
MODEL_COOLDOWN_SECONDS = 60


def _get_model_priority() -> List[str]:
    raw = os.environ.get("GEMINI_MODEL_PRIORITY", "")
    if raw.strip():
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(DEFAULT_MODEL_PRIORITY)


class _ModelManager:
    """Tracks rate-limited models and picks the best available one.

    Supports a user-preferred model override stored in MongoDB settings.
    When set, the preferred model is tried first; on rate-limit, it falls
    back through the remaining priority list.
    """

    def __init__(self):
        self._cooldowns: Dict[str, float] = {}
        self._preferred: Optional[str] = None

    def set_preferred(self, model: Optional[str]):
        self._preferred = model
        logger.info(f"Preferred model set to: {model or '(auto)'}")

    @property
    def preferred(self) -> Optional[str]:
        return self._preferred

    def mark_rate_limited(self, model: str):
        self._cooldowns[model] = time.time()
        logger.warning(f"Model {model} rate-limited — cooling down for {MODEL_COOLDOWN_SECONDS}s")

    def _ordered_models(self) -> List[str]:
        """Priority list with user-preferred model promoted to first."""
        base = _get_model_priority()
        if self._preferred and self._preferred in base:
            return [self._preferred] + [m for m in base if m != self._preferred]
        if self._preferred:
            return [self._preferred] + base
        return base

    def get_model(self) -> str:
        """Return the highest-priority model that is not on cooldown."""
        now = time.time()
        for model in self._ordered_models():
            limited_at = self._cooldowns.get(model)
            if limited_at is None or (now - limited_at) > MODEL_COOLDOWN_SECONDS:
                self._cooldowns.pop(model, None)
                return model
        fallback = self._ordered_models()[0]
        logger.warning(f"All models on cooldown, falling back to {fallback}")
        return fallback

    def current_model(self) -> str:
        return self.get_model()


_model_mgr = _ModelManager()


def get_active_model() -> str:
    """Public accessor for the currently active model name (used by routes/UI)."""
    return _model_mgr.current_model()


def get_available_models() -> List[str]:
    """Return the full ordered list of models from env config."""
    return _get_model_priority()


def get_preferred_model() -> Optional[str]:
    """Return the user-selected preferred model, or None for auto."""
    return _model_mgr.preferred


def set_preferred_model(model: Optional[str]):
    """Set the user-preferred model (None = auto/default priority)."""
    _model_mgr.set_preferred(model)


def _is_retryable_error(exc: Exception) -> bool:
    """Detect errors that should trigger model fallback (rate limits, model not found, etc.)."""
    msg = str(exc).lower()
    if "429" in msg or "resource_exhausted" in msg:
        return True
    if "rate" in msg and "limit" in msg:
        return True
    if "quota" in msg:
        return True
    if "404" in msg or "not_found" in msg or "not found" in msg:
        return True
    if "503" in msg or "unavailable" in msg:
        return True
    return False


def _get_gemini_client():
    """Get configured Gemini client using the google.genai SDK."""
    from google import genai
    api_key = os.environ.get('GOOGLE_GEMINI_KEY')
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def _call_gemini(client, prompt: str, config, max_retries: int = 4):
    """Call Gemini with automatic model fallback on rate-limit errors.

    Tries the preferred model, and on a 429/quota error switches to
    the next model in the priority list and retries.
    """
    errors = []
    tried = set()

    for attempt in range(max_retries + 1):
        model = _model_mgr.get_model()
        if model in tried:
            # Already failed with this model — skip to avoid tight loops
            remaining = [m for m in _get_model_priority() if m not in tried]
            if not remaining:
                break
            model = remaining[0]

        tried.add(model)
        try:
            logger.info(f"Gemini call → model={model} (attempt {attempt + 1})")
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            return response
        except Exception as e:
            if _is_retryable_error(e):
                _model_mgr.mark_rate_limited(model)
                errors.append((model, e))
                continue
            raise

    # All retries exhausted
    models_tried = ", ".join(m for m, _ in errors)
    raise RuntimeError(f"All Gemini models rate-limited ({models_tried}). Last error: {errors[-1][1]}")


from prompts import build_analysis_prompt, build_trade_signal_prompt, build_sell_signal_prompt


async def get_ai_stock_analysis(
    stock_symbol: str,
    stock_name: str,
    sector: str,
    analysis_type: str = "hybrid",
    technical_data: str = None
) -> Dict[str, Any]:
    """Analyze a stock using Gemini AI with real market data and search grounding.

    Optimized for daily profit-booking — structured output with actionable levels.
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

        analysis_prompt = build_analysis_prompt(
            stock_symbol, stock_name, sector, analysis_type, technical_data or "",
        )

        config = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.4,
        )

        response = _call_gemini(client, analysis_prompt, config)
        text_response = response.text

        # Parse confidence score
        confidence = 65.0
        match = re.search(r'confidence[^:]*?[:\s]*(\d+)', text_response.lower())
        if match:
            confidence = float(match.group(1))

        # Parse trade horizon
        trade_horizon = "short_term"  # default to short-term for daily profit-booking
        if re.search(r'(horizon|term)[^.]{0,30}(medium|1-3\s*month)', text_response.lower()):
            trade_horizon = "medium_term"
        if re.search(r'(horizon|term)[^.]{0,30}(long|3-12\s*month)', text_response.lower()):
            trade_horizon = "long_term"

        # Parse key signals
        key_signals = {}
        buy_sell = re.search(r'\*\*1\.\s*VERDICT\*\*[^[]*\[(BUY|SHORT|SELL|HOLD)\]', text_response)
        if not buy_sell:
            buy_sell = re.search(r'\b(BUY|SHORT|SELL|HOLD)\b', text_response)
        if buy_sell:
            action_parsed = buy_sell.group(1)
            # Normalize: SELL in analysis context (unheld stock) means SHORT
            if action_parsed == "SELL":
                action_parsed = "SHORT"
            key_signals["action"] = action_parsed

        # Extract target and stop-loss from the verdict line
        target_match = re.search(r'Target[:\s]*Rs\.?\s*([\d,.]+)', text_response)
        sl_match = re.search(r'Stop[- ]?Loss[:\s]*Rs\.?\s*([\d,.]+)', text_response)
        if target_match:
            key_signals["target_price"] = target_match.group(1).replace(",", "")
        if sl_match:
            key_signals["stop_loss"] = sl_match.group(1).replace(",", "")

        # Technical bias from scorecard references
        if re.search(r'score[:\s]*[+]?\d+.*bullish', text_response.lower()):
            key_signals["technical_bias"] = "bullish"
        elif re.search(r'score[:\s]*[-]\d+.*bearish', text_response.lower()):
            key_signals["technical_bias"] = "bearish"
        elif "bullish" in text_response.lower()[:500]:
            key_signals["technical_bias"] = "bullish"
        elif "bearish" in text_response.lower()[:500]:
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

    if action not in ("BUY", "SELL", "SHORT", "HOLD"):
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
        if target and (target / current_price) > 2.0:
            return f"target ({target}) is >100% above current price — unrealistic"
        if stop and (stop / current_price) < 0.5:
            return f"stop-loss ({stop}) is >50% below current price — unrealistic"

    if action in ("SELL", "SHORT"):
        if target and target >= current_price:
            return f"{action} target ({target}) must be below current price ({current_price})"
        if stop and stop <= current_price:
            return f"{action} stop-loss ({stop}) must be above current price ({current_price})"
        if target and stop and target >= stop:
            return f"{action} target ({target}) must be below stop-loss ({stop})"

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

        prompt = build_trade_signal_prompt(
            stock_symbol, stock_name, sector, current_price,
            technical_data or "", max_trade_value, risk_per_trade_pct,
        )

        config = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.3,
        )

        response = _call_gemini(client, prompt, config)
        text_response = response.text

        # Extract the first complete JSON object (non-greedy to avoid grabbing nested braces incorrectly)
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text_response)
        if not json_match:
            logger.error(f"No JSON found in AI response for {stock_symbol}: {text_response[:200]}")
            return None

        data = json.loads(json_match.group())

        # Normalize: AI may still return SELL — treat as SHORT for entry signals
        if data.get("action") == "SELL":
            data["action"] = "SHORT"
            data["product_type"] = "INTRADAY"

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

        action = data["action"]
        # For SHORT: risk_per_share = stop_loss - current_price (upward risk)
        if action == "SHORT" and stop_loss_val and stop_loss_val > effective_price:
            risk_per_share = stop_loss_val - effective_price
            risk_budget = max_trade_value * (risk_per_trade_pct / 100.0)
            qty_by_value = int(max_trade_value / effective_price) if effective_price else 1
            qty_by_risk = int(risk_budget / risk_per_share) if risk_per_share > 0 else qty_by_value
            quantity = max(1, min(qty_by_value, qty_by_risk))
        else:
            quantity = _compute_quantity(effective_price, max_trade_value,
                                        risk_per_trade_pct, stop_loss_val or 0)

        product_type = "INTRADAY" if action == "SHORT" else data.get("product_type", "DELIVERY")

        return {
            "stock_symbol": stock_symbol,
            "stock_name": stock_name,
            "action": action,
            "product_type": product_type,
            "trade_horizon": data.get("trade_horizon", "short_term" if action == "SHORT" else "medium_term"),
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

        prompt = build_sell_signal_prompt(
            symbol, position_block, technical_data or "", qty,
        )

        config = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.3,
        )

        response = _call_gemini(client, prompt, config)
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
