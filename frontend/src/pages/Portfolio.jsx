import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  Wallet, 
  TrendingUp, 
  TrendingDown, 
  PieChart,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart as RechartsPie, Pie, Cell } from "recharts";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SECTOR_COLORS = {
  IT: "#3B82F6",
  Banking: "#10B981",
  Pharma: "#8B5CF6",
  Auto: "#F97316",
  FMCG: "#FACC15",
  Energy: "#EF4444",
  Metal: "#71717A",
  Infrastructure: "#06B6D4",
  Telecom: "#EC4899",
  Consumer: "#6366F1"
};

const HoldingCard = ({ holding }) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    className="p-4 bg-surface-secondary rounded-lg border border-border-subtle"
  >
    <div className="flex items-start justify-between mb-3">
      <div>
        <h3 className="font-mono font-semibold">{holding.stock_symbol}</h3>
        <p className="text-xs text-muted-foreground">{holding.stock_name}</p>
      </div>
      <Badge className="text-[10px]">{holding.sector}</Badge>
    </div>
    
    <div className="grid grid-cols-2 gap-4">
      <div>
        <p className="data-label">Quantity</p>
        <p className="font-mono text-lg">{holding.quantity}</p>
      </div>
      <div>
        <p className="data-label">Avg Price</p>
        <p className="font-mono">₹{holding.avg_buy_price?.toLocaleString()}</p>
      </div>
      <div>
        <p className="data-label">Invested</p>
        <p className="font-mono">₹{holding.invested_value?.toLocaleString()}</p>
      </div>
      <div>
        <p className="data-label">Current</p>
        <p className="font-mono">₹{holding.current_value?.toLocaleString()}</p>
      </div>
    </div>
    
    <div className={`mt-4 p-2 rounded flex items-center justify-between ${holding.pnl >= 0 ? 'bg-signal-success/10' : 'bg-signal-danger/10'}`}>
      <span className="text-sm">P&L</span>
      <span className={`font-mono font-semibold flex items-center gap-1 ${holding.pnl >= 0 ? 'text-signal-success' : 'text-signal-danger'}`}>
        {holding.pnl >= 0 ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
        ₹{Math.abs(holding.pnl || 0).toLocaleString()} ({holding.pnl_percent?.toFixed(2) || 0}%)
      </span>
    </div>
  </motion.div>
);

export default function Portfolio() {
  const [portfolio, setPortfolio] = useState({ holdings: [], summary: {} });
  const [sectorBreakdown, setSectorBreakdown] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [portfolioRes, sectorRes] = await Promise.all([
        axios.get(`${API}/portfolio`),
        axios.get(`${API}/portfolio/sector-breakdown`)
      ]);
      setPortfolio(portfolioRes.data);
      setSectorBreakdown(sectorRes.data);
    } catch (error) {
      console.error("Failed to fetch portfolio:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const pnlTrend = portfolio.summary?.total_pnl >= 0 ? 'up' : 'down';

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
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Portfolio</h1>
          <p className="text-muted-foreground mt-1">Your holdings and performance</p>
        </div>
        <Button onClick={fetchData} variant="outline" data-testid="refresh-portfolio-btn">
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-5">
            <p className="data-label mb-2">Total Invested</p>
            <p className="data-value text-2xl">₹{(portfolio.summary?.total_invested || 0).toLocaleString()}</p>
          </CardContent>
        </Card>
        
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-5">
            <p className="data-label mb-2">Current Value</p>
            <p className="data-value text-2xl">₹{(portfolio.summary?.total_current || 0).toLocaleString()}</p>
          </CardContent>
        </Card>
        
        <Card className={`border-border-subtle ${pnlTrend === 'up' ? 'bg-signal-success/5' : 'bg-signal-danger/5'}`}>
          <CardContent className="p-5">
            <p className="data-label mb-2">Total P&L</p>
            <div className="flex items-center gap-2">
              {pnlTrend === 'up' ? (
                <TrendingUp className="w-5 h-5 text-signal-success" />
              ) : (
                <TrendingDown className="w-5 h-5 text-signal-danger" />
              )}
              <p className={`data-value text-2xl ${pnlTrend === 'up' ? 'text-signal-success' : 'text-signal-danger'}`}>
                ₹{Math.abs(portfolio.summary?.total_pnl || 0).toLocaleString()}
              </p>
            </div>
            <p className={`text-sm mt-1 ${pnlTrend === 'up' ? 'text-signal-success' : 'text-signal-danger'}`}>
              {portfolio.summary?.total_pnl_percent?.toFixed(2) || 0}%
            </p>
          </CardContent>
        </Card>
        
        <Card className="bg-surface-primary border-border-subtle">
          <CardContent className="p-5">
            <p className="data-label mb-2">Holdings</p>
            <p className="data-value text-2xl">{portfolio.summary?.holdings_count || 0}</p>
            <p className="text-sm text-muted-foreground mt-1">Active positions</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Holdings List */}
        <div className="lg:col-span-2">
          <Card className="bg-surface-primary border-border-subtle h-full">
            <CardHeader className="border-b border-border-subtle">
              <CardTitle className="font-heading text-xl flex items-center gap-2">
                <Wallet className="w-5 h-5 text-muted-foreground" />
                Holdings ({portfolio.holdings.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              {portfolio.holdings.length === 0 ? (
                <div className="text-center py-16">
                  <Wallet className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">No holdings yet</p>
                  <p className="text-sm text-muted-foreground mt-1">Approved trades will appear here</p>
                </div>
              ) : (
                <ScrollArea className="h-[500px]">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pr-4">
                    {portfolio.holdings.map((holding) => (
                      <HoldingCard key={holding.id} holding={holding} />
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
            <CardHeader className="border-b border-border-subtle">
              <CardTitle className="font-heading text-lg flex items-center gap-2">
                <PieChart className="w-5 h-5 text-muted-foreground" />
                Sector Allocation
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              {sectorBreakdown.length === 0 ? (
                <div className="text-center py-12">
                  <PieChart className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground">No data available</p>
                </div>
              ) : (
                <>
                  <div className="h-[200px] mb-4">
                    <ResponsiveContainer width="100%" height="100%">
                      <RechartsPie>
                        <Pie
                          data={sectorBreakdown}
                          dataKey="value"
                          nameKey="sector"
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={80}
                          paddingAngle={2}
                        >
                          {sectorBreakdown.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={SECTOR_COLORS[entry.sector] || "#71717A"} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{ 
                            backgroundColor: '#0A0A0A', 
                            border: '1px solid #27272A',
                            borderRadius: '8px'
                          }}
                          formatter={(value) => [`₹${value.toLocaleString()}`, 'Value']}
                        />
                      </RechartsPie>
                    </ResponsiveContainer>
                  </div>
                  
                  <div className="space-y-2">
                    {sectorBreakdown.map((item) => (
                      <div key={item.sector} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div 
                            className="w-3 h-3 rounded-full" 
                            style={{ backgroundColor: SECTOR_COLORS[item.sector] || "#71717A" }}
                          />
                          <span className="text-sm">{item.sector}</span>
                        </div>
                        <span className="font-mono text-sm">₹{item.value?.toLocaleString()}</span>
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
