"""Technical indicator calculations using pandas-ta.

Takes raw OHLCV candle data from Upstox and computes indicators
that get fed into the AI analysis prompt.
"""
import logging
from typing import Dict, Any, Optional
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


def candles_to_dataframe(candles: list) -> Optional[pd.DataFrame]:
    """Convert Upstox candle arrays to a pandas DataFrame.
    
    Upstox format: [timestamp, open, high, low, close, volume, oi]
    """
    if not candles or len(candles) < 20:
        logger.warning(f"Insufficient candle data: {len(candles) if candles else 0} candles")
        return None

    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def compute_indicators(candles: list) -> Optional[Dict[str, Any]]:
    """Compute all technical indicators from raw candle data.
    
    Returns a structured dict ready for injection into the AI prompt.
    """
    df = candles_to_dataframe(candles)
    if df is None:
        return None

    try:
        result = {}
        latest = df.iloc[-1]

        # --- Price Context ---
        result["current_price"] = round(float(latest["close"]), 2)
        result["day_open"] = round(float(latest["open"]), 2)
        result["day_high"] = round(float(latest["high"]), 2)
        result["day_low"] = round(float(latest["low"]), 2)
        result["volume"] = int(latest["volume"])
        result["high_52w"] = round(float(df["high"].tail(252).max()), 2)
        result["low_52w"] = round(float(df["low"].tail(252).min()), 2)

        pct_from_52w_high = ((latest["close"] - df["high"].tail(252).max()) / df["high"].tail(252).max()) * 100
        result["pct_from_52w_high"] = round(float(pct_from_52w_high), 1)

        # --- Moving Averages ---
        sma_20 = ta.sma(df["close"], length=20)
        sma_50 = ta.sma(df["close"], length=50)
        sma_200 = ta.sma(df["close"], length=200)
        ema_12 = ta.ema(df["close"], length=12)
        ema_26 = ta.ema(df["close"], length=26)

        result["sma_20"] = round(float(sma_20.iloc[-1]), 2) if sma_20 is not None and not sma_20.empty else None
        result["sma_50"] = round(float(sma_50.iloc[-1]), 2) if sma_50 is not None and not sma_50.empty else None
        result["sma_200"] = round(float(sma_200.iloc[-1]), 2) if sma_200 is not None and not sma_200.empty else None
        result["ema_12"] = round(float(ema_12.iloc[-1]), 2) if ema_12 is not None and not ema_12.empty else None
        result["ema_26"] = round(float(ema_26.iloc[-1]), 2) if ema_26 is not None and not ema_26.empty else None

        # Price vs MAs
        price = latest["close"]
        if result["sma_200"]:
            result["above_200_sma"] = price > result["sma_200"]
        if result["sma_50"] and result["sma_200"]:
            result["golden_cross"] = result["sma_50"] > result["sma_200"]

        # --- RSI ---
        rsi = ta.rsi(df["close"], length=14)
        if rsi is not None and not rsi.empty:
            result["rsi_14"] = round(float(rsi.iloc[-1]), 1)
            if result["rsi_14"] > 70:
                result["rsi_signal"] = "overbought"
            elif result["rsi_14"] < 30:
                result["rsi_signal"] = "oversold"
            else:
                result["rsi_signal"] = "neutral"

        # --- MACD ---
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            macd_line = macd_df.iloc[-1].get("MACD_12_26_9")
            signal_line = macd_df.iloc[-1].get("MACDs_12_26_9")
            histogram = macd_df.iloc[-1].get("MACDh_12_26_9")
            result["macd_line"] = round(float(macd_line), 2) if pd.notna(macd_line) else None
            result["macd_signal"] = round(float(signal_line), 2) if pd.notna(signal_line) else None
            result["macd_histogram"] = round(float(histogram), 2) if pd.notna(histogram) else None
            if result["macd_line"] is not None and result["macd_signal"] is not None:
                result["macd_crossover"] = "bullish" if result["macd_line"] > result["macd_signal"] else "bearish"

        # --- Bollinger Bands ---
        bb = ta.bbands(df["close"], length=20, std=2)
        if bb is not None and not bb.empty:
            result["bb_upper"] = round(float(bb.iloc[-1].get("BBU_20_2.0", 0)), 2)
            result["bb_middle"] = round(float(bb.iloc[-1].get("BBM_20_2.0", 0)), 2)
            result["bb_lower"] = round(float(bb.iloc[-1].get("BBL_20_2.0", 0)), 2)

        # --- ATR (for stop-loss calibration) ---
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        if atr is not None and not atr.empty:
            result["atr_14"] = round(float(atr.iloc[-1]), 2)

        # --- Volume Analysis ---
        vol_sma_20 = ta.sma(df["volume"].astype(float), length=20)
        if vol_sma_20 is not None and not vol_sma_20.empty:
            avg_vol = float(vol_sma_20.iloc[-1])
            result["volume_avg_20"] = int(avg_vol)
            result["volume_ratio"] = round(float(latest["volume"]) / avg_vol, 2) if avg_vol > 0 else 1.0

        # --- ADX (trend strength) ---
        adx = ta.adx(df["high"], df["low"], df["close"], length=14)
        if adx is not None and not adx.empty:
            adx_val = adx.iloc[-1].get("ADX_14")
            if pd.notna(adx_val):
                result["adx_14"] = round(float(adx_val), 1)
                if result["adx_14"] > 25:
                    result["trend_strength"] = "strong"
                else:
                    result["trend_strength"] = "weak"

        # --- Stochastic RSI ---
        stoch_rsi = ta.stochrsi(df["close"], length=14)
        if stoch_rsi is not None and not stoch_rsi.empty:
            k_val = stoch_rsi.iloc[-1].get("STOCHRSIk_14_14_3_3")
            d_val = stoch_rsi.iloc[-1].get("STOCHRSId_14_14_3_3")
            if pd.notna(k_val):
                result["stoch_rsi_k"] = round(float(k_val), 1)
            if pd.notna(d_val):
                result["stoch_rsi_d"] = round(float(d_val), 1)

        # --- Price change over periods ---
        if len(df) >= 5:
            result["change_5d"] = round(float((price - df.iloc[-5]["close"]) / df.iloc[-5]["close"] * 100), 2)
        if len(df) >= 20:
            result["change_20d"] = round(float((price - df.iloc[-20]["close"]) / df.iloc[-20]["close"] * 100), 2)
        if len(df) >= 60:
            result["change_60d"] = round(float((price - df.iloc[-60]["close"]) / df.iloc[-60]["close"] * 100), 2)

        logger.info(f"Computed {len(result)} technical indicators")
        return result

    except Exception as e:
        logger.error(f"Indicator computation failed: {e}")
        return None


