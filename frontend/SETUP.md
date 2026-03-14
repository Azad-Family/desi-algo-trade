# Frontend Setup & Troubleshooting Guide

## Quick Start

### Prerequisites
- Node 18+ installed
- Yarn package manager: https://classic.yarnpkg.com/en/docs/install

### Installation

```bash
cd frontend
yarn install
```

### Environment Configuration

The frontend needs to know where your backend API is located. Set the environment variable **before** starting:

**PowerShell:**
```powershell
$env:REACT_APP_BACKEND_URL = "http://localhost:8000"
yarn start
```

**Command Prompt (CMD):**
```cmd
set REACT_APP_BACKEND_URL=http://localhost:8000
yarn start
```

**Bash/Linux/Mac:**
```bash
export REACT_APP_BACKEND_URL=http://localhost:8000
yarn start
```

### That's It!
The app launches at: **http://localhost:3000**

---

## Environment Variables Required

### REACT_APP_BACKEND_URL (Required)
- **Default:** http://localhost:8000
- **Purpose:** Tells the frontend where the backend API is running
- **Example values:**
  - Local development: `http://localhost:8000`
  - Remote server: `https://api.mydomain.com`
  - Docker container: `http://backend:8000`

> ⚠️ **No `/api` suffix needed!** The frontend automatically appends `/api` to this URL.

---

## Troubleshooting

### Error: "Failed to load stocks"

**Check these in order:**

1. **Is the backend running?**
   ```powershell
   # Try this - should return JSON with health status
   Invoke-WebRequest http://localhost:8000/api/health
   ```

2. **Is the environment variable set?**
   ```powershell
   # Check what the frontend sees
   $env:REACT_APP_BACKEND_URL
   # Should output: http://localhost:8000
   ```

3. **Check browser console (F12 → Console tab)**
   - Look for the log: `🔌 API Configuration:`
   - Verify `API` URL is correct
   - Look for `❌ API Error Details` with full error information

4. **Common mistakes:**
   - ❌ Environment variable not set `→` ✅ Run: `$env:REACT_APP_BACKEND_URL = "http://localhost:8000"`
   - ❌ Backend not running `→` ✅ Start backend: `uvicorn server:app --reload`
   - ❌ Wrong host (127.0.0.1 vs localhost) `→` ✅ Use `localhost`
   - ❌ CORS issue `→` ✅ Check backend CORS_ORIGINS in `.env`

---

## Available Pages

Once loaded, you can navigate to:

| Page | Endpoint | Purpose |
|------|----------|---------|
| **Dashboard** | `/` | Portfolio overview & stats |
| **AI Research** | `/research` | Stock analysis & recommendations |
| **Stock Universe** | `/stocks` | Browse all 58 stocks by sector |
| **Trade Queue** | `/queue` | Pending trade approvals |
| **Portfolio** | `/portfolio` | Current holdings & P&L |
| **Trade History** | `/history` | Execution log |
| **Settings** | `/settings` | Preferences & API keys |

---

## Development Tips

### Hot Reload
Changes to `.jsx` files automatically reload in the browser.

### Debug API Calls
Open **Browser DevTools (F12)**:
1. Go to **Network** tab
2. Watch API requests come through
3. Click on request to see full response

### Test API Directly
```powershell
# Get all stocks (no auth required)
Invoke-WebRequest http://localhost:8000/api/stocks | Select -ExpandProperty Content | ConvertFrom-Json

# Get health status
Invoke-WebRequest http://localhost:8000/api/health | Select -ExpandProperty Content | ConvertFrom-Json
```

### Rebuild After npm/Security Updates
```powershell
rm -r node_modules
rm yarn.lock
yarn install
yarn start
```

---

## Production Deployment

Update environment variable for production:

```powershell
# Assuming backend is at api.mydomain.com
$env:REACT_APP_BACKEND_URL = "https://api.mydomain.com"
yarn build
# Deploy the /build folder to your hosting
```

---

## Still Having Issues?

1. **Check backend logs:**
   ```powershell
   cd backend
   uvicorn server:app --reload --log-level debug
   ```

2. **Open browser DevTools (F12):**
   - Console tab → Look for errors
   - Network tab → Watch API request to `/api/stocks`
   - Check response status (should be 2xx)

3. **Test with curl:**
   ```powershell
   Invoke-WebRequest http://localhost:8000/api/stocks
   ```

4. **Report with:**
   - Screenshot of browser console error
   - Backend log output
   - Output of running: `$env:REACT_APP_BACKEND_URL`
   - Browser address bar URL

---

**Last Updated:** 2026-02-23  
**Frontend Port:** 3000  
**Backend Port:** 8000  
**CORS Enabled:** ✓
