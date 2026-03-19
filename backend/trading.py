"""Upstox integration for trading"""
import logging
import os
import gzip
import json
from typing import Optional, Dict, Any
from urllib.parse import quote as url_quote
import httpx
import uuid as uuid_lib
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')

NSE_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

# Symbols whose trading_symbol in Upstox instrument master differs from our database symbol.
# Maps our_symbol -> ISIN-based instrument_key for request resolution.
SYMBOL_OVERRIDES = {
    "LTIM": "NSE_EQ|INE214T01019",        # Upstox uses "LTM"
    "TATAMOTORS": "NSE_EQ|INE1TAE01010",  # Demerged → Upstox uses "TMCV"
    "ZOMATO": "NSE_EQ|INE758T01015",      # Rebranded → Upstox uses "ETERNAL"
    "ADANIENSO": "NSE_EQ|INE931S01010",   # Upstox uses "ADANIENSOL"
}


class UpstoxClient:
    """Client for Upstox trading API"""
    
    _instrument_map: Dict[str, str] = {}
    _instrument_map_loaded: bool = False

    def __init__(self):
        self.sandbox = os.environ.get('UPSTOX_USE_SANDBOX', 'true').lower() == 'true'

        # Market data APIs (quotes, historical candles) are NOT sandbox-enabled,
        # so we always use live credentials for them.
        self.live_access_token = os.environ.get('UPSTOX_ACCESS_TOKEN', '')

        # Order APIs support sandbox — use sandbox credentials when enabled.
        if self.sandbox:
            self.order_access_token = os.environ.get('UPSTOX_SANDBOX_ACCESS_TOKEN', '')
            self.order_base_url = "https://api-sandbox.upstox.com/v3"
        else:
            self.order_access_token = self.live_access_token
            self.order_base_url = "https://api-hft.upstox.com/v3"

        self.base_url = "https://api.upstox.com/v3"
        self.market_quote_url = "https://api.upstox.com/v2"
        

        mode = "SANDBOX" if self.sandbox else "LIVE"
        market_hint = self.live_access_token[-8:] if self.live_access_token else "MISSING"
        order_hint = self.order_access_token[-8:] if self.order_access_token else "MISSING"
        logger.info(
            f"Upstox client initialized — order_mode: {mode}, "
            f"UPSTOX_USE_SANDBOX={os.environ.get('UPSTOX_USE_SANDBOX','<unset>')}, "
            f"market_token: ...{market_hint}, order_token: ...{order_hint}"
        )
    
    def is_configured(self) -> bool:
        """Check if Upstox credentials are configured for market data"""
        return bool(self.live_access_token)
    
    def is_market_open(self) -> Dict[str, Any]:
        """Check if NSE market is currently open
        
        NSE trading hours: 9:15 AM - 3:30 PM IST, Mon-Fri
        """
        now = datetime.now(IST)
        is_weekday = now.weekday() < 5  # Mon=0, Fri=4
        
        market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        is_open = is_weekday and market_open_time <= now <= market_close_time
        
        return {
            "is_open": is_open,
            "current_time": now.isoformat(),
            "market_open_time": "09:15 IST",
            "market_close_time": "15:30 IST",
            "trading_day": not now.weekday() >= 5  # True if Mon-Fri
        }
    
    async def _ensure_instrument_map(self):
        """Download NSE instrument master and build trading_symbol -> instrument_key map.
        Cached as a class-level dict so it's fetched only once per process."""
        if UpstoxClient._instrument_map_loaded:
            return

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(NSE_INSTRUMENTS_URL, timeout=30.0)
                if resp.status_code != 200:
                    logger.error(f"Failed to download NSE instruments: HTTP {resp.status_code}")
                    return

                raw = gzip.decompress(resp.content)
                instruments = json.loads(raw)

                for inst in instruments:
                    if inst.get("segment") == "NSE_EQ" and inst.get("instrument_type") in ("EQ", "ETF"):
                        ts = inst.get("trading_symbol", "")
                        ik = inst.get("instrument_key", "")
                        if ts and ik:
                            UpstoxClient._instrument_map[ts] = ik

                UpstoxClient._instrument_map_loaded = True
                logger.info(f"Loaded {len(UpstoxClient._instrument_map)} NSE equity instrument keys")
        except Exception as e:
            logger.error(f"Error loading instrument master: {e}")

    async def resolve_instrument_key(self, symbol: str) -> str:
        """Resolve a trading symbol to its full Upstox instrument key (ISIN-based).
        Uses SYMBOL_OVERRIDES first, then instrument map, then fallback."""
        override = SYMBOL_OVERRIDES.get(symbol.upper())
        if override:
            return override
        await self._ensure_instrument_map()
        key = UpstoxClient._instrument_map.get(symbol)
        if not key:
            logger.warning(f"No instrument key found for {symbol}, falling back to NSE_EQ|{symbol}")
            return f"NSE_EQ|{symbol}"
        return key

    async def get_market_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get real-time market quote for a stock (always uses live token)"""
        if not self.is_configured():
            return None
        
        try:
            instrument_key = await self.resolve_instrument_key(symbol)
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.live_access_token}",
                    "Accept": "application/json"
                }
                response = await client.get(
                    f"{self.market_quote_url}/market-quote/quotes",
                    params={"instrument_key": instrument_key},
                    headers=headers
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Upstox API error for {symbol}: {e}")
        return None
    
    def _extract_quote(self, quote: dict) -> dict:
        """Normalize an Upstox quote object into our internal format."""
        ltp = quote.get("last_price") or quote.get("ltp", 0)
        ohlc = quote.get("ohlc", {})
        prev_close = ohlc.get("close", 0)
        net_change = quote.get("net_change", 0)
        if prev_close and prev_close > 0:
            change_pct = (net_change / prev_close) * 100
        else:
            change_pct = 0
        return {
            "ltp": ltp,
            "change_percent": round(change_pct, 2),
            "net_change": net_change,
            "high": ohlc.get("high", 0),
            "low": ohlc.get("low", 0),
            "volume": quote.get("volume", 0),
            "oi": quote.get("oi", 0),
        }

    async def get_batch_quotes(self, symbols: list[str]) -> Dict[str, Any]:
        """Get market quotes for multiple stocks using the Upstox Full Market Quotes API.
        
        Resolves trading symbols to ISIN-based instrument keys, sends batch requests
        (up to 50 per call), and maps the response keys back to trading symbols.
        
        Upstox request:  instrument_key = NSE_EQ|INE848E01016  (ISIN-based)
        Upstox response: data key       = NSE_EQ:NHPC          (colon + trading symbol)
        """
        if not self.is_configured():
            logger.warning("Upstox not configured - cannot fetch live prices")
            return {}
        
        await self._ensure_instrument_map()
        
        # Build symbol -> instrument_key mapping for request
        sym_to_key = {}
        for symbol in symbols:
            key = await self.resolve_instrument_key(symbol)
            sym_to_key[symbol] = key
        
        # Reverse map: Upstox responds with "NSE_EQ:ACTUAL_TRADING_SYMBOL".
        # For overridden symbols, the actual trading symbol on Upstox differs
        # from our symbol (e.g. ZOMATO→ETERNAL, LTIM→LTM).
        # Build isin→actual_trading_symbol from the instrument map, then
        # map NSE_EQ:actual_trading_symbol → our_symbol.
        isin_to_ts = {ik: ts for ts, ik in UpstoxClient._instrument_map.items()}
        key_to_sym = {}
        for symbol in symbols:
            inst_key = sym_to_key[symbol]
            actual_ts = isin_to_ts.get(inst_key, symbol)
            key_to_sym[f"NSE_EQ:{actual_ts}"] = symbol
            if actual_ts != symbol:
                key_to_sym[f"NSE_EQ:{symbol}"] = symbol
        
        quotes = {}
        BATCH_SIZE = 50
        symbol_batches = [symbols[i:i+BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.live_access_token}",
                    "Accept": "application/json"
                }
                
                for batch in symbol_batches:
                    instrument_keys = [sym_to_key[s] for s in batch]
                    keys_param = ",".join(instrument_keys)
                    
                    try:
                        response = await client.get(
                            f"{self.market_quote_url}/market-quote/quotes",
                            params={"instrument_key": keys_param},
                            headers=headers,
                            timeout=15.0,
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            if data.get("status") == "success" and "data" in data and data["data"]:
                                for resp_key, quote in data["data"].items():
                                    # Map response key back to our symbol
                                    # Response key format: "NSE_EQ:SYMBOL"
                                    symbol = key_to_sym.get(resp_key)
                                    if not symbol:
                                        # Try extracting from the "symbol" field in the quote
                                        symbol = quote.get("symbol")
                                    if not symbol and ":" in resp_key:
                                        symbol = resp_key.split(":", 1)[1]
                                    if symbol and symbol in sym_to_key:
                                        quotes[symbol] = self._extract_quote(quote)
                        
                        elif response.status_code == 401:
                            logger.error("Upstox authentication failed - access token may have expired. Generate a new token.")
                            break
                        else:
                            logger.warning(f"Upstox market-quote returned {response.status_code}: {response.text[:300]}")
                    
                    except httpx.TimeoutException:
                        logger.warning(f"Timeout fetching quotes for batch of {len(batch)} stocks")
                    except Exception as e:
                        logger.error(f"Error fetching batch quote: {e}")
                
                if quotes:
                    logger.info(f"Fetched prices for {len(quotes)}/{len(symbols)} stocks")
                else:
                    logger.warning("No prices fetched - check if access token is valid and market is open")
        
        except Exception as e:
            logger.error(f"Batch quote error: {e}")
        
        return quotes
    
    async def get_historical_candles(
        self, symbol: str, unit: str = "days", interval: int = 1,
        from_date: str = None, to_date: str = None
    ) -> list:
        """Fetch historical OHLCV candle data from Upstox V3 API.
        
        Returns list of [timestamp, open, high, low, close, volume, oi] arrays.
        """
        if not self.is_configured():
            logger.warning("Upstox not configured - cannot fetch historical data")
            return []

        if not to_date:
            to_date = datetime.now(IST).strftime("%Y-%m-%d")
        if not from_date:
            if unit == "days":
                from_date = (datetime.now(IST) - timedelta(days=365)).strftime("%Y-%m-%d")
            elif unit == "weeks":
                from_date = (datetime.now(IST) - timedelta(weeks=104)).strftime("%Y-%m-%d")
            else:
                from_date = (datetime.now(IST) - timedelta(days=90)).strftime("%Y-%m-%d")

        try:
            raw_key = await self.resolve_instrument_key(symbol)
            encoded_key = url_quote(raw_key, safe="")
            url = f"{self.base_url}/historical-candle/{encoded_key}/{unit}/{interval}/{to_date}/{from_date}"
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.live_access_token}",
                    "Accept": "application/json"
                }
                response = await client.get(url, headers=headers, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    candles = data.get("data", {}).get("candles", [])
                    logger.info(f"Fetched {len(candles)} {unit} candles for {symbol}")
                    return candles
                else:
                    logger.warning(f"Historical candle API returned {response.status_code} for {symbol}: {response.text}")
        except Exception as e:
            logger.error(f"Historical candle fetch error for {symbol}: {e}")
        return []

    async def place_order(self, symbol: str, action: str, quantity: int, price: float,
                          product_type: str = "D") -> Dict[str, Any]:
        """Place an order through Upstox.

        Args:
            product_type: "D" for Delivery, "I" for Intraday (used for SHORT trades).
            action: "BUY" or "SELL". For SHORT trades, caller should pass action="SELL"
                    with product_type="I".

        Returns dict with at least: order_id, status, trade_mode.
        trade_mode is one of: "live", "sandbox", "simulated".
        """
        if not self.order_access_token:
            return {
                "status": "simulated",
                "order_id": f"SIM-{uuid_lib.uuid4().hex[:8].upper()}",
                "trade_mode": "simulated",
            }

        mode = "sandbox" if self.sandbox else "live"

        instrument_key = await self.resolve_instrument_key(symbol)

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.order_access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
                order_data = {
                    "quantity": quantity,
                    "product": product_type,
                    "validity": "DAY",
                    "price": price,
                    "instrument_token": instrument_key,
                    "order_type": "LIMIT",
                    "transaction_type": action,
                    "disclosed_quantity": 0,
                    "trigger_price": 0,
                    "is_amo": False
                }
                response = await client.post(
                    f"{self.order_base_url}/order/place",
                    json=order_data,
                    headers=headers
                )
                if response.status_code == 200:
                    result = response.json()
                    result["trade_mode"] = mode
                    return result
                else:
                    logger.warning(f"Upstox order returned {response.status_code}: {response.text[:300]}")
        except Exception as e:
            logger.error(f"Upstox order error: {e}")

        return {
            "status": "simulated",
            "order_id": f"SIM-{uuid_lib.uuid4().hex[:8].upper()}",
            "trade_mode": "simulated",
        }