def compute_signal_scorecard(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """Distill raw indicators into a bullish/bearish signal tally.

    Returns a dict with individual signal verdicts and overall counts so the
    AI prompt gets a pre-digested quantitative anchor rather than raw numbers.
    """
    signals = []  # list of (name, "bullish" | "bearish" | "neutral")

    # 1. Price vs 200-SMA
    if indicators.get("above_200_sma") is not None:
        signals.append(("price_vs_200sma",
                        "bullish" if indicators["above_200_sma"] else "bearish"))

    # 2. Golden / Death cross
    if indicators.get("golden_cross") is not None:
        signals.append(("ma_cross",
                        "bullish" if indicators["golden_cross"] else "bearish"))

    # 3. RSI
    rsi_sig = indicators.get("rsi_signal")
    if rsi_sig == "overbought":
        signals.append(("rsi", "bearish"))
    elif rsi_sig == "oversold":
        signals.append(("rsi", "bullish"))
    else:
        signals.append(("rsi", "neutral"))

    # 4. MACD crossover
    macd_co = indicators.get("macd_crossover")
    if macd_co:
        signals.append(("macd", macd_co))

    # 5. Bollinger Band position
    price = indicators.get("current_price", 0)
    bb_upper = indicators.get("bb_upper")
    bb_lower = indicators.get("bb_lower")
    if bb_upper and bb_lower and price:
        if price >= bb_upper:
            signals.append(("bollinger", "bearish"))
        elif price <= bb_lower:
            signals.append(("bollinger", "bullish"))
        else:
            signals.append(("bollinger", "neutral"))

    # 6. Volume confirmation
    vol_ratio = indicators.get("volume_ratio")
    if vol_ratio is not None:
        if vol_ratio >= 1.5:
            signals.append(("volume", "bullish"))
        elif vol_ratio <= 0.5:
            signals.append(("volume", "bearish"))
        else:
            signals.append(("volume", "neutral"))

    # 7. ADX trend strength
    adx = indicators.get("adx_14")
    if adx is not None:
        signals.append(("trend_strength",
                        "bullish" if adx > 25 else "neutral"))

    bullish = sum(1 for _, v in signals if v == "bullish")
    bearish = sum(1 for _, v in signals if v == "bearish")
    neutral = sum(1 for _, v in signals if v == "neutral")
    total = len(signals)

    if total == 0:
        net = "neutral"
    elif bullish > bearish and bullish >= total * 0.5:
        net = "bullish"
    elif bearish > bullish and bearish >= total * 0.5:
        net = "bearish"
    else:
        net = "neutral"

    return {
        "signals": signals,
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "total": total,
        "net_bias": net,
    }


def compute_trade_constraints(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """Pre-calculate ATR-based target / stop-loss ranges per trade horizon.

    Gives the AI concrete guardrails so it can't hallucinate absurd levels.
    """
    price = indicators.get("current_price", 0)
    atr = indicators.get("atr_14", 0)
    if not price or not atr:
        return {}

    return {
        "current_price": price,
        "atr_14": atr,
        "atr_pct": round(atr / price * 100, 2),
        "short_term": {
            "stop_loss_range": (round(price - 2 * atr, 2), round(price - 1 * atr, 2)),
            "target_range": (round(price + 1 * atr, 2), round(price + 3 * atr, 2)),
            "horizon": "1-2 weeks",
        },
        "medium_term": {
            "stop_loss_range": (round(price - 3 * atr, 2), round(price - 2 * atr, 2)),
            "target_range": (round(price + 3 * atr, 2), round(price + 6 * atr, 2)),
            "horizon": "1-3 months",
        },
        "long_term": {
            "stop_loss_range": (round(price - 5 * atr, 2), round(price - 3 * atr, 2)),
            "target_range": (round(price + 5 * atr, 2), round(price + 10 * atr, 2)),
            "horizon": "3-12 months",
        },
        "support_levels": [
            indicators.get("sma_50"),
            indicators.get("sma_200"),
            indicators.get("bb_lower"),
        ],
        "resistance_levels": [
            indicators.get("bb_upper"),
            indicators.get("high_52w"),
        ],
    }


def format_indicators_for_prompt(indicators: Dict[str, Any]) -> str:
    """Format computed indicators into a human-readable block for the AI prompt.

    Includes the signal scorecard and ATR-based constraints so the model
    gets a pre-digested quantitative summary alongside raw numbers.
    """
    if not indicators:
        return "Technical indicator data unavailable."

    lines = []
    lines.append("=== PRICE DATA ===")
    lines.append(f"Current Price: Rs.{indicators.get('current_price', 'N/A')}")
    lines.append(f"Day Range: Rs.{indicators.get('day_low', 'N/A')} - Rs.{indicators.get('day_high', 'N/A')}")
    lines.append(f"52-Week Range: Rs.{indicators.get('low_52w', 'N/A')} - Rs.{indicators.get('high_52w', 'N/A')} ({indicators.get('pct_from_52w_high', 'N/A')}% from high)")

    vol = indicators.get('volume', 'N/A')
    avg_vol = indicators.get('volume_avg_20', 'N/A')
    vol_str = f"{vol:,}" if isinstance(vol, int) else str(vol)
    avg_vol_str = f"{avg_vol:,}" if isinstance(avg_vol, int) else str(avg_vol)
    lines.append(f"Volume: {vol_str} (vs 20d avg {avg_vol_str}, ratio: {indicators.get('volume_ratio', 'N/A')}x)")

    if indicators.get("change_5d") is not None:
        lines.append(f"Price Change: 5d={indicators['change_5d']}% | 20d={indicators.get('change_20d', 'N/A')}% | 60d={indicators.get('change_60d', 'N/A')}%")

    lines.append("")
    lines.append("=== MOVING AVERAGES ===")
    lines.append(f"SMA: 20d={indicators.get('sma_20', 'N/A')} | 50d={indicators.get('sma_50', 'N/A')} | 200d={indicators.get('sma_200', 'N/A')}")
    lines.append(f"EMA: 12d={indicators.get('ema_12', 'N/A')} | 26d={indicators.get('ema_26', 'N/A')}")
    if indicators.get("above_200_sma") is not None:
        lines.append(f"Price {'ABOVE' if indicators['above_200_sma'] else 'BELOW'} 200-SMA")
    if indicators.get("golden_cross") is not None:
        lines.append(f"{'Golden Cross (50 > 200 SMA)' if indicators['golden_cross'] else 'Death Cross (50 < 200 SMA)'}")

    lines.append("")
    lines.append("=== MOMENTUM INDICATORS ===")
    lines.append(f"RSI(14): {indicators.get('rsi_14', 'N/A')} [{indicators.get('rsi_signal', 'N/A')}]")
    if indicators.get("macd_line") is not None:
        lines.append(f"MACD: Line={indicators['macd_line']} | Signal={indicators.get('macd_signal', 'N/A')} | Hist={indicators.get('macd_histogram', 'N/A')} [{indicators.get('macd_crossover', 'N/A')}]")
    if indicators.get("stoch_rsi_k") is not None:
        lines.append(f"Stochastic RSI: %K={indicators['stoch_rsi_k']} | %D={indicators.get('stoch_rsi_d', 'N/A')}")
    if indicators.get("adx_14") is not None:
        lines.append(f"ADX(14): {indicators['adx_14']} [trend: {indicators.get('trend_strength', 'N/A')}]")

    lines.append("")
    lines.append("=== VOLATILITY ===")
    if indicators.get("bb_upper") is not None:
        lines.append(f"Bollinger Bands: Upper={indicators['bb_upper']} | Mid={indicators['bb_middle']} | Lower={indicators['bb_lower']}")
    if indicators.get("atr_14") is not None:
        lines.append(f"ATR(14): Rs.{indicators['atr_14']}")

    # --- Signal Scorecard ---
    scorecard = compute_signal_scorecard(indicators)
    lines.append("")
    lines.append("=== SIGNAL SCORECARD ===")
    lines.append(f"Net Bias: {scorecard['net_bias'].upper()} ({scorecard['bullish']} bullish / {scorecard['bearish']} bearish / {scorecard['neutral']} neutral out of {scorecard['total']} signals)")
    for name, verdict in scorecard["signals"]:
        lines.append(f"  {name}: {verdict}")

    # --- Trade Constraints ---
    constraints = compute_trade_constraints(indicators)
    if constraints:
        lines.append("")
        lines.append("=== ATR-BASED TRADE CONSTRAINTS (you MUST set target/stop-loss within these ranges) ===")
        lines.append(f"ATR(14): Rs.{constraints['atr_14']} ({constraints['atr_pct']}% of price)")
        for horizon in ["short_term", "medium_term", "long_term"]:
            h = constraints[horizon]
            sl = h["stop_loss_range"]
            tgt = h["target_range"]
            lines.append(f"  {horizon.replace('_',' ').title()} ({h['horizon']}): "
                         f"Stop-Loss Rs.{sl[0]}-{sl[1]} | Target Rs.{tgt[0]}-{tgt[1]}")

        support = [f"Rs.{s}" for s in constraints.get("support_levels", []) if s]
        resist = [f"Rs.{r}" for r in constraints.get("resistance_levels", []) if r]
        if support:
            lines.append(f"  Key Support: {', '.join(support)}")
        if resist:
            lines.append(f"  Key Resistance: {', '.join(resist)}")

    return "\n".join(lines)


def format_technical_numbers_for_ai(indicators: Dict[str, Any]) -> str:
    """Compact key numbers for Gemini: one block of critical metrics for decision-making.
    
    Use alongside the full format_indicators_for_prompt so the model has both
    narrative and crisp numeric summary.
    """
    if not indicators:
        return ""

    scorecard = compute_signal_scorecard(indicators)
    constraints = compute_trade_constraints(indicators)

    lines = [
        "KEY_NUMBERS (use these for your decision):",
        f"current_price={indicators.get('current_price')}",
        f"rsi_14={indicators.get('rsi_14')} rsi_signal={indicators.get('rsi_signal')}",
        f"macd_crossover={indicators.get('macd_crossover')}",
        f"above_200_sma={indicators.get('above_200_sma')} golden_cross={indicators.get('golden_cross')}",
        f"scorecard_net_bias={scorecard['net_bias']} bullish={scorecard['bullish']} bearish={scorecard['bearish']} neutral={scorecard['neutral']}",
        f"atr_14={indicators.get('atr_14')} volume_ratio={indicators.get('volume_ratio')}",
        f"change_5d={indicators.get('change_5d')} change_20d={indicators.get('change_20d')}",
    ]
    if constraints:
        st = constraints.get("short_term", {})
        mt = constraints.get("medium_term", {})
        lt = constraints.get("long_term", {})
        lines.append(f"short_term_stop_range={st.get('stop_loss_range')} short_term_target_range={st.get('target_range')}")
        lines.append(f"medium_term_stop_range={mt.get('stop_loss_range')} medium_term_target_range={mt.get('target_range')}")
        lines.append(f"long_term_stop_range={lt.get('stop_loss_range')} long_term_target_range={lt.get('target_range')}")
    return "\n".join(lines)
