"""Technical indicator calculations using pandas-ta.

Takes raw OHLCV candle data from Upstox and computes indicators
that get fed into the AI analysis prompt.

Designed for daily profit-booking in Indian markets (NSE/BSE).
Includes intraday-critical indicators: Pivot Points, CPR,
Supertrend, Fibonacci retracements, gap analysis, and OBV.
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
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


# ---------------------------------------------------------------------------
# Pivot Points & CPR (Central Pivot Range)
# ---------------------------------------------------------------------------
def _compute_pivot_points(prev_high: float, prev_low: float, prev_close: float) -> Dict[str, float]:
    """Classic pivot points + CPR from previous day's OHLC."""
    pp = (prev_high + prev_low + prev_close) / 3.0
    bc = (prev_high + prev_low) / 2.0  # Bottom CPR
    tc = 2 * pp - bc                    # Top CPR

    r1 = 2 * pp - prev_low
    s1 = 2 * pp - prev_high
    r2 = pp + (prev_high - prev_low)
    s2 = pp - (prev_high - prev_low)
    r3 = prev_high + 2 * (pp - prev_low)
    s3 = prev_low - 2 * (prev_high - pp)

    return {
        "pivot": round(pp, 2),
        "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2),
        "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2),
        "cpr_top": round(tc, 2), "cpr_bottom": round(bc, 2),
        "cpr_width_pct": round(abs(tc - bc) / pp * 100, 2),
    }


