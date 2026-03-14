import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  Search, 
  Filter, 
  Brain, 
  TrendingUp, 
  TrendingDown,
  RefreshCw,
  Layers,
  AlertCircle
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Alert, AlertDescription } from "../components/ui/alert";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const API = `${BACKEND_URL}/api`;

// Log API endpoint for debugging
console.log("🔌 API Configuration:", { BACKEND_URL, API, env: process.env.REACT_APP_BACKEND_URL });

const SECTOR_COLORS = {
  IT: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  Banking: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  Pharma: "bg-purple-500/10 text-purple-400 border-purple-500/30",
  Auto: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  FMCG: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  Energy: "bg-red-500/10 text-red-400 border-red-500/30",
  Metal: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
  Infrastructure: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
  Telecom: "bg-pink-500/10 text-pink-400 border-pink-500/30",
  Consumer: "bg-indigo-500/10 text-indigo-400 border-indigo-500/30",
};

const StockCard = ({ stock, onAnalyze }) => (
  <motion.div
    initial={{ opacity: 0, scale: 0.95 }}
    animate={{ opacity: 1, scale: 1 }}
    whileHover={{ scale: 1.02 }}
    transition={{ duration: 0.2 }}
    className="stock-card"
  >
    <div className="flex items-start justify-between mb-3">
      <div>
        <h3 className="font-heading font-semibold text-lg">{stock.symbol}</h3>
        <p className="text-sm text-muted-foreground line-clamp-1">{stock.name}</p>
      </div>
      <Badge className={`${SECTOR_COLORS[stock.sector] || "bg-secondary text-secondary-foreground"} border text-[10px]`}>
        {stock.sector}
      </Badge>
    </div>
    
    <div className="flex items-center justify-between mb-3">
      <div>
        <p className="data-label" title="Last traded price from Upstox (from last refresh)">Price (LTP)</p>
        <p className="font-mono text-lg">
          {stock.current_price != null && stock.current_price > 0 ? `₹${Number(stock.current_price).toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '-'}
        </p>
      </div>
      <div className="text-right">
        <p className="data-label" title="Percentage change from previous close (from last refresh)">Day Chg %</p>
        <p className={`font-mono flex items-center gap-1 ${stock.change_percent >= 0 ? 'text-signal-success' : 'text-signal-danger'}`}>
          {stock.change_percent >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          {stock.change_percent != null ? `${(stock.change_percent >= 0 ? '+' : '')}${Number(stock.change_percent).toFixed(2)}%` : '-'}
        </p>
      </div>
    </div>
    
    <Button 
      onClick={() => onAnalyze(stock)} 
      size="sm" 
      className="w-full bg-ai-glow/20 text-ai-glow border border-ai-glow/30 hover:bg-ai-glow/30"
      data-testid={`analyze-${stock.symbol}`}
    >
      <Brain className="w-3 h-3 mr-2" />
      AI Analyze
    </Button>
  </motion.div>
);

export default function StockUniverse() {
  const [stocks, setStocks] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSector, setSelectedSector] = useState("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const navigate = useNavigate();

  const fetchData = async () => {
    setLoading(true);
    try {
      const [stocksRes, sectorsRes] = await Promise.all([
        axios.get(`${API}/stocks`),
        axios.get(`${API}/stocks/sectors`)
      ]);
      setStocks(stocksRes.data);
      setSectors(sectorsRes.data);
      console.log("✓ Loaded", stocksRes.data.length, "stocks from API");
    } catch (error) {
      console.error("❌ API Error Details:", {
        message: error.message,
        code: error.code,
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        url: `${API}/stocks`,
        backendUrl: BACKEND_URL
      });
      
      const errorMsg = error.response?.data?.detail || error.message || "Unknown error";
      toast.error(`Failed to load stocks: ${errorMsg}`);
    } finally {
      setLoading(false);
    }
  };

  const initializeStocks = async () => {
    setRefreshing(true);
    try {
      const res = await axios.post(`${API}/stocks/refresh`);
      console.log("✓ Stock prices updated:", res.data);
      await fetchData();
      toast.success(`Updated ${res.data.updated}/${res.data.total} stock prices`);
    } catch (error) {
      console.error("❌ Refresh Error:", {
        message: error.message,
        status: error.response?.status,
        data: error.response?.data,
        url: `${API}/stocks/refresh`
      });
      
      const errorMsg = error.response?.data?.detail || error.message || "Unknown error";
      toast.error(`Failed to refresh prices: ${errorMsg}`);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    // Fetch stocks (backend initializes them on startup)
    fetchData();
  }, []);

  const handleAnalyze = (stock) => {
    navigate('/research', { state: { stock } });
  };

  const filteredStocks = stocks.filter(stock => {
    const matchesSearch = stock.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         stock.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSector = selectedSector === "all" || stock.sector === selectedSector;
    return matchesSearch && matchesSector;
  });

  const groupedStocks = filteredStocks.reduce((acc, stock) => {
    if (!acc[stock.sector]) acc[stock.sector] = [];
    acc[stock.sector].push(stock);
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div data-testid="stock-universe-page" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Stock Universe</h1>
          <p className="text-muted-foreground mt-1">{stocks.length} stocks across {sectors.length} sectors</p>
        </div>
        <Button 
          onClick={initializeStocks}
          variant="outline"
          disabled={refreshing}
          data-testid="refresh-stocks-btn"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Search and Filter */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by symbol or name..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10 bg-surface-primary border-border-subtle"
            data-testid="stock-search-input"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-muted-foreground" />
          <select
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            className="bg-surface-primary border border-border-subtle rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            data-testid="sector-filter"
          >
            <option value="all">All Sectors</option>
            {sectors.map((s) => (
              <option key={s.sector} value={s.sector}>{s.sector} ({s.count})</option>
            ))}
          </select>
        </div>
      </div>

      {/* Sector Stats */}
      <div className="flex flex-wrap gap-2">
        {sectors.map((s) => (
          <Badge
            key={s.sector}
            className={`cursor-pointer ${SECTOR_COLORS[s.sector] || "bg-secondary"} border ${selectedSector === s.sector ? 'ring-2 ring-offset-2 ring-offset-background ring-primary' : ''}`}
            onClick={() => setSelectedSector(s.sector === selectedSector ? "all" : s.sector)}
            data-testid={`sector-badge-${s.sector}`}
          >
            {s.sector}: {s.count}
          </Badge>
        ))}
      </div>

      {/* Stocks Grid by Sector */}
      {selectedSector === "all" ? (
        <Tabs defaultValue={sectors[0]?.sector || "IT"} className="space-y-4">
          <TabsList className="bg-surface-primary border border-border-subtle flex-wrap h-auto p-1">
            {sectors.map((s) => (
              <TabsTrigger 
                key={s.sector} 
                value={s.sector}
                className="data-[state=active]:bg-secondary"
              >
                {s.sector}
              </TabsTrigger>
            ))}
          </TabsList>
          
          {sectors.map((s) => (
            <TabsContent key={s.sector} value={s.sector}>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {groupedStocks[s.sector]?.map((stock) => (
                  <StockCard key={stock.id} stock={stock} onAnalyze={handleAnalyze} />
                ))}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredStocks.map((stock) => (
            <StockCard key={stock.id} stock={stock} onAnalyze={handleAnalyze} />
          ))}
        </div>
      )}

      {filteredStocks.length === 0 && (
        <div className="text-center py-12">
          <Layers className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">No stocks found</p>
          <Button onClick={initializeStocks} className="mt-4" variant="outline">
            Initialize Stock Universe
          </Button>
        </div>
      )}
    </div>
  );
}
