import { useState, useEffect } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Clock, 
  CheckCircle2, 
  XCircle, 
  TrendingUp, 
  TrendingDown,
  AlertCircle,
  RefreshCw,
  Edit3,
  History,
  BarChart3,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  ListChecks,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Input } from "../components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Label } from "../components/ui/label";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"}/api`;

const STATUS_BADGES = {
  pending: "badge-pending",
  approved: "badge-approved",
  rejected: "badge-rejected",
  executed: "badge-approved",
  failed: "badge-rejected"
};

const actionBarColor = (action) =>
  action === "BUY" ? "bg-signal-success" : action === "SHORT" ? "bg-orange-500" : "bg-signal-danger";

const actionBadgeClass = (action) =>
  action === "BUY" ? "badge-buy" : action === "SHORT" ? "bg-orange-500/20 text-orange-300 border-orange-500/30" : "badge-sell";

const ActionIcon = ({ action }) =>
  action === "BUY" ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />;

const RecommendationRow = ({ rec, onApprove, onReject, onEdit }) => (
  <motion.tr
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, x: -20 }}
    className="border-b border-border-subtle hover:bg-surface-secondary/50"
  >
    <td className="p-4">
      <div className="flex items-center gap-3">
        <div className={`w-1 h-12 rounded-full ${actionBarColor(rec.action)}`} />
        <div>
          <p className="font-mono font-semibold">{rec.stock_symbol}</p>
          <p className="text-xs text-muted-foreground">{rec.stock_name}</p>
        </div>
      </div>
    </td>
    <td className="p-4">
      <div className="flex items-center gap-1.5">
        <Badge className={actionBadgeClass(rec.action)}>
          <ActionIcon action={rec.action} />
          {rec.action}
        </Badge>
        {/* {rec.product_type === "INTRADAY" && (
          <Badge className="text-[9px] bg-orange-500/20 text-orange-300 border-orange-500/30">INTRADAY</Badge>
        )} */}
      </div>
    </td>
    <td className="p-4 font-mono">{rec.quantity}</td>
    <td className="p-4 font-mono" title="Current / last price when recommendation was generated">
      {rec.current_price != null && rec.current_price > 0 ? `₹${Number(rec.current_price).toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '-'}
    </td>
    <td className="p-4 font-mono">₹{rec.target_price != null ? Number(rec.target_price).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}</td>
    <td className="p-4 font-mono text-signal-danger">₹{rec.stop_loss != null ? Number(rec.stop_loss).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}</td>
    <td className="p-4">
      <div className="flex items-center gap-2">
        <div className="w-16 h-1.5 bg-surface-primary rounded-full overflow-hidden">
          <div 
            className={`h-full ${(rec.confidence_score ?? 0) >= 70 ? 'bg-signal-success' : (rec.confidence_score ?? 0) >= 50 ? 'bg-signal-warning' : 'bg-signal-danger'}`}
            style={{ width: `${Math.min(100, Math.max(0, rec.confidence_score ?? 0))}%` }}
          />
        </div>
        <span className="text-xs font-mono">{rec.confidence_score != null ? `${Number(rec.confidence_score).toFixed(0)}%` : '-'}</span>
      </div>
    </td>
    <td className="p-4">
      {rec.trade_horizon ? (
        <Badge className={`text-[10px] ${
          rec.trade_horizon === 'short_term' ? 'bg-signal-warning/20 text-signal-warning' :
          rec.trade_horizon === 'long_term' ? 'bg-ai-glow/20 text-ai-glow' :
          'bg-signal-success/20 text-signal-success'
        }`}>
          {rec.trade_horizon === 'short_term' ? 'Short' :
           rec.trade_horizon === 'long_term' ? 'Long' : 'Medium'}
        </Badge>
      ) : (
        <span className="text-xs text-muted-foreground">-</span>
      )}
    </td>
    <td className="p-4">
      <div className="flex items-center gap-1">
        <Badge className={STATUS_BADGES[rec.status]}>{rec.status}</Badge>
        {rec.status === 'executed' && rec.trade_mode && (
          <Badge className={`text-[9px] ${
            rec.trade_mode === 'live' ? 'bg-signal-success/20 text-signal-success' :
            rec.trade_mode === 'sandbox' ? 'bg-signal-warning/20 text-signal-warning' :
            'bg-zinc-500/20 text-zinc-400'
          }`}
            title={
              rec.trade_mode === 'live' ? 'Real order placed on Upstox' :
              rec.trade_mode === 'sandbox' ? 'Paper trade via Upstox sandbox' :
              'No Upstox order — simulated locally'
            }
          >
            {rec.trade_mode === 'live' ? 'LIVE' :
             rec.trade_mode === 'sandbox' ? 'SANDBOX' : 'SIM'}
          </Badge>
        )}
      </div>
    </td>
    <td className="p-4 text-xs text-muted-foreground" title="When this recommendation was generated (scan date/time)">
      {rec.created_at
        ? new Date(rec.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
        : '-'}
    </td>
    <td className="p-4">
      {rec.status === 'pending' ? (
        <div className="flex items-center gap-2">
          <Button 
            size="sm" 
            onClick={() => onApprove(rec)}
            className="h-8 px-3 bg-signal-success/20 text-signal-success hover:bg-signal-success/30 border-0"
            data-testid={`approve-btn-${rec.id}`}
          >
            <CheckCircle2 className="w-3 h-3" />
          </Button>
          <Button 
            size="sm" 
            onClick={() => onEdit(rec)}
            variant="outline"
            className="h-8 px-3"
            data-testid={`edit-btn-${rec.id}`}
          >
            <Edit3 className="w-3 h-3" />
          </Button>
          <Button 
            size="sm" 
            onClick={() => onReject(rec)}
            className="h-8 px-3 bg-signal-danger/20 text-signal-danger hover:bg-signal-danger/30 border-0"
            data-testid={`reject-btn-${rec.id}`}
          >
            <XCircle className="w-3 h-3" />
          </Button>
        </div>
      ) : (
        <span className="text-xs text-muted-foreground">
          {rec.updated_at ? new Date(rec.updated_at).toLocaleDateString() : '-'}
        </span>
      )}
    </td>
  </motion.tr>
);

