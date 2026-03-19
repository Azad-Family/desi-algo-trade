import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import {
  FlaskConical,
  Play,
  Square,
  RefreshCw,
  Target,
  ShieldAlert,
  BarChart3,
  Clock,
  Zap,
  RotateCcw,
  ArrowUpCircle,
  ArrowDownCircle,
  Activity,
  Award,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Scan,
  ChevronRight,
  Wallet,
  History,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const API = `${BACKEND_URL}/api/sandbox`;

const TABS = {
  OVERVIEW: "overview",
  SCREENER: "screener",
  HOLDINGS: "holdings",
  TRADES: "trades",
  STRATEGY: "strategy",
};

function fmt(n, decimals = 2) {
  if (n == null) return "-";
  return Number(n).toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

const TRADE_TYPE_STYLES = {
  BUY_CNC:        { label: "BUY CNC",        color: "text-signal-success", bg: "bg-signal-success/15 border-signal-success/30" },
  BUY_INTRADAY:   { label: "BUY INTRADAY",   color: "text-blue-400",       bg: "bg-blue-500/15 border-blue-500/30" },
  SHORT_INTRADAY:  { label: "SHORT INTRADAY",  color: "text-orange-400",     bg: "bg-orange-500/15 border-orange-500/30" },
  SELL_CNC:       { label: "SELL CNC",        color: "text-signal-danger",  bg: "bg-signal-danger/15 border-signal-danger/30" },
};

function TradeTypeBadge({ action, productType }) {
  const key = `${action}_${productType || "CNC"}`;
  const style = TRADE_TYPE_STYLES[key] || TRADE_TYPE_STYLES.BUY_CNC;
  return (
    <Badge variant="outline" className={`text-[10px] font-mono ${style.color} ${style.bg}`}>
      {style.label}
    </Badge>
  );
}

const ACCENT_BAR = {
  BUY_CNC:       "bg-signal-success",
  BUY_INTRADAY:  "bg-blue-400",
  SHORT_INTRADAY: "bg-orange-500",
  SELL_CNC:      "bg-signal-danger",
};

function PnlText({ value, className = "" }) {
  if (value == null) return <span className="text-muted-foreground">-</span>;
  const positive = value >= 0;
  return (
    <span className={`font-mono ${positive ? "text-signal-success" : "text-signal-danger"} ${className}`}>
      {positive ? "+" : ""}{fmt(value)}
    </span>
  );
}

/* ─── Account Summary Bar ─── */
function AccountBar({ account, schedulerStatus, onStart, onStop, onReset, onRefresh, loading }) {
  if (!account) return null;
  const totalVal = account.current_capital + (account.current_value || 0);
  const pnlPct = account.total_pnl_pct || 0;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-3 text-center">
          <p className="text-[10px] uppercase text-muted-foreground tracking-wider">Capital</p>
          <p className="font-mono text-lg font-semibold">₹{fmt(account.current_capital, 0)}</p>
        </CardContent>
      </Card>
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-3 text-center">
          <p className="text-[10px] uppercase text-muted-foreground tracking-wider">Invested</p>
          <p className="font-mono text-lg">₹{fmt(account.invested_value, 0)}</p>
        </CardContent>
      </Card>
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-3 text-center">
          <p className="text-[10px] uppercase text-muted-foreground tracking-wider">Total P&L</p>
          <PnlText value={account.total_pnl} className="text-lg font-semibold" />
          <p className={`text-xs ${pnlPct >= 0 ? "text-signal-success" : "text-signal-danger"}`}>
            ({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%)
          </p>
        </CardContent>
      </Card>
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-3 text-center">
          <p className="text-[10px] uppercase text-muted-foreground tracking-wider">Win Rate</p>
          <p className="font-mono text-lg">{account.win_rate || 0}%</p>
          <p className="text-xs text-muted-foreground">{account.winning_trades}W / {account.losing_trades}L</p>
        </CardContent>
      </Card>
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-3 text-center">
          <p className="text-[10px] uppercase text-muted-foreground tracking-wider">Trades</p>
          <p className="font-mono text-lg">{account.total_trades || 0}</p>
        </CardContent>
      </Card>
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-3 text-center">
          <p className="text-[10px] uppercase text-muted-foreground tracking-wider">Max Drawdown</p>
          <p className="font-mono text-lg text-signal-danger">₹{fmt(account.max_drawdown, 0)}</p>
        </CardContent>
      </Card>
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-3 flex flex-col gap-1 items-center justify-center">
          <p className="text-[10px] uppercase text-muted-foreground tracking-wider">Scheduler</p>
          <div className="flex items-center gap-1">
            <div className={`w-2 h-2 rounded-full ${schedulerStatus?.running ? "bg-signal-success animate-pulse" : "bg-muted-foreground"}`} />
            <span className="text-xs">{schedulerStatus?.running ? "Active" : "Stopped"}</span>
          </div>
          <p className="text-[9px] text-muted-foreground mt-0.5">Squareoff 15:15</p>
        </CardContent>
      </Card>
    </div>
  );
}

/* ─── Screener Results ─── */
function ScreenerPanel({ results, onRunScreener, loading }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-heading text-xl font-semibold">Stock Screener</h2>
          <p className="text-sm text-muted-foreground">
            Fast technical pre-filter — ranks all 125 stocks by momentum score
          </p>
        </div>
        <Button onClick={onRunScreener} disabled={loading} size="sm">
          <Scan className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Screening..." : "Run Screener"}
        </Button>
      </div>

      {results && (
        <div className="text-sm text-muted-foreground mb-2">
          Screened {results.total_screened || results.total_screened} stocks —{" "}
          <span className="text-signal-success">{results.buy_candidates_count ?? results.buy_candidates?.length ?? 0} BUY</span>,{" "}
          <span className="text-signal-danger">{results.short_candidates_count ?? results.short_candidates?.length ?? 0} SHORT</span> candidates
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="bg-surface-primary border-signal-success/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-signal-success">
              <ArrowUpCircle className="w-4 h-4" /> BUY Candidates
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 max-h-[400px] overflow-y-auto space-y-1">
            {(results?.buy_candidates || []).map((c, i) => (
              <div key={c.symbol} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-surface-secondary text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground w-5 text-right">{i + 1}.</span>
                  <span className="font-semibold">{c.symbol}</span>
                  <Badge variant="outline" className="text-[10px]">{c.sector}</Badge>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">RSI {c.rsi?.toFixed(0) || "-"}</span>
                  <span className={`font-mono text-xs ${(c.change_1d || 0) >= 0 ? "text-signal-success" : "text-signal-danger"}`}>
                    {c.change_1d != null ? `${c.change_1d >= 0 ? "+" : ""}${c.change_1d}%` : ""}
                  </span>
                  <Badge className="bg-signal-success/20 text-signal-success border-signal-success/30 text-xs font-mono">
                    +{c.score?.toFixed(0)}
                  </Badge>
                </div>
              </div>
            ))}
            {(!results?.buy_candidates || results.buy_candidates.length === 0) && (
              <p className="text-muted-foreground text-sm text-center py-6">No BUY candidates found</p>
            )}
          </CardContent>
        </Card>

        <Card className="bg-surface-primary border-signal-danger/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-signal-danger">
              <ArrowDownCircle className="w-4 h-4" /> SHORT Candidates
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 max-h-[400px] overflow-y-auto space-y-1">
            {(results?.short_candidates || []).map((c, i) => (
              <div key={c.symbol} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-surface-secondary text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground w-5 text-right">{i + 1}.</span>
                  <span className="font-semibold">{c.symbol}</span>
                  <Badge variant="outline" className="text-[10px]">{c.sector}</Badge>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">RSI {c.rsi?.toFixed(0) || "-"}</span>
                  <span className={`font-mono text-xs ${(c.change_1d || 0) >= 0 ? "text-signal-success" : "text-signal-danger"}`}>
                    {c.change_1d != null ? `${c.change_1d >= 0 ? "+" : ""}${c.change_1d}%` : ""}
                  </span>
                  <Badge className="bg-signal-danger/20 text-signal-danger border-signal-danger/30 text-xs font-mono">
                    {c.score?.toFixed(0)}
                  </Badge>
                </div>
              </div>
            ))}
            {(!results?.short_candidates || results.short_candidates.length === 0) && (
              <p className="text-muted-foreground text-sm text-center py-6">No SHORT candidates found</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/* ─── Holdings Panel ─── */
function HoldingsPanel({ holdings, onExit, onRefresh, loading }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-xl font-semibold">Paper Holdings</h2>
        <Button onClick={onRefresh} disabled={loading} variant="outline" size="sm">
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh Prices
        </Button>
      </div>

      {holdings.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <FlaskConical className="w-12 h-12 mx-auto mb-3 opacity-40" />
          <p>No paper holdings yet. Run a scan to start paper trading.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {holdings.map((h) => (
            <Card key={h.id} className="bg-surface-primary border-border-subtle">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-1 h-12 rounded-full ${ACCENT_BAR[`${h.action}_${h.product_type || "CNC"}`] || "bg-signal-success"}`} />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{h.stock_symbol}</span>
                        <TradeTypeBadge action={h.action} productType={h.product_type} />
                        <span className="text-xs text-muted-foreground">{h.stock_name}</span>
                      </div>
                      <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                        <span>Qty: {h.quantity}</span>
                        <span>Entry: ₹{fmt(h.entry_price)}</span>
                        <span>LTP: ₹{fmt(h.current_price)}</span>
                        {h.target_price && <span className="text-signal-success">T: ₹{fmt(h.target_price)}</span>}
                        {h.stop_loss && <span className="text-signal-danger">SL: ₹{fmt(h.stop_loss)}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <PnlText value={h.pnl} className="text-sm" />
                      <p className={`text-xs ${(h.pnl_pct || 0) >= 0 ? "text-signal-success" : "text-signal-danger"}`}>
                        {h.pnl_pct >= 0 ? "+" : ""}{(h.pnl_pct || 0).toFixed(2)}%
                      </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => onExit(h.stock_symbol)} className="text-signal-danger border-signal-danger/30 hover:bg-signal-danger/10">
                      Exit
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Trades Panel ─── */
function TradesPanel({ trades }) {
  return (
    <div className="space-y-4">
      <h2 className="font-heading text-xl font-semibold">Paper Trade History</h2>
      {trades.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Clock className="w-12 h-12 mx-auto mb-3 opacity-40" />
          <p>No completed paper trades yet</p>
        </div>
      ) : (
        <div className="space-y-1">
          {trades.map((t) => (
            <div key={t.id} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-surface-secondary border border-border-subtle bg-surface-primary text-sm">
              <div className="flex items-center gap-3">
                {t.pnl >= 0
                  ? <CheckCircle2 className="w-4 h-4 text-signal-success" />
                  : <XCircle className="w-4 h-4 text-signal-danger" />
                }
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{t.stock_symbol}</span>
                    <TradeTypeBadge action={t.action} productType={t.product_type} />
                    <Badge variant="outline" className="text-[10px]">{t.exit_reason?.replace(/_/g, " ")}</Badge>
                  </div>
                  <div className="flex gap-3 text-xs text-muted-foreground mt-0.5">
                    <span>Entry: ₹{fmt(t.entry_price)}</span>
                    <span>Exit: ₹{fmt(t.exit_price)}</span>
                    <span>Qty: {t.quantity}</span>
                    <span>{t.holding_duration_hours?.toFixed(1)}h</span>
                  </div>
                </div>
              </div>
              <div className="text-right">
                <PnlText value={t.pnl} className="text-sm" />
                <p className={`text-xs ${t.pnl_pct >= 0 ? "text-signal-success" : "text-signal-danger"}`}>
                  {t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct?.toFixed(2)}%
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Strategy Insights ─── */
function StrategyPanel({ insights }) {
  if (!insights || !insights.total_trades) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-40" />
        <p>Complete some paper trades to see strategy insights</p>
      </div>
    );
  }

  const StatCard = ({ title, icon: Icon, children }) => (
    <Card className="bg-surface-primary border-border-subtle">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Icon className="w-4 h-4 text-ai-glow" /> {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3">{children}</CardContent>
    </Card>
  );

  const StatRow = ({ label, stats }) => (
    <div className="flex items-center justify-between py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <div className="flex items-center gap-3">
        <span>{stats.count} trades</span>
        <PnlText value={stats.total_pnl} />
        <span className="text-xs text-muted-foreground">{stats.win_rate}% WR</span>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <h2 className="font-heading text-xl font-semibold">Strategy Insights</h2>
      <p className="text-sm text-muted-foreground">
        AI-derived patterns from {insights.total_trades} paper trades
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <StatCard title="By Trade Type" icon={Activity}>
          {Object.entries(insights.by_trade_type || insights.by_action || {}).map(([type, stats]) => (
            <StatRow key={type} label={type.replace(/_/g, " ")} stats={stats} />
          ))}
        </StatCard>

        <StatCard title="By Confidence" icon={Target}>
          {Object.entries(insights.by_confidence || {}).map(([band, stats]) => (
            <StatRow key={band} label={band} stats={stats} />
          ))}
        </StatCard>

        <StatCard title="By Exit Reason" icon={ShieldAlert}>
          {Object.entries(insights.by_exit_reason || {}).map(([reason, stats]) => (
            <StatRow key={reason} label={reason} stats={stats} />
          ))}
        </StatCard>

        <StatCard title="By Duration" icon={Clock}>
          {Object.entries(insights.by_duration || {}).map(([dur, stats]) => (
            <StatRow key={dur} label={dur} stats={stats} />
          ))}
        </StatCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <StatCard title="Top Winners" icon={Award}>
          {(insights.top_winners || []).map((t, i) => (
            <div key={i} className="flex items-center justify-between py-1 text-sm">
              <span className="font-semibold">{t.symbol}</span>
              <div className="flex items-center gap-2">
                <TradeTypeBadge action={t.action} productType={t.product_type} />
                <PnlText value={t.pnl} />
              </div>
            </div>
          ))}
        </StatCard>

        <StatCard title="Top Losers" icon={AlertTriangle}>
          {(insights.top_losers || []).map((t, i) => (
            <div key={i} className="flex items-center justify-between py-1 text-sm">
              <span className="font-semibold">{t.symbol}</span>
              <div className="flex items-center gap-2">
                <TradeTypeBadge action={t.action} productType={t.product_type} />
                <PnlText value={t.pnl} />
              </div>
            </div>
          ))}
        </StatCard>
      </div>
    </div>
  );
}

/* ─── Main Page ─── */
export default function Sandbox() {
  const [tab, setTab] = useState(TABS.OVERVIEW);
  const [account, setAccount] = useState(null);
  const [holdings, setHoldings] = useState([]);
  const [trades, setTrades] = useState([]);
  const [screenerResults, setScreenerResults] = useState(null);
  const [strategyInsights, setStrategyInsights] = useState(null);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [loading, setLoading] = useState({});

  const setL = (key, val) => setLoading((prev) => ({ ...prev, [key]: val }));

  const fetchAll = useCallback(async () => {
    try {
      const [accRes, holdRes, tradeRes, schedRes, screenRes] = await Promise.all([
        axios.get(`${API}/account`),
        axios.get(`${API}/holdings`),
        axios.get(`${API}/trades`),
        axios.get(`${API}/scheduler/status`),
        axios.get(`${API}/screener/latest`),
      ]);
      setAccount(accRes.data);
      setHoldings(holdRes.data);
      setTrades(tradeRes.data);
      setSchedulerStatus(schedRes.data);
      if (!screenRes.data.message) setScreenerResults(screenRes.data);
    } catch (e) {
      console.error("Failed to load paper data", e);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const runScreener = async () => {
    setL("screener", true);
    try {
      const res = await axios.post(`${API}/screener/run`);
      setScreenerResults(res.data);
      toast.success(`Screened ${res.data.total_screened} stocks`);
    } catch (e) {
      toast.error("Screener failed");
    }
    setL("screener", false);
  };

  const runDailyScan = async () => {
    setL("scan", true);
    toast.info("Running full daily scan — this may take a few minutes...");
    try {
      const res = await axios.post(`${API}/scheduler/run-now`);
      toast.success(
        `Scan complete: ${res.data.signals_generated} signals, ${res.data.sandbox_entries} sandbox entries`
      );
      await fetchAll();
    } catch (e) {
      toast.error("Daily scan failed");
    }
    setL("scan", false);
  };

  const toggleScheduler = async () => {
    const running = schedulerStatus?.running;
    try {
      if (running) {
        await axios.post(`${API}/scheduler/stop`);
        toast.success("Scheduler stopped");
      } else {
        await axios.post(`${API}/scheduler/start`);
        toast.success("Scheduler started — will auto-scan daily");
      }
      const res = await axios.get(`${API}/scheduler/status`);
      setSchedulerStatus(res.data);
    } catch (e) {
      toast.error("Failed to toggle scheduler");
    }
  };

  const resetSandbox = async () => {
    if (!window.confirm("Reset paper? All holdings and trade history will be cleared.")) return;
    try {
      await axios.post(`${API}/reset`);
      toast.success("Paper reset to ₹1,00,000");
      await fetchAll();
    } catch (e) {
      toast.error("Reset failed");
    }
  };

  const exitHolding = async (symbol) => {
    try {
      await axios.post(`${API}/holdings/${symbol}/exit`);
      toast.success(`Exited ${symbol}`);
      await fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Exit failed");
    }
  };

  const refreshPrices = async () => {
    setL("prices", true);
    try {
      const res = await axios.post(`${API}/holdings/refresh-prices`);
      toast.success(`Updated ${res.data.updated} prices`);
      await fetchAll();
    } catch (e) {
      toast.error("Price refresh failed");
    }
    setL("prices", false);
  };

  const loadStrategy = async () => {
    try {
      const res = await axios.get(`${API}/strategy`);
      setStrategyInsights(res.data);
    } catch (e) {
      toast.error("Failed to load strategy insights");
    }
  };

  useEffect(() => {
    if (tab === TABS.STRATEGY) loadStrategy();
  }, [tab]);

  const tabItems = [
    { id: TABS.OVERVIEW, label: "Overview", icon: BarChart3 },
    { id: TABS.SCREENER, label: "Screener", icon: Scan },
    { id: TABS.HOLDINGS, label: `Holdings (${holdings.length})`, icon: Wallet },
    { id: TABS.TRADES, label: `Trades (${trades.length})`, icon: History },
    { id: TABS.STRATEGY, label: "Strategy", icon: Award },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
            <FlaskConical className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h1 className="font-heading text-2xl font-bold tracking-tight">Paper Trading</h1>
            <p className="text-sm text-muted-foreground">Paper trade with ₹1,00,000 virtual capital — test AI strategies risk-free</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={runDailyScan}
            disabled={loading.scan}
            size="sm"
            className="bg-ai-glow/20 text-ai-glow border border-ai-glow/30 hover:bg-ai-glow/30"
          >
            <Zap className={`w-4 h-4 mr-1 ${loading.scan ? "animate-pulse" : ""}`} />
            {loading.scan ? "Scanning..." : "Run Daily Scan"}
          </Button>
          <Button onClick={toggleScheduler} variant="outline" size="sm">
            {schedulerStatus?.running
              ? <><Square className="w-4 h-4 mr-1" /> Stop Auto</>
              : <><Play className="w-4 h-4 mr-1" /> Start Auto</>
            }
          </Button>
          <Button onClick={resetSandbox} variant="outline" size="sm" className="text-signal-danger border-signal-danger/30">
            <RotateCcw className="w-4 h-4 mr-1" /> Reset
          </Button>
        </div>
      </div>

      {/* Account Summary */}
      <AccountBar
        account={account}
        schedulerStatus={schedulerStatus}
        onStart={() => toggleScheduler()}
        onStop={() => toggleScheduler()}
        onReset={resetSandbox}
        onRefresh={fetchAll}
        loading={false}
      />

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border-subtle pb-0">
        {tabItems.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.id
                ? "border-purple-500 text-purple-400"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.15 }}
        >
          {tab === TABS.OVERVIEW && (
            <div className="space-y-6">
              {/* Quick actions */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="bg-surface-primary border-border-subtle hover:border-ai-glow/30 cursor-pointer transition-colors" onClick={() => { setTab(TABS.SCREENER); runScreener(); }}>
                  <CardContent className="p-5 flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center">
                      <Scan className="w-6 h-6 text-blue-400" />
                    </div>
                    <div>
                      <p className="font-semibold">Run Screener</p>
                      <p className="text-xs text-muted-foreground">Pre-filter 125 stocks by momentum</p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground ml-auto" />
                  </CardContent>
                </Card>

                <Card className="bg-surface-primary border-border-subtle hover:border-signal-success/30 cursor-pointer transition-colors" onClick={runDailyScan}>
                  <CardContent className="p-5 flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-signal-success/10 flex items-center justify-center">
                      <Zap className="w-6 h-6 text-signal-success" />
                    </div>
                    <div>
                      <p className="font-semibold">Full Daily Scan</p>
                      <p className="text-xs text-muted-foreground">Screen + AI analysis + auto-trade</p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground ml-auto" />
                  </CardContent>
                </Card>

                <Card className="bg-surface-primary border-border-subtle hover:border-purple-500/30 cursor-pointer transition-colors" onClick={() => { setTab(TABS.STRATEGY); loadStrategy(); }}>
                  <CardContent className="p-5 flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center">
                      <Award className="w-6 h-6 text-purple-400" />
                    </div>
                    <div>
                      <p className="font-semibold">Strategy Insights</p>
                      <p className="text-xs text-muted-foreground">Analyze patterns from past trades</p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground ml-auto" />
                  </CardContent>
                </Card>
              </div>

              {/* Recent holdings + trades summary */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div>
                  <h3 className="font-heading font-semibold mb-2">Active Positions ({holdings.length})</h3>
                  <HoldingsPanel holdings={holdings.slice(0, 5)} onExit={exitHolding} onRefresh={refreshPrices} loading={loading.prices} />
                </div>
                <div>
                  <h3 className="font-heading font-semibold mb-2">Recent Trades</h3>
                  <TradesPanel trades={trades.slice(0, 5)} />
                </div>
              </div>
            </div>
          )}

          {tab === TABS.SCREENER && (
            <ScreenerPanel results={screenerResults} onRunScreener={runScreener} loading={loading.screener} />
          )}

          {tab === TABS.HOLDINGS && (
            <HoldingsPanel holdings={holdings} onExit={exitHolding} onRefresh={refreshPrices} loading={loading.prices} />
          )}

          {tab === TABS.TRADES && <TradesPanel trades={trades} />}

          {tab === TABS.STRATEGY && <StrategyPanel insights={strategyInsights} />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
