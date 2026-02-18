import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  History, 
  TrendingUp, 
  TrendingDown, 
  BarChart3,
  Calendar,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function TradeHistory() {
  const [trades, setTrades] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [tradesRes, statsRes] = await Promise.all([
        axios.get(`${API}/trades/history`),
        axios.get(`${API}/trades/stats`)
      ]);
      setTrades(tradesRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error("Failed to fetch trade history:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div data-testid="trade-history-page" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Trade History</h1>
          <p className="text-muted-foreground mt-1">All executed trades and performance</p>
        </div>
        <Button onClick={fetchData} variant="outline" data-testid="refresh-history-btn">
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-5">
            <p className="data-label mb-2">Total Trades</p>
            <p className="data-value text-2xl">{stats.total_trades || 0}</p>
          </CardContent>
        </Card>
        
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-5">
            <p className="data-label mb-2">Buy Trades</p>
            <p className="data-value text-2xl text-signal-success">{stats.buy_trades || 0}</p>
          </CardContent>
        </Card>
        
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-5">
            <p className="data-label mb-2">Sell Trades</p>
            <p className="data-value text-2xl text-signal-danger">{stats.sell_trades || 0}</p>
          </CardContent>
        </Card>
        
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-5">
            <p className="data-label mb-2">Total Traded</p>
            <p className="data-value text-2xl">₹{(stats.total_traded_value || 0).toLocaleString()}</p>
          </CardContent>
        </Card>
      </div>

      {/* Trade Table */}
      <Card className="bg-surface-primary border-border-subtle">
        <CardHeader className="border-b border-border-subtle">
          <CardTitle className="font-heading text-xl flex items-center gap-2">
            <History className="w-5 h-5 text-muted-foreground" />
            Executed Trades
          </CardTitle>
        </CardHeader>
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
                    <th className="text-left p-4">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade, idx) => (
                    <motion.tr
                      key={trade.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: idx * 0.05 }}
                      className="border-b border-border-subtle/50 hover:bg-surface-secondary/50"
                    >
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-muted-foreground" />
                          <div>
                            <p className="font-mono text-sm">
                              {new Date(trade.executed_at).toLocaleDateString()}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(trade.executed_at).toLocaleTimeString()}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <div>
                          <p className="font-mono font-semibold">{trade.stock_symbol}</p>
                          <p className="text-xs text-muted-foreground">{trade.stock_name}</p>
                        </div>
                      </td>
                      <td className="p-4">
                        <Badge className={trade.action === 'BUY' ? 'badge-buy' : 'badge-sell'}>
                          {trade.action === 'BUY' ? (
                            <ArrowUpRight className="w-3 h-3 mr-1" />
                          ) : (
                            <ArrowDownRight className="w-3 h-3 mr-1" />
                          )}
                          {trade.action}
                        </Badge>
                      </td>
                      <td className="p-4 font-mono">{trade.quantity}</td>
                      <td className="p-4 font-mono">₹{trade.price?.toLocaleString()}</td>
                      <td className="p-4 font-mono font-semibold">₹{trade.total_value?.toLocaleString()}</td>
                      <td className="p-4">
                        <code className="text-xs bg-surface-secondary px-2 py-1 rounded">
                          {trade.order_id || '-'}
                        </code>
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
    </div>
  );
}
