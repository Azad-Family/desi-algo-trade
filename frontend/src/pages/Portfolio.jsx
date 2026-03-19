import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  Wallet, 
  TrendingUp, 
  TrendingDown, 
  PieChart as PieChartIcon,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Brain,
  Loader2,
  AlertTriangle,
  Clock,
  Target,
  ListChecks,
  BarChart3,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

const API = `${process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"}/api`;

const PALETTE = [
  "#3B82F6", "#10B981", "#8B5CF6", "#F97316", "#FACC15",
  "#EF4444", "#06B6D4", "#EC4899", "#6366F1", "#71717A",
  "#14B8A6", "#F43F5E", "#A855F7", "#22D3EE", "#FB923C",
];

const getSectorColor = (sector, index) => PALETTE[index % PALETTE.length];

const HORIZON_SHORT = { short_term: "Short", medium_term: "Med", long_term: "Long" };

const getDaysHeld = (boughtAt) => {
  if (!boughtAt) return null;
  return Math.floor((Date.now() - new Date(boughtAt).getTime()) / 86400000);
};

const HoldingCard = ({ holding, sellSignal, onSell, sellingSymbol }) => {
  const daysHeld = getDaysHeld(holding.bought_at);
  const [sellQty, setSellQty] = useState(holding.quantity);
  const [showSellForm, setShowSellForm] = useState(false);
  const isSelling = sellingSymbol === holding.stock_symbol;
  const pnlUp = (holding.pnl ?? 0) >= 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`p-3 bg-surface-secondary rounded-lg border ${
        sellSignal?.action === "SELL" ? "border-signal-danger/50" : "border-border-subtle"
      }`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <div className="min-w-0">
          <h3 className="font-mono text-sm font-semibold leading-tight">{holding.stock_symbol}</h3>
          <p className="text-[10px] text-muted-foreground truncate">{holding.stock_name}</p>
        </div>
        <div className="flex gap-1 flex-shrink-0">
          {holding.sector && <Badge className="text-[9px] py-0 px-1.5">{holding.sector}</Badge>}
          {holding.trade_horizon && (
            <Badge className="text-[9px] py-0 px-1.5 bg-ai-glow/20 text-ai-glow border-ai-glow/30">
              {HORIZON_SHORT[holding.trade_horizon] || holding.trade_horizon}
            </Badge>
          )}
          <Badge className={`text-[9px] py-0 px-1.5 ${
            holding.trade_mode === 'live' ? 'bg-signal-success/20 text-signal-success border-signal-success/30' :
            holding.trade_mode === 'sandbox' ? 'bg-signal-warning/20 text-signal-warning border-signal-warning/30' :
            'bg-zinc-500/20 text-zinc-400 border-zinc-500/30'
          }`}>
            {holding.trade_mode === 'live' ? 'LIVE' : holding.trade_mode === 'sandbox' ? 'SBX' : 'SIM'}
          </Badge>
        </div>
      </div>

      {/* Data grid */}
      <div className="grid grid-cols-4 gap-x-1.5 gap-y-1 text-[11px]">
        <div>
          <p className="text-muted-foreground text-[9px]">Qty</p>
          <p className="font-mono">{holding.quantity}</p>
        </div>
        <div>
          <p className="text-muted-foreground text-[9px]">Buy Price</p>
          <p className="font-mono">₹{holding.avg_buy_price?.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-muted-foreground text-[9px]">LTP</p>
          <p className="font-mono">₹{holding.current_price?.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-muted-foreground text-[9px]">Invested</p>
          <p className="font-mono">₹{holding.invested_value?.toLocaleString()}</p>
        </div>
        {/* <div>
          <p className="text-muted-foreground text-[9px]">Current</p>
          <p className="font-mono">₹{holding.current_value?.toLocaleString()}</p>
        </div> */}
      </div>

      {/* Meta chips — days held, target, SL */}
      {(daysHeld !== null || holding.target_price > 0 || holding.stop_loss > 0) && (
        <div className="mt-1.5 flex flex-wrap gap-1 text-[9px]">
          {daysHeld !== null && (
            <span className="px-1.5 py-0.5 rounded-full bg-surface-primary text-muted-foreground flex items-center gap-0.5">
              <Clock className="w-2.5 h-2.5" /> {daysHeld}d
            </span>
          )}
          {holding.target_price > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-signal-success/10 text-signal-success flex items-center gap-0.5">
              <Target className="w-2.5 h-2.5" /> ₹{holding.target_price?.toLocaleString()}
            </span>
          )}
          {holding.stop_loss > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-signal-danger/10 text-signal-danger flex items-center gap-0.5">
              <AlertTriangle className="w-2.5 h-2.5" /> ₹{holding.stop_loss?.toLocaleString()}
            </span>
          )}
        </div>
      )}

      {/* P&L — compact inline */}
      <div className={`mt-2 px-2 py-1 rounded flex items-center justify-between text-[11px] ${pnlUp ? 'bg-signal-success/10' : 'bg-signal-danger/10'}`}>
        <span className="text-muted-foreground">P&L</span>
        <span className={`font-mono font-medium flex items-center gap-0.5 ${pnlUp ? 'text-signal-success' : 'text-signal-danger'}`}>
          {pnlUp ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          ₹{Math.abs(holding.pnl || 0).toLocaleString()}
          <span className="text-[10px] opacity-80">({holding.pnl_percent?.toFixed(1) || 0}%)</span>
        </span>
      </div>

      {/* AI sell signal */}
      {sellSignal && (
        <div className={`mt-2 p-2 rounded-lg text-[10px] ${
          sellSignal.action === "SELL"
            ? "bg-signal-danger/10 border border-signal-danger/30"
            : "bg-signal-success/10 border border-signal-success/30"
        }`}>
          <div className="flex items-center justify-between mb-0.5">
            <span className="font-semibold flex items-center gap-1">
              <Brain className="w-2.5 h-2.5" /> AI: {sellSignal.action}
            </span>
            {sellSignal.urgency && (
              <Badge className={`text-[8px] py-0 ${
                sellSignal.urgency === "immediate" ? "bg-signal-danger/20 text-signal-danger" :
                sellSignal.urgency === "soon" ? "bg-signal-warning/20 text-signal-warning" :
                "bg-secondary text-muted-foreground"
              }`}>{sellSignal.urgency}</Badge>
            )}
          </div>
          <p className="text-muted-foreground leading-relaxed line-clamp-2">{sellSignal.reasoning}</p>
        </div>
      )}

      {/* Sell button / form — compact */}
      {!showSellForm ? (
        <button
          onClick={() => setShowSellForm(true)}
          className="mt-2 w-full py-1 text-[10px] font-medium rounded border border-signal-danger/30 text-signal-danger hover:bg-signal-danger/10 transition-colors"
        >
          Sell
        </button>
      ) : (
        <div className="mt-2 p-2 rounded-lg bg-signal-danger/5 border border-signal-danger/20 space-y-1.5">
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-muted-foreground">Qty</label>
            <input
              type="number"
              min={1}
              max={holding.quantity}
              value={sellQty}
              onChange={(e) => setSellQty(Math.min(holding.quantity, Math.max(1, parseInt(e.target.value) || 1)))}
              className="w-16 px-1.5 py-0.5 text-[10px] font-mono rounded bg-surface-primary border border-border-subtle text-foreground"
            />
            <span className="text-[9px] text-muted-foreground">/ {holding.quantity}</span>
          </div>
          <div className="flex gap-1.5">
            <button
              onClick={() => { onSell(holding.stock_symbol, sellQty); setShowSellForm(false); }}
              disabled={isSelling}
              className="flex-1 py-1 text-[10px] font-semibold rounded bg-signal-danger text-white hover:bg-signal-danger/80 disabled:opacity-50 transition-colors flex items-center justify-center gap-1"
            >
              {isSelling ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : null}
              {isSelling ? "Selling..." : `Sell ${sellQty} @ ₹${holding.current_price?.toLocaleString()}`}
            </button>
            <button
              onClick={() => setShowSellForm(false)}
              className="px-2 py-1 text-[10px] rounded border border-border-subtle text-muted-foreground hover:bg-surface-primary transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default function Portfolio() {
  const navigate = useNavigate();
  const [portfolio, setPortfolio] = useState({ holdings: [], summary: {} });
  const [sectorBreakdown, setSectorBreakdown] = useState([]);
  const [dashStats, setDashStats] = useState({});
  const [sellSignals, setSellSignals] = useState({});
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [sellingSymbol, setSellingSymbol] = useState(null);

  const fetchData = async () => {
    try {
      const [portfolioRes, sectorRes, statsRes] = await Promise.all([
        axios.get(`${API}/portfolio`),
        axios.get(`${API}/portfolio/sector-breakdown`),
        axios.get(`${API}/dashboard/stats`),
      ]);
      setPortfolio(portfolioRes.data);
      setSectorBreakdown(sectorRes.data);
      setDashStats(statsRes.data);
    } catch (error) {
      console.error("Failed to fetch portfolio:", error);
    } finally {
      setLoading(false);
    }
  };

  const refreshPrices = async () => {
    setRefreshing(true);
    try {
      await axios.post(`${API}/stocks/refresh`);
      await fetchData();
      toast.success("Portfolio prices updated");
    } catch (error) {
      toast.error("Failed to refresh prices");
    } finally {
      setRefreshing(false);
    }
  };

  const scanForSells = async () => {
    setScanning(true);
    try {
      const res = await axios.post(`${API}/portfolio/scan-sells`);
      const { signals, sell_count } = res.data;
      const signalMap = {};
      for (const sig of signals) {
        signalMap[sig.stock_symbol] = sig;
      }
      setSellSignals(signalMap);
      toast.success(`Scan complete: ${sell_count} sell signal(s) — check Trade Queue`);
    } catch (error) {
      console.error("Scan failed:", error);
      toast.error("Failed to scan portfolio");
    } finally {
      setScanning(false);
    }
  };

  const handleSell = async (symbol, quantity) => {
    setSellingSymbol(symbol);
    try {
      const res = await axios.post(`${API}/portfolio/${symbol}/sell`, null, { params: { quantity } });
      toast.success(`Sold ${quantity} of ${symbol} (${res.data.trade_mode})`);
      await fetchData();
    } catch (error) {
      const msg = error.response?.data?.detail || "Failed to sell";
      toast.error(msg);
    } finally {
      setSellingSymbol(null);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const pnlTrend = (portfolio.summary?.total_pnl ?? 0) >= 0 ? 'up' : 'down';

  // Prepare sector data — filter out null sectors and ensure valid values
  const validSectors = sectorBreakdown.filter(s => s.sector && s.value > 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div data-testid="portfolio-page" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="font-heading text-3xl font-bold tracking-tight">Portfolio</h1>
            <p className="text-muted-foreground mt-1">Your holdings and performance</p>
          </div>
          {portfolio.trade_mode && (
            <Badge className={`text-xs px-2 py-1 ${
              portfolio.trade_mode === 'live'
                ? 'bg-signal-success/20 text-signal-success border-signal-success/30'
                : 'bg-signal-warning/20 text-signal-warning border-signal-warning/30'
            }`}>
              {portfolio.trade_mode === 'live' ? 'LIVE' : 'SANDBOX'}
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            onClick={scanForSells}
            disabled={scanning || portfolio.holdings.length === 0}
            className="bg-ai-glow/20 text-ai-glow border border-ai-glow/30 hover:bg-ai-glow/30"
            data-testid="scan-sells-btn"
          >
            {scanning ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Brain className="w-4 h-4 mr-2" />
            )}
            {scanning ? "Scanning..." : "AI Sell Scan"}
          </Button>
          <Button onClick={refreshPrices} variant="outline" disabled={refreshing} data-testid="refresh-portfolio-btn">
            <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
            Refresh Prices
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-4">
            <p className="data-label mb-1 text-[10px]">Total Invested</p>
            <p className="data-value text-lg font-mono">₹{(portfolio.summary?.total_invested || 0).toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-4">
            <p className="data-label mb-1 text-[10px]">Current Value</p>
            <p className="data-value text-lg font-mono">₹{(portfolio.summary?.total_current || 0).toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card className={`border-border-subtle ${pnlTrend === 'up' ? 'bg-signal-success/5' : 'bg-signal-danger/5'}`}>
          <CardContent className="p-4">
            <p className="data-label mb-1 text-[10px]">Total P&L</p>
            <div className="flex items-center gap-1">
              {pnlTrend === 'up' ? (
                <TrendingUp className="w-4 h-4 text-signal-success" />
              ) : (
                <TrendingDown className="w-4 h-4 text-signal-danger" />
              )}
              <p className={`data-value text-lg font-mono ${pnlTrend === 'up' ? 'text-signal-success' : 'text-signal-danger'}`}>
                ₹{Math.abs(portfolio.summary?.total_pnl || 0).toLocaleString()}
              </p>
            </div>
            <p className={`text-xs mt-0.5 ${pnlTrend === 'up' ? 'text-signal-success' : 'text-signal-danger'}`}>
              {portfolio.summary?.total_pnl_percent?.toFixed(2) || 0}%
            </p>
          </CardContent>
        </Card>
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-4">
            <p className="data-label mb-1 text-[10px]">Holdings</p>
            <p className="data-value text-lg font-mono">{portfolio.summary?.holdings_count || 0}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Active positions</p>
          </CardContent>
        </Card>
        <Card
          className="bg-surface-primary border-border-subtle cursor-pointer hover:border-border-active transition-colors"
          onClick={() => navigate("/trades")}
        >
          <CardContent className="p-4">
            <p className="data-label mb-1 text-[10px] flex items-center gap-1">
              <ListChecks className="w-3 h-3" /> Pending Signals
            </p>
            <p className="data-value text-lg font-mono">{dashStats.pending_recommendations || 0}</p>
          </CardContent>
        </Card>
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-4">
            <p className="data-label mb-1 text-[10px] flex items-center gap-1">
              <BarChart3 className="w-3 h-3" /> Today's Trades
            </p>
            <p className="data-value text-lg font-mono">{dashStats.today_trades || 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Holdings List */}
        <div className="lg:col-span-2">
          <Card className="bg-surface-primary border-border-subtle h-full">
            <CardHeader className="border-b border-border-subtle py-3 px-4">
              <CardTitle className="font-heading text-lg flex items-center gap-2">
                <Wallet className="w-4 h-4 text-muted-foreground" />
                Holdings ({portfolio.holdings.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3">
              {portfolio.holdings.length === 0 ? (
                <div className="text-center py-12">
                  <Wallet className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                  <p className="text-muted-foreground text-sm">No holdings yet</p>
                  <p className="text-xs text-muted-foreground mt-1">Approved trades will appear here</p>
                </div>
              ) : (
                <ScrollArea className="h-[520px]">
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 pr-3">
                    {portfolio.holdings.map((holding) => (
                      <HoldingCard
                        key={holding.id}
                        holding={holding}
                        sellSignal={sellSignals[holding.stock_symbol]}
                        onSell={handleSell}
                        sellingSymbol={sellingSymbol}
                      />
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sector Breakdown */}
        <div>
          <Card className="bg-surface-primary border-border-subtle">
            <CardHeader className="border-b border-border-subtle py-3 px-4">
              <CardTitle className="font-heading text-lg flex items-center gap-2">
                <PieChartIcon className="w-4 h-4 text-muted-foreground" />
                Sector Allocation
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              {validSectors.length === 0 ? (
                <div className="text-center py-10">
                  <PieChartIcon className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground">No data available</p>
                </div>
              ) : (
                <>
                  <div className="h-[200px] mb-4">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={validSectors}
                          dataKey="value"
                          nameKey="sector"
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={75}
                          paddingAngle={2}
                          stroke="none"
                        >
                          {validSectors.map((entry, i) => (
                            <Cell key={entry.sector} fill={getSectorColor(entry.sector, i)} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#0A0A0A',
                            border: '1px solid #27272A',
                            borderRadius: '8px',
                            fontSize: '12px',
                          }}
                          formatter={(value) => [`₹${value.toLocaleString()}`, 'Value']}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="space-y-1.5">
                    {validSectors.map((item, i) => (
                      <div key={item.sector} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <div
                            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                            style={{ backgroundColor: getSectorColor(item.sector, i) }}
                          />
                          <span>{item.sector} ({item.count})</span>
                        </div>
                        <span className="font-mono">₹{item.value?.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
