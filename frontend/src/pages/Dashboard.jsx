import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  TrendingUp, 
  TrendingDown, 
  Wallet, 
  Clock, 
  BarChart3, 
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  Brain,
  CheckCircle2,
  XCircle
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { useNavigate } from "react-router-dom";

const API = `${process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"}/api`;

const StatCard = ({ title, value, change, icon: Icon, trend, delay = 0 }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.3, delay }}
  >
    <Card className="bg-surface-primary border-border-subtle hover:border-border-active transition-colors">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="data-label mb-2">{title}</p>
            <p className="data-value text-2xl">{value}</p>
            {change !== undefined && (
              <div className={`flex items-center gap-1 mt-2 text-sm ${trend === 'up' ? 'text-signal-success' : trend === 'down' ? 'text-signal-danger' : 'text-muted-foreground'}`}>
                {trend === 'up' ? <ArrowUpRight className="w-4 h-4" /> : trend === 'down' ? <ArrowDownRight className="w-4 h-4" /> : null}
                <span>{change}</span>
              </div>
            )}
          </div>
          <div className={`p-3 rounded-lg ${trend === 'up' ? 'bg-signal-success/10' : trend === 'down' ? 'bg-signal-danger/10' : 'bg-secondary'}`}>
            <Icon className={`w-5 h-5 ${trend === 'up' ? 'text-signal-success' : trend === 'down' ? 'text-signal-danger' : 'text-muted-foreground'}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  </motion.div>
);

const RecommendationCard = ({ rec, onApprove, onReject }) => (
  <motion.div
    initial={{ opacity: 0, x: -20 }}
    animate={{ opacity: 1, x: 0 }}
    className={`recommendation-card ${rec.action.toLowerCase()}`}
  >
    <div className="flex items-start justify-between mb-4">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <h3 className="font-heading font-semibold text-lg">{rec.stock_symbol}</h3>
          <Badge className={rec.action === "BUY" ? "badge-buy" : "badge-sell"}>
            {rec.action}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{rec.stock_name}</p>
      </div>
      <div className="text-right">
        <p className="data-value">{rec.confidence_score.toFixed(0)}%</p>
        <p className="data-label">Confidence</p>
      </div>
    </div>
    
    <div className="grid grid-cols-3 gap-4 mb-4">
      <div>
        <p className="data-label">Target</p>
        <p className="font-mono text-sm">₹{rec.target_price?.toLocaleString()}</p>
      </div>
      <div>
        <p className="data-label">Quantity</p>
        <p className="font-mono text-sm">{rec.quantity}</p>
      </div>
      <div>
        <p className="data-label">Stop Loss</p>
        <p className="font-mono text-sm text-signal-danger">₹{rec.stop_loss?.toLocaleString() || '-'}</p>
      </div>
    </div>
    
    <p className="text-sm text-muted-foreground mb-4 line-clamp-2">{rec.ai_reasoning}</p>
    
    <div className="flex gap-2">
      <Button 
        onClick={() => onApprove(rec.id)} 
        className="flex-1 btn-trade-buy"
        data-testid={`approve-${rec.id}`}
      >
        <CheckCircle2 className="w-4 h-4 mr-2" />
        Approve
      </Button>
      <Button 
        onClick={() => onReject(rec.id)} 
        variant="outline"
        className="flex-1 border-signal-danger/50 text-signal-danger hover:bg-signal-danger/10"
        data-testid={`reject-${rec.id}`}
      >
        <XCircle className="w-4 h-4 mr-2" />
        Reject
      </Button>
    </div>
  </motion.div>
);

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [pendingRecs, setPendingRecs] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchData = async () => {
    try {
      const [statsRes, recsRes] = await Promise.all([
        axios.get(`${API}/dashboard/stats`),
        axios.get(`${API}/recommendations/pending`)
      ]);
      setStats(statsRes.data);
      setPendingRecs(recsRes.data);
    } catch (error) {
      console.error("Failed to fetch dashboard data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Only load data, don't initialize stocks here
    // Stock initialization is handled by StockUniverse component
    fetchData();
  }, []);

  const handleApprove = async (recId) => {
    try {
      await axios.post(`${API}/recommendations/${recId}/approve`, { approved: true });
      fetchData();
    } catch (error) {
      console.error("Failed to approve:", error);
    }
  };

  const handleReject = async (recId) => {
    try {
      await axios.post(`${API}/recommendations/${recId}/approve`, { approved: false });
      fetchData();
    } catch (error) {
      console.error("Failed to reject:", error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]">
        <div className="spinner" />
      </div>
    );
  }

  const pnlTrend = stats?.total_pnl >= 0 ? 'up' : 'down';

  return (
    <div data-testid="dashboard-page" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1">AI-powered trading insights for Indian markets</p>
        </div>
        <Button 
          onClick={() => navigate('/research')}
          className="bg-ai-glow/20 text-ai-glow border border-ai-glow/30 hover:bg-ai-glow/30"
          data-testid="start-ai-scan-btn"
        >
          <Brain className="w-4 h-4 mr-2" />
          Start AI Scan
        </Button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Portfolio Value"
          value={`₹${(stats?.portfolio_value || 0).toLocaleString()}`}
          change={`${stats?.pnl_percent?.toFixed(2) || 0}%`}
          icon={Wallet}
          trend={pnlTrend}
          delay={0}
        />
        <StatCard
          title="Total P&L"
          value={`₹${(stats?.total_pnl || 0).toLocaleString()}`}
          change={stats?.total_pnl >= 0 ? "Profit" : "Loss"}
          icon={stats?.total_pnl >= 0 ? TrendingUp : TrendingDown}
          trend={pnlTrend}
          delay={0.1}
        />
        <StatCard
          title="Pending Approvals"
          value={stats?.pending_recommendations || 0}
          icon={Clock}
          delay={0.2}
        />
        <StatCard
          title="Today's Trades"
          value={stats?.today_trades || 0}
          icon={BarChart3}
          delay={0.3}
        />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pending Recommendations */}
        <div className="lg:col-span-2">
          <Card className="bg-surface-primary border-border-subtle h-full">
            <CardHeader className="border-b border-border-subtle">
              <div className="flex items-center justify-between">
                <CardTitle className="font-heading text-xl flex items-center gap-2">
                  <Clock className="w-5 h-5 text-signal-warning" />
                  Pending Approvals
                </CardTitle>
                <Badge className="badge-pending">{pendingRecs.length} Pending</Badge>
              </div>
            </CardHeader>
            <CardContent className="p-4">
              {pendingRecs.length === 0 ? (
                <div className="text-center py-12">
                  <Brain className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">No pending recommendations</p>
                  <p className="text-sm text-muted-foreground mt-1">Run AI scan to generate trade ideas</p>
                </div>
              ) : (
                <ScrollArea className="h-[400px] pr-4">
                  <div className="space-y-4">
                    {pendingRecs.map((rec) => (
                      <RecommendationCard
                        key={rec.id}
                        rec={rec}
                        onApprove={handleApprove}
                        onReject={handleReject}
                      />
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Quick Stats */}
        <div className="space-y-4">
          <Card className="bg-surface-primary border-border-subtle">
            <CardHeader className="border-b border-border-subtle pb-3">
              <CardTitle className="font-heading text-lg flex items-center gap-2">
                <Layers className="w-5 h-5 text-muted-foreground" />
                Stock Universe
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <div className="text-center py-4">
                <p className="data-value text-4xl">{stats?.total_stocks || 0}</p>
                <p className="data-label mt-2">Stocks Tracked</p>
              </div>
              <Button 
                variant="outline" 
                className="w-full mt-4"
                onClick={() => navigate('/stocks')}
                data-testid="view-stocks-btn"
              >
                View All Stocks
              </Button>
            </CardContent>
          </Card>

          <Card className="bg-surface-primary border-border-subtle">
            <CardHeader className="border-b border-border-subtle pb-3">
              <CardTitle className="font-heading text-lg flex items-center gap-2">
                <Wallet className="w-5 h-5 text-muted-foreground" />
                Holdings
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <div className="text-center py-4">
                <p className="data-value text-4xl">{stats?.holdings_count || 0}</p>
                <p className="data-label mt-2">Active Positions</p>
              </div>
              <Button 
                variant="outline" 
                className="w-full mt-4"
                onClick={() => navigate('/portfolio')}
                data-testid="view-portfolio-btn"
              >
                View Portfolio
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