const TABS = { PENDING_BUY: "pending_buy", PENDING_SHORT: "pending_short", PENDING_SELL: "pending_sell", PAIR_TRADES: "pair_trades", HISTORY: "history", TRADE_LOG: "trade_log" };

export default function TradeQueue() {
  const [recommendations, setRecommendations] = useState([]);
  const [trades, setTrades] = useState([]);
  const [tradeStats, setTradeStats] = useState({});
  const [pairTrades, setPairTrades] = useState([]);
  const [tab, setTab] = useState(TABS.PENDING_BUY);
  const [loading, setLoading] = useState(true);
  const [editDialog, setEditDialog] = useState({ open: false, rec: null });
  const [editForm, setEditForm] = useState({ quantity: 0, price: 0 });

  const fetchRecommendations = async () => {
    try {
      const res = await axios.get(`${API}/recommendations`);
      setRecommendations(res.data);
    } catch (error) {
      console.error("Failed to fetch recommendations:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchTradeHistory = async () => {
    try {
      const [tradesRes, statsRes] = await Promise.all([
        axios.get(`${API}/trades/history`),
        axios.get(`${API}/trades/stats`),
      ]);
      setTrades(tradesRes.data);
      setTradeStats(statsRes.data);
    } catch (error) {
      console.error("Failed to fetch trade history:", error);
    }
  };

  const fetchPairTrades = async () => {
    try {
      const res = await axios.get(`${API}/pairs/trades`);
      setPairTrades(res.data || []);
    } catch {
      /* pairs may not be computed yet */
    }
  };

  const fetchAll = async () => {
    setLoading(true);
    await Promise.all([fetchRecommendations(), fetchTradeHistory(), fetchPairTrades()]);
    setLoading(false);
  };

  useEffect(() => {
    fetchAll();
  }, []);

  const pendingBuy = recommendations.filter((r) => r.status === "pending" && r.action === "BUY");
  const pendingShort = recommendations.filter((r) => r.status === "pending" && r.action === "SHORT");
  const pendingSell = recommendations.filter((r) => r.status === "pending" && r.action === "SELL");
  const history = recommendations.filter((r) => r.status === "executed" || r.status === "rejected");

  const filteredRecs =
    tab === TABS.PENDING_BUY ? pendingBuy
    : tab === TABS.PENDING_SHORT ? pendingShort
    : tab === TABS.PENDING_SELL ? pendingSell
    : tab === TABS.HISTORY ? history
    : [];

  const handleApprove = async (rec) => {
    try {
      await axios.post(`${API}/recommendations/${rec.id}/approve`, { approved: true });
      toast.success(`Trade approved: ${rec.action} ${rec.stock_symbol}`);
      fetchRecommendations();
    } catch (error) {
      console.error("Failed to approve:", error);
      toast.error("Failed to approve trade");
    }
  };

  const handleReject = async (rec) => {
    try {
      await axios.post(`${API}/recommendations/${rec.id}/approve`, { approved: false });
      toast.info(`Trade rejected: ${rec.stock_symbol}`);
      fetchRecommendations();
    } catch (error) {
      console.error("Failed to reject:", error);
      toast.error("Failed to reject trade");
    }
  };

  const handleEdit = (rec) => {
    setEditForm({ quantity: rec.quantity, price: rec.target_price });
    setEditDialog({ open: true, rec });
  };

  const handleApproveWithEdit = async () => {
    try {
      await axios.post(`${API}/recommendations/${editDialog.rec.id}/approve`, {
        approved: true,
        modified_quantity: editForm.quantity,
        modified_price: editForm.price
      });
      toast.success(`Trade approved with modifications`);
      setEditDialog({ open: false, rec: null });
      fetchRecommendations();
    } catch (error) {
      console.error("Failed to approve:", error);
      toast.error("Failed to approve trade");
    }
  };


  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div data-testid="trade-queue-page" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="font-heading text-3xl font-bold tracking-tight flex items-center gap-3">
              <ListChecks className="w-8 h-8 text-muted-foreground" />
              Trades
            </h1>
            <p className="text-muted-foreground mt-1">Signals, approvals, and execution history</p>
          </div>
          {tradeStats.trade_mode && (
            <Badge className={`text-xs px-2 py-1 ${
              tradeStats.trade_mode === 'live'
                ? 'bg-signal-success/20 text-signal-success border-signal-success/30'
                : 'bg-signal-warning/20 text-signal-warning border-signal-warning/30'
            }`}>
              {tradeStats.trade_mode === 'live' ? 'LIVE' : 'SANDBOX'}
            </Badge>
          )}
        </div>
        <Button onClick={fetchAll} variant="outline" data-testid="refresh-queue-btn">
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Trade Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-3 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-secondary"><BarChart3 className="w-4 h-4 text-muted-foreground" /></div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Total Trades</p>
              <p className="font-mono font-semibold">{tradeStats.total_trades || 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-3 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-signal-success/10"><TrendingUp className="w-4 h-4 text-signal-success" /></div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Buy Trades</p>
              <p className="font-mono font-semibold text-signal-success">{tradeStats.buy_trades || 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-3 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-signal-danger/10"><TrendingDown className="w-4 h-4 text-signal-danger" /></div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Sell Trades</p>
              <p className="font-mono font-semibold text-signal-danger">{tradeStats.sell_trades || 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-3 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-secondary"><BarChart3 className="w-4 h-4 text-muted-foreground" /></div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Total Traded</p>
              <p className="font-mono font-semibold">₹{(tradeStats.total_traded_value || 0).toLocaleString()}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-border-subtle pb-2 flex-wrap">
        <Button
          variant={tab === TABS.PENDING_BUY ? "default" : "outline"}
          size="sm"
          onClick={() => setTab(TABS.PENDING_BUY)}
          className={tab === TABS.PENDING_BUY ? "bg-signal-success hover:bg-signal-success/90" : ""}
          data-testid="tab-pending-buy"
        >
          <TrendingUp className="w-4 h-4 mr-1" />
          Pending BUY ({pendingBuy.length})
        </Button>
        <Button
          variant={tab === TABS.PENDING_SHORT ? "default" : "outline"}
          size="sm"
          onClick={() => setTab(TABS.PENDING_SHORT)}
          className={tab === TABS.PENDING_SHORT ? "bg-orange-500 hover:bg-orange-500/90" : ""}
          data-testid="tab-pending-short"
        >
          <TrendingDown className="w-4 h-4 mr-1" />
          Pending SHORT ({pendingShort.length})
        </Button>
        <Button
          variant={tab === TABS.PENDING_SELL ? "default" : "outline"}
          size="sm"
          onClick={() => setTab(TABS.PENDING_SELL)}
          className={tab === TABS.PENDING_SELL ? "bg-signal-danger hover:bg-signal-danger/90" : ""}
          data-testid="tab-pending-sell"
        >
          <TrendingDown className="w-4 h-4 mr-1" />
          Pending SELL ({pendingSell.length})
        </Button>
        <Button
          variant={tab === TABS.PAIR_TRADES ? "default" : "outline"}
          size="sm"
          onClick={() => setTab(TABS.PAIR_TRADES)}
          className={tab === TABS.PAIR_TRADES ? "bg-purple-500 hover:bg-purple-500/90" : ""}
          data-testid="tab-pair-trades"
        >
          <ListChecks className="w-4 h-4 mr-1" />
          Pairs ({pairTrades.length})
        </Button>
        <Button
          variant={tab === TABS.HISTORY ? "default" : "outline"}
          size="sm"
          onClick={() => setTab(TABS.HISTORY)}
          data-testid="tab-history"
        >
          <Clock className="w-4 h-4 mr-1" />
          Rec History ({history.length})
        </Button>
        <Button
          variant={tab === TABS.TRADE_LOG ? "default" : "outline"}
          size="sm"
          onClick={() => setTab(TABS.TRADE_LOG)}
          data-testid="tab-trade-log"
        >
          <History className="w-4 h-4 mr-1" />
          Executed ({trades.length})
        </Button>
      </div>

      {/* Pair Trades Tab */}
      {tab === TABS.PAIR_TRADES ? (
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-6">
            {pairTrades.length === 0 ? (
              <div className="text-center py-16">
                <ListChecks className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                <p className="text-muted-foreground">No active pair trades</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Pair trades are generated from correlation analysis when two stocks diverge significantly
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {pairTrades.map((pt, idx) => (
                  <div key={pt.trade_id || idx} className="p-4 rounded-lg bg-surface-secondary border border-purple-500/20">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Badge className="bg-signal-success/20 text-signal-success border-signal-success/30 text-xs">
                          BUY {pt.long_leg}
                        </Badge>
                        <span className="text-muted-foreground text-xs">+</span>
                        <Badge className="bg-orange-500/20 text-orange-300 border-orange-500/30 text-xs">
                          SHORT {pt.short_leg}
                        </Badge>
                      </div>
                      <Badge className={pt.status === "open" ? "bg-blue-500/20 text-blue-300 border-blue-500/30" : "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"}>
                        {pt.status}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-4 gap-4 text-xs text-muted-foreground">
                      <div>
                        <span className="block text-[10px] uppercase">Correlation</span>
                        <span className="text-foreground font-medium">{pt.correlation?.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] uppercase">Z-Score</span>
                        <span className="text-foreground font-medium">{pt.z_score?.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] uppercase">Long @ Rs.</span>
                        <span className="text-foreground font-medium">{pt.long_price?.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] uppercase">Short @ Rs.</span>
                        <span className="text-foreground font-medium">{pt.short_price?.toFixed(2)}</span>
                      </div>
                    </div>
                    {pt.reasoning && (
                      <p className="text-xs text-muted-foreground mt-2 italic">{pt.reasoning}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {/* Trade Log Tab */}
      {tab === TABS.TRADE_LOG ? (
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-0">
            {trades.length === 0 ? (
              <div className="text-center py-16">
                <BarChart3 className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                <p className="text-muted-foreground">No trades executed yet</p>
                <p className="text-sm text-muted-foreground mt-1">Approved trades will appear here</p>
              </div>
            ) : (
              <ScrollArea className="max-h-[600px]">
                <table className="w-full trading-table">
                  <thead>
                    <tr className="border-b border-border-subtle">
                      <th className="text-left p-4">Date/Time</th>
                      <th className="text-left p-4">Stock</th>
                      <th className="text-left p-4">Action</th>
                      <th className="text-left p-4">Qty</th>
                      <th className="text-left p-4">Price</th>
                      <th className="text-left p-4">Total Value</th>
                      <th className="text-left p-4">Order ID</th>
                      <th className="text-left p-4">Mode</th>
                      <th className="text-left p-4">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((trade, idx) => (
                      <motion.tr
                        key={trade.id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.03 }}
                        className="border-b border-border-subtle/50 hover:bg-surface-secondary/50"
                      >
                        <td className="p-4">
                          <div className="flex items-center gap-2">
                            <Calendar className="w-4 h-4 text-muted-foreground" />
                            <div>
                              <p className="font-mono text-sm">{new Date(trade.executed_at).toLocaleDateString()}</p>
                              <p className="text-xs text-muted-foreground">{new Date(trade.executed_at).toLocaleTimeString()}</p>
                            </div>
                          </div>
                        </td>
                        <td className="p-4">
                          <p className="font-mono font-semibold">{trade.stock_symbol}</p>
                          <p className="text-xs text-muted-foreground">{trade.stock_name}</p>
                        </td>
                        <td className="p-4">
                          <Badge className={trade.action === "BUY" ? "badge-buy" : "badge-sell"}>
                            {trade.action === "BUY" ? <ArrowUpRight className="w-3 h-3 mr-1" /> : <ArrowDownRight className="w-3 h-3 mr-1" />}
                            {trade.action}
                          </Badge>
                        </td>
                        <td className="p-4 font-mono">{trade.quantity}</td>
                        <td className="p-4 font-mono">₹{trade.price?.toLocaleString()}</td>
                        <td className="p-4 font-mono font-semibold">₹{trade.total_value?.toLocaleString()}</td>
                        <td className="p-4">
                          <code className="text-xs bg-surface-secondary px-2 py-1 rounded">{trade.order_id || "-"}</code>
                        </td>
                        <td className="p-4">
                          <Badge className={`text-[10px] ${
                            trade.trade_mode === "live" ? "bg-signal-success/20 text-signal-success border-signal-success/30" :
                            trade.trade_mode === "sandbox" ? "bg-signal-warning/20 text-signal-warning border-signal-warning/30" :
                            "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"
                          }`}>
                            {trade.trade_mode === "live" ? "LIVE" : trade.trade_mode === "sandbox" ? "SANDBOX" : "SIMULATED"}
                          </Badge>
                        </td>
                        <td className="p-4">
                          <Badge className="badge-approved">{trade.status}</Badge>
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      ) : (
      /* Recommendations Table */
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-0">
          {filteredRecs.length === 0 ? (
            <div className="text-center py-16">
              <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">
                {tab === TABS.PENDING_BUY && "No pending BUY recommendations"}
                {tab === TABS.PENDING_SHORT && "No pending SHORT (intraday) recommendations"}
                {tab === TABS.PENDING_SELL && "No pending SELL recommendations"}
                {tab === TABS.HISTORY && "No executed or rejected trades in history"}
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                {tab !== TABS.HISTORY && "Run AI scan (or Portfolio Sell Scan) to generate trade ideas"}
              </p>
            </div>
          ) : (
            <ScrollArea className="w-full">
              <table className="w-full trading-table">
                <thead>
                  <tr className="border-b border-border-subtle">
                    <th className="text-left p-4">Stock</th>
                    <th className="text-left p-4">Action</th>
                    <th className="text-left p-4">Qty</th>
                    <th className="text-left p-4">Price</th>
                    <th className="text-left p-4">Target</th>
                    <th className="text-left p-4">Stop Loss</th>
                    <th className="text-left p-4">Confidence</th>
                    <th className="text-left p-4">Horizon</th>
                    <th className="text-left p-4">Status</th>
                    <th className="text-left p-4">Scan at</th>
                    <th className="text-left p-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <AnimatePresence>
                    {filteredRecs.map((rec) => (
                      <RecommendationRow
                        key={rec.id}
                        rec={rec}
                        onApprove={handleApprove}
                        onReject={handleReject}
                        onEdit={handleEdit}
                      />
                    ))}
                  </AnimatePresence>
                </tbody>
              </table>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
      )}

      {/* Edit Dialog */}
      <Dialog open={editDialog.open} onOpenChange={(open) => setEditDialog({ open, rec: editDialog.rec })}>
        <DialogContent className="bg-surface-primary border-border-subtle">
          <DialogHeader>
            <DialogTitle className="font-heading">
              Modify Trade: {editDialog.rec?.stock_symbol}
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Quantity</Label>
              <Input
                type="number"
                value={editForm.quantity}
                onChange={(e) => setEditForm({ ...editForm, quantity: parseInt(e.target.value) })}
                className="bg-surface-secondary border-border-subtle"
                data-testid="edit-quantity-input"
              />
            </div>
            <div className="space-y-2">
              <Label>Target Price (₹)</Label>
              <Input
                type="number"
                value={editForm.price}
                onChange={(e) => setEditForm({ ...editForm, price: parseFloat(e.target.value) })}
                className="bg-surface-secondary border-border-subtle"
                data-testid="edit-price-input"
              />
            </div>
            
            {editDialog.rec?.action === "SHORT" && (
              <div className="p-3 bg-orange-500/10 border border-orange-500/30 rounded-lg">
                <p className="text-sm font-semibold text-orange-300 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  Intraday Short-Sell
                </p>
                <p className="text-xs text-orange-200/80 mt-1">
                  This position MUST be squared off before 3:15 PM IST. Upstox will auto-square-off
                  any open intraday positions at market close.
                </p>
              </div>
            )}
            <div className="p-3 bg-surface-secondary rounded-lg">
              <p className="text-sm text-muted-foreground mb-2">AI Reasoning:</p>
              <p className="text-sm">{editDialog.rec?.ai_reasoning}</p>
            </div>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialog({ open: false, rec: null })}>
              Cancel
            </Button>
            <Button onClick={handleApproveWithEdit} className="btn-trade-buy" data-testid="confirm-edit-btn">
              Approve with Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
