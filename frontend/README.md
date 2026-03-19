# Frontend — Desi Algo Trade

React UI for the Desi Algo Trade AI Trading Agent. Built with React 19, React Router, Tailwind CSS, shadcn/ui, Framer Motion, and Recharts.

---

## Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | **Agent** | Conversational AI agent — the primary interface for briefings, stock discovery, analysis, trade signals, and portfolio management through natural language. |
| `/research` | **Research** | Stock browser with live prices, sector filter, and AI analysis panel. Run individual analyses or scan all stocks. |
| `/trades` | **Trades** | Pending BUY/SHORT/SELL signals with approve/edit/reject actions, recommendation history, executed trade log with stats. |
| `/portfolio` | **Portfolio** | Mode-scoped holdings with P&L, sector allocation pie chart, AI sell scan, and direct sell with quantity control. |
| `/sandbox` | **Sandbox** | Virtual paper trading dashboard — ₹1L virtual account, AI-driven strategy, automated scheduler control, and performance analytics. |
| `/settings` | **Settings** | Risk parameters, Gemini model selection, and Upstox connectivity status. |

---

## Setup

```bash
cd frontend
yarn install
```

Set the backend URL environment variable:

```bash
# PowerShell
$env:REACT_APP_BACKEND_URL = "http://localhost:8000"

# Bash
export REACT_APP_BACKEND_URL=http://localhost:8000
```

Start development server:

```bash
yarn start
```

App runs at **http://localhost:3000**.

---

## Environment

| Variable | Purpose |
|----------|--------|
| `REACT_APP_BACKEND_URL` | Backend base URL (e.g. `http://localhost:8000`). No `/api` suffix. |

---

## Key Dependencies

- **react** / **react-dom** — UI framework
- **react-router-dom** — Client-side routing
- **axios** — HTTP client for API calls
- **tailwindcss** — Utility-first CSS
- **framer-motion** — Animations and transitions
- **recharts** — Charts (sector allocation pie chart)
- **lucide-react** — Icon library
- **sonner** — Toast notifications

See [SETUP.md](./SETUP.md) for detailed install and troubleshooting.
See [root README](../README.md) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for full project overview.
