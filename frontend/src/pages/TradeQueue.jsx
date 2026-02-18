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
  Filter,
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

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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
    <td className="p-4 font-mono">₹{rec.target_price?.toLocaleString()}</td>
    <td className="p-4 font-mono text-signal-danger">₹{rec.stop_loss?.toLocaleString() || '-'}</td>
    <td className="p-4">
      <div className="flex items-center gap-2">
        <div className="w-16 h-1.5 bg-surface-primary rounded-full overflow-hidden">
          <div 
            className={`h-full ${rec.confidence_score >= 70 ? 'bg-signal-success' : rec.confidence_score >= 50 ? 'bg-signal-warning' : 'bg-signal-danger'}`}
            style={{ width: `${rec.confidence_score}%` }}
          />
        </div>
        <span className="text-xs font-mono">{rec.confidence_score?.toFixed(0)}%</span>
      </div>
    </td>
    <td className="p-4">
      <Badge className={STATUS_BADGES[rec.status]}>{rec.status}</Badge>
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
          {new Date(rec.updated_at).toLocaleDateString()}
        </span>
      )}
    </td>
  </motion.tr>
);

export default function TradeQueue() {
  const [recommendations, setRecommendations] = useState([]);
  const [filter, setFilter] = useState("all");
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

  const filteredRecs = recommendations.filter(rec => {
    if (filter === "all") return true;
    return rec.status === filter;
  });

  const pendingCount = recommendations.filter(r => r.status === 'pending').length;
  const approvedCount = recommendations.filter(r => r.status === 'approved' || r.status === 'executed').length;
  const rejectedCount = recommendations.filter(r => r.status === 'rejected').length;

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

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <Card 
          className={`bg-surface-primary border-border-subtle cursor-pointer ${filter === 'pending' ? 'ring-2 ring-signal-warning' : ''}`}
          onClick={() => setFilter('pending')}
        >
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="data-label">Pending</p>
              <p className="data-value text-2xl text-signal-warning">{pendingCount}</p>
            </div>
            <Clock className="w-8 h-8 text-signal-warning/50" />
          </CardContent>
        </Card>
        
        <Card 
          className={`bg-surface-primary border-border-subtle cursor-pointer ${filter === 'executed' ? 'ring-2 ring-signal-success' : ''}`}
          onClick={() => setFilter('executed')}
        >
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="data-label">Executed</p>
              <p className="data-value text-2xl text-signal-success">{approvedCount}</p>
            </div>
            <CheckCircle2 className="w-8 h-8 text-signal-success/50" />
          </CardContent>
        </Card>
        
        <Card 
          className={`bg-surface-primary border-border-subtle cursor-pointer ${filter === 'rejected' ? 'ring-2 ring-signal-danger' : ''}`}
          onClick={() => setFilter('rejected')}
        >
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="data-label">Rejected</p>
              <p className="data-value text-2xl text-signal-danger">{rejectedCount}</p>
            </div>
            <XCircle className="w-8 h-8 text-signal-danger/50" />
          </CardContent>
        </Card>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-4">
        <Filter className="w-4 h-4 text-muted-foreground" />
        <div className="flex gap-2">
          {['all', 'pending', 'executed', 'rejected'].map((status) => (
            <Button
              key={status}
              variant={filter === status ? "default" : "outline"}
              size="sm"
              onClick={() => setFilter(status)}
              data-testid={`filter-${status}`}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      {/* Recommendations Table */}
      <Card className="bg-surface-primary border-border-subtle">
        <CardContent className="p-0">
          {filteredRecs.length === 0 ? (
            <div className="text-center py-16">
              <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">No recommendations found</p>
              <p className="text-sm text-muted-foreground mt-1">Run AI scan to generate trade ideas</p>
            </div>
          ) : (
            <ScrollArea className="w-full">
              <table className="w-full trading-table">
                <thead>
                  <tr className="border-b border-border-subtle">
                    <th className="text-left p-4">Stock</th>
                    <th className="text-left p-4">Action</th>
                    <th className="text-left p-4">Qty</th>
                    <th className="text-left p-4">Target</th>
                    <th className="text-left p-4">Stop Loss</th>
                    <th className="text-left p-4">Confidence</th>
                    <th className="text-left p-4">Status</th>
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
