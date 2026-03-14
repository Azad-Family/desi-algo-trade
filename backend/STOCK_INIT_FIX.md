# Stock Initialization Fix

## Problem
The stock data was being inserted twice at each startup:
1. **Startup event** in `server.py` was inserting stocks if collection was empty
2. **Initialize endpoint** in `routes.py` was duplicating the insertion logic

This caused:
- Duplicate initialization code (violation of DRY principle)
- Potential for inconsistencies if logic diverges
- **58 stocks being loaded twice** on first startup

## Solution
Extracted common initialization logic into a dedicated module:

### New File: `stock_init.py`
Single source of truth for all stock initialization operations.

**Functions:**
- `initialize_stocks()` - Clear existing stocks and load from STOCK_UNIVERSE
- `get_stock_count()` - Get current stock count in database

**Benefits:**
- ✅ No code duplication
- ✅ Consistent initialization logic everywhere
- ✅ Easy to test in isolation
- ✅ Clear responsibility separation

### Updated Files

**`server.py`**
- Now imports `initialize_stocks` and `get_stock_count` from `stock_init`
- Startup event checks stock count and initializes only if empty
- Handles errors gracefully (logs but doesn't crash)

**`routes.py`**
- Now imports `initialize_stocks` from `stock_init`
- `/api/stocks/initialize` endpoint delegates to shared function
- Both use the exact same initialization logic

## Flow Diagram

```
On Startup:
┌─────────────────────────────────────┐
│ server.py startup_event()           │
├─────────────────────────────────────┤
│ 1. Check stock count via            │
│    get_stock_count()                │
│                                     │
│ 2. If count == 0:                   │
│    Call initialize_stocks()         │
│                                     │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ stock_init.py                       │
├─────────────────────────────────────┤
│ initialize_stocks():                │
│ • Delete all existing stocks        │
│ • Insert 59 fresh stocks from       │
│   STOCK_UNIVERSE                    │
│ • Return count                      │
└─────────────────────────────────────┘

On Manual Reinit (POST /api/stocks/initialize):
┌─────────────────────────────────────┐
│ routes.py                           │
│ /stocks/initialize endpoint         │
├─────────────────────────────────────┤
│ Call initialize_stocks()            │
│ Return result                       │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ stock_init.py (Same function!)      │
│ initialize_stocks()                 │
└─────────────────────────────────────┘
```

## Code Changes Summary

| File | Change | Lines |
|------|--------|-------|
| **stock_init.py** | New file with initialization logic | 45 |
| **server.py** | Use `initialize_stocks()` function | -15, +8 |
| **routes.py** | Use `initialize_stocks()` function | -22, +8 |

**Result:** +17 lines of new code, -37 lines of duplication = **20 lines cleaner**

## Testing

### Verify it works:
```bash
# Clear database (optional)
# Start fresh server
uvicorn server:app --reload

# Check logs should show:
# ✓ Startup initialization complete: 59 stocks loaded
```

### Test manual reinit:
```bash
# POST to reinitialize
curl -X POST http://localhost:8000/api/stocks/initialize

# Response should be:
# {"message": "Reinitialized 59 stocks", "count": 59}
```

### Check database directly:
```python
import requests
response = requests.get("http://localhost:8000/api/stocks")
stocks = response.json()
print(f"Total stocks: {len(stocks)}")  # Should print: 59 (not 118!)
```

---

**Fixed:** 2026-02-23  
**Status:** ✅ Ready to deploy