# ---------------------------------------------------------------------------
# Fibonacci Retracement
# ---------------------------------------------------------------------------
def _compute_fibonacci(df: pd.DataFrame, lookback: int = 50) -> Dict[str, float]:
    """Fibonacci retracement from the most recent swing high/low."""
    recent = df.tail(lookback)
    swing_high = float(recent["high"].max())
    swing_low = float(recent["low"].min())
    diff = swing_high - swing_low

    if diff <= 0:
        return {}

    return {
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "fib_236": round(swing_high - 0.236 * diff, 2),
        "fib_382": round(swing_high - 0.382 * diff, 2),
        "fib_500": round(swing_high - 0.500 * diff, 2),
        "fib_618": round(swing_high - 0.618 * diff, 2),
        "fib_786": round(swing_high - 0.786 * diff, 2),
    }


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
        prev = df.iloc[-2] if len(df) >= 2 else latest

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

        # --- Previous Day Levels (critical for daily trading) ---
        result["prev_close"] = round(float(prev["close"]), 2)
        result["prev_high"] = round(float(prev["high"]), 2)
        result["prev_low"] = round(float(prev["low"]), 2)
        result["prev_open"] = round(float(prev["open"]), 2)

        # Gap analysis
        gap = float(latest["open"]) - float(prev["close"])
        gap_pct = (gap / float(prev["close"])) * 100 if float(prev["close"]) > 0 else 0
        result["gap"] = round(gap, 2)
        result["gap_pct"] = round(gap_pct, 2)
        if abs(gap_pct) > 1.0:
            result["gap_type"] = "gap_up" if gap > 0 else "gap_down"
        else:
            result["gap_type"] = "flat_open"

        # Day range analysis
        day_range = float(latest["high"]) - float(latest["low"])
        result["day_range"] = round(day_range, 2)
        body = abs(float(latest["close"]) - float(latest["open"]))
        result["body_to_range"] = round(body / day_range * 100, 1) if day_range > 0 else 0

        # --- Pivot Points & CPR ---
        pivot_data = _compute_pivot_points(float(prev["high"]), float(prev["low"]), float(prev["close"]))
        result.update({f"pivot_{k}": v for k, v in pivot_data.items()})

        # --- Fibonacci Retracement ---
        fib_data = _compute_fibonacci(df, lookback=50)
        result.update({f"fib_{k}" if not k.startswith("fib_") else k: v for k, v in fib_data.items()})

        # --- Moving Averages ---
        ema_9 = ta.ema(df["close"], length=9)
        ema_21 = ta.ema(df["close"], length=21)
        sma_20 = ta.sma(df["close"], length=20)
        sma_50 = ta.sma(df["close"], length=50)
        sma_200 = ta.sma(df["close"], length=200)
        ema_12 = ta.ema(df["close"], length=12)
        ema_26 = ta.ema(df["close"], length=26)

        result["ema_9"] = round(float(ema_9.iloc[-1]), 2) if ema_9 is not None and not ema_9.empty else None
        result["ema_21"] = round(float(ema_21.iloc[-1]), 2) if ema_21 is not None and not ema_21.empty else None
        result["sma_20"] = round(float(sma_20.iloc[-1]), 2) if sma_20 is not None and not sma_20.empty else None
        result["sma_50"] = round(float(sma_50.iloc[-1]), 2) if sma_50 is not None and not sma_50.empty else None
        result["sma_200"] = round(float(sma_200.iloc[-1]), 2) if sma_200 is not None and not sma_200.empty else None
        result["ema_12"] = round(float(ema_12.iloc[-1]), 2) if ema_12 is not None and not ema_12.empty else None
        result["ema_26"] = round(float(ema_26.iloc[-1]), 2) if ema_26 is not None and not ema_26.empty else None

        # EMA 9/21 crossover (short-term trading signal)
        if result["ema_9"] and result["ema_21"]:
            result["ema_9_21_cross"] = "bullish" if result["ema_9"] > result["ema_21"] else "bearish"
            prev_ema_9 = float(ema_9.iloc[-2]) if len(ema_9) >= 2 else None
            prev_ema_21 = float(ema_21.iloc[-2]) if len(ema_21) >= 2 else None
            if prev_ema_9 and prev_ema_21:
                if prev_ema_9 <= prev_ema_21 and result["ema_9"] > result["ema_21"]:
                    result["ema_9_21_cross_event"] = "fresh_bullish_cross"
                elif prev_ema_9 >= prev_ema_21 and result["ema_9"] < result["ema_21"]:
                    result["ema_9_21_cross_event"] = "fresh_bearish_cross"

        # Price vs MAs
        price = latest["close"]
        if result["sma_200"]:
            result["above_200_sma"] = price > result["sma_200"]
        if result["sma_50"]:
            result["above_50_sma"] = price > result["sma_50"]
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
            elif result["rsi_14"] > 60:
                result["rsi_signal"] = "bullish_zone"
            elif result["rsi_14"] < 40:
                result["rsi_signal"] = "bearish_zone"
            else:
                result["rsi_signal"] = "neutral"

            # RSI divergence (price making higher high but RSI making lower high)
            if len(df) >= 10:
                price_5d_trend = float(latest["close"]) - float(df.iloc[-5]["close"])
                rsi_5d_trend = float(rsi.iloc[-1]) - float(rsi.iloc[-5])
                if price_5d_trend > 0 and rsi_5d_trend < -5:
                    result["rsi_divergence"] = "bearish_divergence"
                elif price_5d_trend < 0 and rsi_5d_trend > 5:
                    result["rsi_divergence"] = "bullish_divergence"

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
                # Histogram expansion/contraction
                if len(macd_df) >= 2:
                    prev_hist = macd_df.iloc[-2].get("MACDh_12_26_9")
                    if pd.notna(prev_hist) and pd.notna(histogram):
                        if abs(float(histogram)) > abs(float(prev_hist)):
                            result["macd_momentum"] = "expanding"
                        else:
                            result["macd_momentum"] = "contracting"

        # --- Bollinger Bands ---
        bb = ta.bbands(df["close"], length=20, std=2)
        if bb is not None and not bb.empty:
            result["bb_upper"] = round(float(bb.iloc[-1].get("BBU_20_2.0", 0)), 2)
            result["bb_middle"] = round(float(bb.iloc[-1].get("BBM_20_2.0", 0)), 2)
            result["bb_lower"] = round(float(bb.iloc[-1].get("BBL_20_2.0", 0)), 2)
            bb_width = result["bb_upper"] - result["bb_lower"]
            if bb_width > 0:
                result["bb_pct_b"] = round((float(price) - result["bb_lower"]) / bb_width * 100, 1)
                result["bb_squeeze"] = bb_width / result["bb_middle"] * 100 < 4  # tight squeeze

        # --- ATR ---
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        if atr is not None and not atr.empty:
            result["atr_14"] = round(float(atr.iloc[-1]), 2)
            result["atr_pct"] = round(float(atr.iloc[-1]) / float(price) * 100, 2) if float(price) > 0 else 0

        # --- Volume Analysis ---
        vol_sma_20 = ta.sma(df["volume"].astype(float), length=20)
        if vol_sma_20 is not None and not vol_sma_20.empty:
            avg_vol = float(vol_sma_20.iloc[-1])
            result["volume_avg_20"] = int(avg_vol)
            result["volume_ratio"] = round(float(latest["volume"]) / avg_vol, 2) if avg_vol > 0 else 1.0
            # Volume trend (is volume increasing or decreasing)
            if len(vol_sma_20) >= 5:
                vol_5d_ago = float(vol_sma_20.iloc[-5])
                if vol_5d_ago > 0:
                    result["volume_trend"] = "increasing" if avg_vol > vol_5d_ago * 1.1 else "decreasing" if avg_vol < vol_5d_ago * 0.9 else "steady"

        # --- OBV (On-Balance Volume) ---
        obv = ta.obv(df["close"], df["volume"])
        if obv is not None and not obv.empty:
            result["obv"] = int(obv.iloc[-1])
            obv_sma = ta.sma(obv, length=20)
            if obv_sma is not None and not obv_sma.empty:
                result["obv_signal"] = "accumulation" if float(obv.iloc[-1]) > float(obv_sma.iloc[-1]) else "distribution"

        # --- ADX ---
        adx = ta.adx(df["high"], df["low"], df["close"], length=14)
        if adx is not None and not adx.empty:
            adx_val = adx.iloc[-1].get("ADX_14")
            dmp = adx.iloc[-1].get("DMP_14")
            dmn = adx.iloc[-1].get("DMN_14")
            if pd.notna(adx_val):
                result["adx_14"] = round(float(adx_val), 1)
                result["trend_strength"] = "strong" if result["adx_14"] > 25 else "weak" if result["adx_14"] < 20 else "moderate"
            if pd.notna(dmp) and pd.notna(dmn):
                result["di_plus"] = round(float(dmp), 1)
                result["di_minus"] = round(float(dmn), 1)
                result["di_signal"] = "bullish" if float(dmp) > float(dmn) else "bearish"

        # --- Supertrend ---
        st = ta.supertrend(df["high"], df["low"], df["close"], length=10, multiplier=3)
        if st is not None and not st.empty:
            st_col = [c for c in st.columns if c.startswith("SUPERTd")]
            if st_col:
                st_val = st.iloc[-1][st_col[0]]
                result["supertrend_signal"] = "bullish" if int(st_val) == 1 else "bearish"
            st_line_col = [c for c in st.columns if c.startswith("SUPERT_") and "d" not in c.lower()]
            if st_line_col:
                result["supertrend_level"] = round(float(st.iloc[-1][st_line_col[0]]), 2)

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
            result["change_1d"] = round(float((price - prev["close"]) / prev["close"] * 100), 2)
            result["change_5d"] = round(float((price - df.iloc[-5]["close"]) / df.iloc[-5]["close"] * 100), 2)
        if len(df) >= 20:
            result["change_20d"] = round(float((price - df.iloc[-20]["close"]) / df.iloc[-20]["close"] * 100), 2)
        if len(df) >= 60:
            result["change_60d"] = round(float((price - df.iloc[-60]["close"]) / df.iloc[-60]["close"] * 100), 2)

        # --- Weekly trend context (from daily data) ---
        if len(df) >= 10:
            week_df = df.tail(5)
            result["weekly_high"] = round(float(week_df["high"].max()), 2)
            result["weekly_low"] = round(float(week_df["low"].min()), 2)
            result["weekly_range_pct"] = round(
                (float(week_df["high"].max()) - float(week_df["low"].min())) / float(week_df["low"].min()) * 100, 2
            )
            result["weekly_close_vs_open"] = "bullish" if float(latest["close"]) > float(week_df.iloc[0]["open"]) else "bearish"

        # --- Candle pattern detection (last candle) ---
        o, h, l, c = float(latest["open"]), float(latest["high"]), float(latest["low"]), float(latest["close"])
        body_size = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        total_range = h - l
        if total_range > 0:
            if body_size / total_range < 0.1 and lower_wick > 2 * body_size:
                result["candle_pattern"] = "hammer" if c > o else "hanging_man"
            elif body_size / total_range < 0.1 and upper_wick > 2 * body_size:
                result["candle_pattern"] = "inverted_hammer" if c < o else "shooting_star"
            elif body_size / total_range < 0.05:
                result["candle_pattern"] = "doji"
            elif body_size / total_range > 0.7:
                result["candle_pattern"] = "strong_bullish" if c > o else "strong_bearish"
            else:
                result["candle_pattern"] = "indecisive"

        logger.info(f"Computed {len(result)} technical indicators")
        return result

    except Exception as e:
        logger.error(f"Indicator computation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Signal Scorecard (weighted)
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS = {
    "supertrend": 2.0,
    "ema_9_21_cross": 1.5,
    "macd": 1.5,
    "rsi": 1.0,
    "price_vs_200sma": 1.0,
    "ma_cross": 1.0,
    "di_signal": 1.5,
    "bollinger": 0.8,
    "volume": 1.0,
    "obv": 1.2,
    "trend_strength": 0.5,
    "candle_pattern": 0.8,
    "rsi_divergence": 1.5,
    "macd_momentum": 0.8,
    "weekly_trend": 0.8,
}


def compute_signal_scorecard(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """Weighted signal scorecard producing a score from -100 (max bearish) to +100 (max bullish).

    Each signal has a weight. Bullish signals add weight, bearish subtract, neutral = 0.
    The raw score is normalized to -100..+100 range.
    """
    signals: List[Tuple[str, str, float]] = []  # (name, verdict, weight)

    def add(name, verdict):
        w = SIGNAL_WEIGHTS.get(name, 1.0)
        signals.append((name, verdict, w))

    # 1. Supertrend
    st = indicators.get("supertrend_signal")
    if st:
        add("supertrend", st)

    # 2. EMA 9/21 cross
    ema_cross = indicators.get("ema_9_21_cross")
    if ema_cross:
        add("ema_9_21_cross", ema_cross)

    # 3. Price vs 200-SMA
    if indicators.get("above_200_sma") is not None:
        add("price_vs_200sma", "bullish" if indicators["above_200_sma"] else "bearish")

    # 4. Golden/Death cross
    if indicators.get("golden_cross") is not None:
        add("ma_cross", "bullish" if indicators["golden_cross"] else "bearish")

    # 5. RSI
    rsi_sig = indicators.get("rsi_signal")
    if rsi_sig == "overbought":
        add("rsi", "bearish")
    elif rsi_sig == "oversold":
        add("rsi", "bullish")
    elif rsi_sig == "bullish_zone":
        add("rsi", "bullish")
    elif rsi_sig == "bearish_zone":
        add("rsi", "bearish")
    else:
        add("rsi", "neutral")

    # 6. RSI divergence (high weight)
    div = indicators.get("rsi_divergence")
    if div == "bullish_divergence":
        add("rsi_divergence", "bullish")
    elif div == "bearish_divergence":
        add("rsi_divergence", "bearish")

    # 7. MACD crossover
    macd_co = indicators.get("macd_crossover")
    if macd_co:
        add("macd", macd_co)

    # 8. MACD momentum (expanding/contracting)
    macd_mom = indicators.get("macd_momentum")
    if macd_mom and macd_co:
        if macd_mom == "expanding" and macd_co == "bullish":
            add("macd_momentum", "bullish")
        elif macd_mom == "expanding" and macd_co == "bearish":
            add("macd_momentum", "bearish")
        else:
            add("macd_momentum", "neutral")

    # 9. DI signal
    di_sig = indicators.get("di_signal")
    if di_sig:
        add("di_signal", di_sig)

    # 10. Bollinger position
    bb_pct_b = indicators.get("bb_pct_b")
    if bb_pct_b is not None:
        if bb_pct_b >= 95:
            add("bollinger", "bearish")
        elif bb_pct_b <= 5:
            add("bollinger", "bullish")
        elif bb_pct_b >= 80:
            add("bollinger", "bearish")
        elif bb_pct_b <= 20:
            add("bollinger", "bullish")
        else:
            add("bollinger", "neutral")

    # 11. Volume
    vol_ratio = indicators.get("volume_ratio")
    if vol_ratio is not None:
        change_1d = indicators.get("change_1d", 0)
        if vol_ratio >= 1.5 and change_1d > 0:
            add("volume", "bullish")
        elif vol_ratio >= 1.5 and change_1d < 0:
            add("volume", "bearish")
        elif vol_ratio <= 0.5:
            add("volume", "neutral")
        else:
            add("volume", "neutral")

    # 12. OBV signal
    obv_sig = indicators.get("obv_signal")
    if obv_sig:
        add("obv", "bullish" if obv_sig == "accumulation" else "bearish")

    # 13. ADX trend strength
    adx = indicators.get("adx_14")
    if adx is not None:
        add("trend_strength", "bullish" if adx > 25 else "neutral")

    # 14. Candle pattern
    cp = indicators.get("candle_pattern")
    if cp:
        if cp in ("hammer", "strong_bullish"):
            add("candle_pattern", "bullish")
        elif cp in ("shooting_star", "hanging_man", "strong_bearish"):
            add("candle_pattern", "bearish")
        else:
            add("candle_pattern", "neutral")

    # 15. Weekly trend context
    wt = indicators.get("weekly_close_vs_open")
    if wt:
        add("weekly_trend", wt)

    # Compute weighted score
    bullish_w = sum(w for _, v, w in signals if v == "bullish")
    bearish_w = sum(w for _, v, w in signals if v == "bearish")
    total_w = sum(w for _, _, w in signals)

    bullish_count = sum(1 for _, v, _ in signals if v == "bullish")
    bearish_count = sum(1 for _, v, _ in signals if v == "bearish")
    neutral_count = sum(1 for _, v, _ in signals if v == "neutral")

    if total_w > 0:
        raw_score = ((bullish_w - bearish_w) / total_w) * 100
    else:
        raw_score = 0

    raw_score = max(-100, min(100, raw_score))

    if raw_score >= 30:
        net = "bullish"
    elif raw_score <= -30:
        net = "bearish"
    elif raw_score >= 10:
        net = "mildly_bullish"
    elif raw_score <= -10:
        net = "mildly_bearish"
    else:
        net = "neutral"

    return {
        "signals": [(n, v) for n, v, _ in signals],
        "bullish": bullish_count,
        "bearish": bearish_count,
        "neutral": neutral_count,
        "total": len(signals),
        "score": round(raw_score, 1),
        "net_bias": net,
    }


def compute_trade_constraints(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """ATR-based target/stop-loss ranges per trade horizon."""
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
        "support_levels": sorted(
            [v for v in [
                indicators.get("sma_50"),
                indicators.get("sma_200"),
                indicators.get("bb_lower"),
                indicators.get("pivot_s1"),
                indicators.get("pivot_s2"),
                indicators.get("supertrend_level") if indicators.get("supertrend_signal") == "bullish" else None,
                indicators.get("fib_618") if indicators.get("fib_618") and indicators.get("fib_618") < price else None,
            ] if v is not None], reverse=True
        ),
        "resistance_levels": sorted(
            [v for v in [
                indicators.get("bb_upper"),
                indicators.get("high_52w"),
                indicators.get("pivot_r1"),
                indicators.get("pivot_r2"),
                indicators.get("supertrend_level") if indicators.get("supertrend_signal") == "bearish" else None,
                indicators.get("fib_382") if indicators.get("fib_382") and indicators.get("fib_382") > price else None,
            ] if v is not None]
        ),
    }


def format_indicators_for_prompt(indicators: Dict[str, Any]) -> str:
    """Format computed indicators into a structured block for the AI prompt.

    Includes pivot points, Fibonacci, Supertrend, gap analysis, scorecard,
    and ATR-based constraints.
    """
    if not indicators:
        return "Technical indicator data unavailable."

    lines = []

    # --- Price & Gap ---
    lines.append("=== PRICE DATA ===")
    live_ltp = indicators.get("live_ltp")
    if live_ltp:
        lines.append(f"Current Price (LIVE): Rs.{indicators.get('current_price', 'N/A')} (intraday {indicators.get('live_change_pct', 0):+.2f}% from prev close Rs.{indicators.get('prev_day_close', 'N/A')})")
    else:
        lines.append(f"Current Price (last close): Rs.{indicators.get('current_price', 'N/A')}")
    lines.append(f"Day OHLC: O={indicators.get('day_open')} H={indicators.get('day_high')} L={indicators.get('day_low')} C={indicators.get('current_price')}")
    lines.append(f"Previous Day: O={indicators.get('prev_open')} H={indicators.get('prev_high')} L={indicators.get('prev_low')} C={indicators.get('prev_close')}")
    lines.append(f"Gap: Rs.{indicators.get('gap', 0)} ({indicators.get('gap_pct', 0)}%) — {indicators.get('gap_type', 'N/A')}")
    lines.append(f"Day Range: Rs.{indicators.get('day_range', 'N/A')} | Body/Range: {indicators.get('body_to_range', 'N/A')}%")
    lines.append(f"52-Week Range: Rs.{indicators.get('low_52w', 'N/A')} – Rs.{indicators.get('high_52w', 'N/A')} ({indicators.get('pct_from_52w_high', 'N/A')}% from high)")

    vol = indicators.get('volume', 'N/A')
    avg_vol = indicators.get('volume_avg_20', 'N/A')
    vol_str = f"{vol:,}" if isinstance(vol, int) else str(vol)
    avg_vol_str = f"{avg_vol:,}" if isinstance(avg_vol, int) else str(avg_vol)
    lines.append(f"Volume: {vol_str} (20d avg {avg_vol_str}, ratio: {indicators.get('volume_ratio', 'N/A')}x, trend: {indicators.get('volume_trend', 'N/A')})")

    cp = indicators.get("candle_pattern")
    if cp:
        lines.append(f"Last Candle: {cp.replace('_', ' ')}")

    if indicators.get("change_1d") is not None:
        lines.append(f"Price Change: 1d={indicators.get('change_1d')}% | 5d={indicators.get('change_5d')}% | 20d={indicators.get('change_20d', 'N/A')}% | 60d={indicators.get('change_60d', 'N/A')}%")

    # --- Pivot Points & CPR ---
    lines.append("")
    lines.append("=== PIVOT POINTS & CPR (key intraday/daily levels) ===")
    lines.append(f"Pivot: Rs.{indicators.get('pivot_pivot', 'N/A')}")
    lines.append(f"R1={indicators.get('pivot_r1', 'N/A')} R2={indicators.get('pivot_r2', 'N/A')} R3={indicators.get('pivot_r3', 'N/A')}")
    lines.append(f"S1={indicators.get('pivot_s1', 'N/A')} S2={indicators.get('pivot_s2', 'N/A')} S3={indicators.get('pivot_s3', 'N/A')}")
    lines.append(f"CPR: Top={indicators.get('pivot_cpr_top', 'N/A')} Bottom={indicators.get('pivot_cpr_bottom', 'N/A')} Width={indicators.get('pivot_cpr_width_pct', 'N/A')}%")
    cpr_w = indicators.get("pivot_cpr_width_pct", 0)
    if cpr_w > 0:
        lines.append(f"CPR Interpretation: {'WIDE (trending day likely)' if cpr_w > 0.5 else 'NARROW (range-bound day likely — breakout potential)'}")

    # --- Fibonacci ---
    if indicators.get("swing_high"):
        lines.append("")
        lines.append("=== FIBONACCI RETRACEMENT (50-day swing) ===")
        lines.append(f"Swing: Rs.{indicators.get('swing_low')} – Rs.{indicators.get('swing_high')}")
        lines.append(f"23.6%={indicators.get('fib_236')} | 38.2%={indicators.get('fib_382')} | 50%={indicators.get('fib_500')} | 61.8%={indicators.get('fib_618')} | 78.6%={indicators.get('fib_786')}")

    # --- Moving Averages ---
    lines.append("")
    lines.append("=== MOVING AVERAGES ===")
    lines.append(f"EMA: 9d={indicators.get('ema_9', 'N/A')} | 21d={indicators.get('ema_21', 'N/A')} | 12d={indicators.get('ema_12', 'N/A')} | 26d={indicators.get('ema_26', 'N/A')}")
    lines.append(f"SMA: 20d={indicators.get('sma_20', 'N/A')} | 50d={indicators.get('sma_50', 'N/A')} | 200d={indicators.get('sma_200', 'N/A')}")
    ema_cross = indicators.get("ema_9_21_cross")
    if ema_cross:
        event = indicators.get("ema_9_21_cross_event", "")
        lines.append(f"EMA 9/21 Cross: {ema_cross.upper()}{' *** ' + event.upper().replace('_', ' ') + ' ***' if event else ''}")
    if indicators.get("above_200_sma") is not None:
        lines.append(f"Price {'ABOVE' if indicators['above_200_sma'] else 'BELOW'} 200-SMA | {'ABOVE' if indicators.get('above_50_sma') else 'BELOW'} 50-SMA")
    if indicators.get("golden_cross") is not None:
        lines.append(f"{'Golden Cross (50>200 SMA) — BULLISH structure' if indicators['golden_cross'] else 'Death Cross (50<200 SMA) — BEARISH structure'}")

    # --- Momentum ---
    lines.append("")
    lines.append("=== MOMENTUM INDICATORS ===")
    lines.append(f"RSI(14): {indicators.get('rsi_14', 'N/A')} [{indicators.get('rsi_signal', 'N/A')}]")
    div = indicators.get("rsi_divergence")
    if div:
        lines.append(f"  *** RSI DIVERGENCE: {div.upper().replace('_', ' ')} *** (price & RSI moving in opposite directions)")
    if indicators.get("macd_line") is not None:
        lines.append(f"MACD: Line={indicators['macd_line']} Signal={indicators.get('macd_signal', 'N/A')} Hist={indicators.get('macd_histogram', 'N/A')} [{indicators.get('macd_crossover', 'N/A')}] momentum={indicators.get('macd_momentum', 'N/A')}")
    if indicators.get("stoch_rsi_k") is not None:
        lines.append(f"Stochastic RSI: %K={indicators['stoch_rsi_k']} %D={indicators.get('stoch_rsi_d', 'N/A')}")
    if indicators.get("adx_14") is not None:
        lines.append(f"ADX(14): {indicators['adx_14']} [trend: {indicators.get('trend_strength', 'N/A')}] | DI+={indicators.get('di_plus', 'N/A')} DI-={indicators.get('di_minus', 'N/A')} [{indicators.get('di_signal', 'N/A')}]")
    st_sig = indicators.get("supertrend_signal")
    if st_sig:
        lines.append(f"Supertrend(10,3): {st_sig.upper()} | Level: Rs.{indicators.get('supertrend_level', 'N/A')}")

    # --- Volume & OBV ---
    lines.append("")
    lines.append("=== VOLUME & OBV ===")
    obv_sig = indicators.get("obv_signal")
    if obv_sig:
        lines.append(f"OBV Signal: {obv_sig.upper()} (smart money {'buying' if obv_sig == 'accumulation' else 'selling'})")

    # --- Volatility ---
    lines.append("")
    lines.append("=== VOLATILITY ===")
    if indicators.get("bb_upper") is not None:
        lines.append(f"Bollinger: Upper={indicators['bb_upper']} Mid={indicators['bb_middle']} Lower={indicators['bb_lower']}")
        lines.append(f"  %B={indicators.get('bb_pct_b', 'N/A')}% | Squeeze: {'YES — expect breakout' if indicators.get('bb_squeeze') else 'No'}")
    if indicators.get("atr_14") is not None:
        lines.append(f"ATR(14): Rs.{indicators['atr_14']} ({indicators.get('atr_pct', 'N/A')}% of price)")

    # --- Weekly Context ---
    if indicators.get("weekly_high"):
        lines.append("")
        lines.append("=== WEEKLY CONTEXT ===")
        lines.append(f"Week Range: Rs.{indicators['weekly_low']} – Rs.{indicators['weekly_high']} ({indicators.get('weekly_range_pct', 'N/A')}%)")
        lines.append(f"Week Bias: {indicators.get('weekly_close_vs_open', 'N/A').upper()}")

    # --- Signal Scorecard ---
    scorecard = compute_signal_scorecard(indicators)
    lines.append("")
    lines.append("=== SIGNAL SCORECARD ===")
    lines.append(f"SCORE: {scorecard['score']:+.1f}/100 → {scorecard['net_bias'].upper()} ({scorecard['bullish']} bullish / {scorecard['bearish']} bearish / {scorecard['neutral']} neutral out of {scorecard['total']})")
    for name, verdict in scorecard["signals"]:
        marker = "+" if verdict == "bullish" else "-" if verdict == "bearish" else "~"
        lines.append(f"  [{marker}] {name}: {verdict}")

    # --- Trade Constraints ---
    constraints = compute_trade_constraints(indicators)
    if constraints:
        lines.append("")
        lines.append("=== ATR-BASED TRADE CONSTRAINTS (target/stop-loss MUST be within these ranges) ===")
        lines.append(f"ATR(14): Rs.{constraints['atr_14']} ({constraints['atr_pct']}% of price)")
        for horizon in ["short_term", "medium_term", "long_term"]:
            h = constraints[horizon]
            sl = h["stop_loss_range"]
            tgt = h["target_range"]
            lines.append(f"  {horizon.replace('_', ' ').title()} ({h['horizon']}): SL Rs.{sl[0]}–{sl[1]} | Target Rs.{tgt[0]}–{tgt[1]}")

        support = [f"Rs.{s}" for s in constraints.get("support_levels", []) if s]
        resist = [f"Rs.{r}" for r in constraints.get("resistance_levels", []) if r]
        if support:
            lines.append(f"  Key Support: {', '.join(support)}")
        if resist:
            lines.append(f"  Key Resistance: {', '.join(resist)}")

    return "\n".join(lines)


def format_technical_numbers_for_ai(indicators: Dict[str, Any]) -> str:
    """Compact key-number block for Gemini to anchor decisions on."""
    if not indicators:
        return ""

    scorecard = compute_signal_scorecard(indicators)
    constraints = compute_trade_constraints(indicators)

    live_ltp = indicators.get("live_ltp")
    prev_day_close = indicators.get("prev_day_close")
    live_line = ""
    if live_ltp and prev_day_close:
        live_line = f"live_ltp={live_ltp} (prev_close={prev_day_close}, intraday_change={indicators.get('live_change_pct')}%)"
    lines = [
        "KEY_NUMBERS (anchor your decision on these):",
        f"current_price={indicators.get('current_price')}" + (f"  <<LIVE>>" if live_ltp else "  (last candle close)"),
        live_line,
        f"prev_close={indicators.get('prev_close')} gap={indicators.get('gap')} gap_type={indicators.get('gap_type')}",
        f"rsi_14={indicators.get('rsi_14')} rsi_signal={indicators.get('rsi_signal')} rsi_divergence={indicators.get('rsi_divergence', 'none')}",
        f"macd_crossover={indicators.get('macd_crossover')} macd_momentum={indicators.get('macd_momentum')}",
        f"ema_9_21_cross={indicators.get('ema_9_21_cross')} ema_cross_event={indicators.get('ema_9_21_cross_event', 'none')}",
        f"supertrend={indicators.get('supertrend_signal')} supertrend_level={indicators.get('supertrend_level')}",
        f"above_200_sma={indicators.get('above_200_sma')} golden_cross={indicators.get('golden_cross')}",
        f"di_signal={indicators.get('di_signal')} adx={indicators.get('adx_14')}",
        f"obv_signal={indicators.get('obv_signal')} volume_ratio={indicators.get('volume_ratio')}",
        f"bb_pct_b={indicators.get('bb_pct_b')} bb_squeeze={indicators.get('bb_squeeze')}",
        f"candle={indicators.get('candle_pattern')}",
        f"pivot={indicators.get('pivot_pivot')} R1={indicators.get('pivot_r1')} S1={indicators.get('pivot_s1')}",
        f"scorecard_score={scorecard['score']} net_bias={scorecard['net_bias']}",
        f"atr_14={indicators.get('atr_14')} atr_pct={indicators.get('atr_pct')}",
        f"change_1d={indicators.get('change_1d')} change_5d={indicators.get('change_5d')} change_20d={indicators.get('change_20d')}",
    ]
    lines = [l for l in lines if l]
    if constraints:
        st = constraints.get("short_term", {})
        mt = constraints.get("medium_term", {})
        lines.append(f"short_term_SL={st.get('stop_loss_range')} short_term_target={st.get('target_range')}")
        lines.append(f"medium_term_SL={mt.get('stop_loss_range')} medium_term_target={mt.get('target_range')}")
    return "\n".join(lines)
