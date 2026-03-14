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
  Edit3
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

const RecommendationRow = ({ rec, onApprove, onReject, onEdit }) => (
  <motion.tr
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, x: -20 }}
    className="border-b border-border-subtle hover:bg-surface-secondary/50"
  >
    <td className="p-4">
      <div className="flex items-center gap-3">
        <div className={`w-1 h-12 rounded-full ${rec.action === 'BUY' ? 'bg-signal-success' : 'bg-signal-danger'}`} />
        <div>
          <p className="font-mono font-semibold">{rec.stock_symbol}</p>
          <p className="text-xs text-muted-foreground">{rec.stock_name}</p>
        </div>
      </div>
    </td>
    <td className="p-4">
      <Badge className={rec.action === 'BUY' ? 'badge-buy' : 'badge-sell'}>
        {rec.action === 'BUY' ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
        {rec.action}
      </Badge>
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

const TABS = { PENDING_BUY: "pending_buy", PENDING_SELL: "pending_sell", HISTORY: "history" };

export default function TradeQueue() {
  const [recommendations, setRecommendations] = useState([]);
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

  useEffect(() => {
    fetchRecommendations();
  }, []);

  const pendingBuy = recommendations.filter((r) => r.status === "pending" && r.action === "BUY");
  const pendingSell = recommendations.filter((r) => r.status === "pending" && r.action === "SELL");
  const history = recommendations.filter((r) => r.status === "executed" || r.status === "rejected");

  const filteredRecs =
    tab === TABS.PENDING_BUY
      ? pendingBuy
      : tab === TABS.PENDING_SELL
        ? pendingSell
        : history;

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
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Trade Queue</h1>
          <p className="text-muted-foreground mt-1">Review and approve AI-generated trade recommendations</p>
        </div>
        <Button onClick={fetchRecommendations} variant="outline" data-testid="refresh-queue-btn">
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* BUY / SELL / History tabs */}
      <div className="flex items-center gap-2 border-b border-border-subtle pb-2">
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
          variant={tab === TABS.HISTORY ? "default" : "outline"}
          size="sm"
          onClick={() => setTab(TABS.HISTORY)}
          data-testid="tab-history"
        >
          <Clock className="w-4 h-4 mr-1" />
          History ({history.length})
        </Button>
      </div>

      {/* Recommendations Table */}
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-0">
          {filteredRecs.length === 0 ? (
            <div className="text-center py-16">
              <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">
                {tab === TABS.PENDING_BUY && "No pending BUY recommendations"}
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
