import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Brain,
  Search,
  Loader2,
  Sparkles,
  Zap,
  RefreshCw,
  MessageSquare,
  Clock,
  ArrowUpCircle,
  ArrowDownCircle,
  CheckCircle2,
  Target,
  ShieldAlert,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Newspaper,
  AlertTriangle,
  Crosshair,
  Gauge,
  Activity,
  DollarSign,
  ChevronRight,
  Filter,
  Layers,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Separator } from "../components/ui/separator";
import { toast } from "sonner";

const SECTOR_COLORS = {
  IT: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  Banking: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  "Financial Services": "bg-teal-500/10 text-teal-400 border-teal-500/30",
  Pharma: "bg-purple-500/10 text-purple-400 border-purple-500/30",
  Healthcare: "bg-violet-500/10 text-violet-400 border-violet-500/30",
  Auto: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  FMCG: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  Energy: "bg-red-500/10 text-red-400 border-red-500/30",
  Metal: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
  Infrastructure: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
  Cement: "bg-stone-500/10 text-stone-400 border-stone-500/30",
  "Capital Goods": "bg-amber-500/10 text-amber-400 border-amber-500/30",
  Defence: "bg-slate-500/10 text-slate-400 border-slate-500/30",
  Telecom: "bg-pink-500/10 text-pink-400 border-pink-500/30",
  Consumer: "bg-indigo-500/10 text-indigo-400 border-indigo-500/30",
  Chemicals: "bg-lime-500/10 text-lime-400 border-lime-500/30",
  "Green Energy": "bg-green-500/10 text-green-400 border-green-500/30",
  Shipping: "bg-sky-500/10 text-sky-400 border-sky-500/30",
  Logistics: "bg-sky-500/10 text-sky-400 border-sky-500/30",
  Realty: "bg-rose-500/10 text-rose-400 border-rose-500/30",
  Conglomerate: "bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/30",
  ETF: "bg-amber-500/10 text-amber-300 border-amber-500/30",
};

const API = `${process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"}/api`;

const SECTION_ICONS = {
  verdict: Target,
  why_now: Zap,
  technical: BarChart3,
  fundamental: DollarSign,
  news: Newspaper,
  risk: AlertTriangle,
  trading_plan: Crosshair,
  timeframe: Activity,
  confidence: Gauge,
};

const SECTION_COLORS = {
  verdict: "text-purple-400",
  why_now: "text-amber-400",
  technical: "text-cyan-400",
  fundamental: "text-emerald-400",
  news: "text-blue-400",
  risk: "text-red-400",
  trading_plan: "text-orange-400",
  timeframe: "text-sky-400",
  confidence: "text-violet-400",
};

const SECTION_BG = {
  verdict: "border-purple-500/20 bg-purple-500/5",
  why_now: "border-amber-500/20 bg-amber-500/5",
  technical: "border-cyan-500/20 bg-cyan-500/5",
  fundamental: "border-emerald-500/20 bg-emerald-500/5",
  news: "border-blue-500/20 bg-blue-500/5",
  risk: "border-red-500/20 bg-red-500/5",
  trading_plan: "border-orange-500/20 bg-orange-500/5",
  timeframe: "border-sky-500/20 bg-sky-500/5",
  confidence: "border-violet-500/20 bg-violet-500/5",
};

const TAB_SECTIONS = {
  hybrid: ["verdict", "why_now", "technical", "fundamental", "news", "risk", "trading_plan", "timeframe", "confidence"],
  momentum: ["verdict", "why_now", "technical", "trading_plan", "timeframe", "confidence"],
  fundamental: ["verdict", "fundamental", "news", "risk", "confidence"],
};

function parseAnalysisSections(text) {
  if (!text) return [];

  const sectionPattern = /\*\*(\d+)\.\s*([^*]+?)\*\*/g;
  const matches = [...text.matchAll(sectionPattern)];

  if (matches.length === 0) {
    return [{ id: "full", key: "verdict", title: "Analysis", content: text.trim() }];
  }

  const sections = [];
  for (let i = 0; i < matches.length; i++) {
    const num = matches[i][1];
    const rawTitle = matches[i][2].trim();
    const startIdx = matches[i].index + matches[i][0].length;
    const endIdx = i + 1 < matches.length ? matches[i + 1].index : text.length;
    const content = text.slice(startIdx, endIdx).trim();

    const keyMap = {
      "1": "verdict",
      "2": "why_now",
      "3": "technical",
      "4": "fundamental",
      "5": "news",
      "6": "risk",
      "7": "trading_plan",
      "8": "timeframe",
      "9": "confidence",
    };

    sections.push({
      id: `section-${num}`,
      num,
      key: keyMap[num] || `section_${num}`,
      title: rawTitle.replace(/\(.*?\)\s*$/, "").trim(),
      content,
    });
  }
  return sections;
}

function VerdictCard({ content }) {
  const verdictLine = content.split("\n").find((l) => l.trim().length > 0) || content;

  const actionMatch = verdictLine.match(/\[(BUY|SHORT|SELL|HOLD)\]/i);
  const action = actionMatch ? actionMatch[1].toUpperCase() : null;
  const priceMatch = verdictLine.match(/at\s*Rs\.?\s*([\d,.]+)/i);
  const targetMatch = verdictLine.match(/Target[:\s]*Rs\.?\s*([\d,.]+)/i);
  const slMatch = verdictLine.match(/Stop[- ]?Loss[:\s]*Rs\.?\s*([\d,.]+)/i);
  const rrMatch = verdictLine.match(/Risk[- ]?Reward[:\s]*([\d.:]+)/i);
  const horizonMatch = verdictLine.match(/Horizon[:\s]*([^|]+)/i);

  const actionColor =
    action === "BUY" ? "bg-emerald-500" :
    action === "SHORT" ? "bg-orange-500" :
    action === "SELL" ? "bg-red-500" : "bg-amber-500";
  const actionBorder =
    action === "BUY" ? "border-emerald-500/40" :
    action === "SHORT" ? "border-orange-500/40" :
    action === "SELL" ? "border-red-500/40" : "border-amber-500/40";

  return (
    <div className={`rounded-xl border-2 ${actionBorder} p-5`}>
      <div className="flex items-center gap-4 flex-wrap">
        {action && (
          <div className="flex items-center gap-2">
            <span className={`${actionColor} text-white font-bold text-lg px-5 py-1.5 rounded-lg tracking-wider`}>
              {action}
            </span>
            {action === "SHORT" && (
              <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded bg-orange-500/20 text-orange-300 border border-orange-500/30">
                Intraday
              </span>
            )}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          {priceMatch && (
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Entry</span>
              <span className="font-mono font-bold text-foreground text-base">Rs.{priceMatch[1]}</span>
            </div>
          )}
          {targetMatch && (
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wider text-emerald-400">Target</span>
              <span className="font-mono font-bold text-emerald-400 text-base">Rs.{targetMatch[1]}</span>
            </div>
          )}
          {slMatch && (
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wider text-red-400">Stop-Loss</span>
              <span className="font-mono font-bold text-red-400 text-base">Rs.{slMatch[1]}</span>
            </div>
          )}
          {horizonMatch && (
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Horizon</span>
              <span className="font-mono font-semibold text-foreground">{horizonMatch[1].trim()}</span>
            </div>
          )}
          {rrMatch && (
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">R:R</span>
              <span className="font-mono font-semibold text-foreground">{rrMatch[1].trim()}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TradingPlanCard({ content }) {
  const lines = content
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  const planItems = lines.map((line) => {
    const cleaned = line.replace(/^[-•]\s*/, "");
    const isEntry = /ideal entry|entry/i.test(cleaned);
    const isTarget = /target\s*\d/i.test(cleaned);
    const isSL = /stop[- ]?loss/i.test(cleaned);
    const isPosition = /position|volatility/i.test(cleaned);

    let icon = ChevronRight;
    let color = "text-muted-foreground";
    if (isEntry) { icon = Crosshair; color = "text-blue-400"; }
    else if (isTarget) { icon = Target; color = "text-emerald-400"; }
    else if (isSL) { icon = ShieldAlert; color = "text-red-400"; }
    else if (isPosition) { icon = Activity; color = "text-amber-400"; }

    const priceMatch = cleaned.match(/Rs\.?\s*([\d,.]+)/);
    const Icon = icon;

    return (
      <div key={cleaned} className="flex items-start gap-3 py-2">
        <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${color}`} />
        <div className="flex-1 text-sm">
          {priceMatch ? (
            <span>
              {cleaned.split(/Rs\.?\s*[\d,.]+/)[0]}
              <span className={`font-mono font-bold ${color}`}>Rs.{priceMatch[1]}</span>
              {cleaned.split(/Rs\.?\s*[\d,.]+/).slice(1).join("")}
            </span>
          ) : (
            <span>{cleaned}</span>
          )}
        </div>
      </div>
    );
  });

  return <div className="divide-y divide-border-subtle">{planItems}</div>;
}

function ConfidenceCard({ content }) {
  const scoreMatch = content.match(/(\d+)\s*\/\s*100/);
  const score = scoreMatch ? parseInt(scoreMatch[1], 10) : null;
  const justification = content
    .replace(/\d+\s*\/\s*100/, "")
    .replace(/^\s*[:\-–]\s*/, "")
    .trim();

  const color = score >= 70 ? "text-emerald-400" : score >= 50 ? "text-amber-400" : "text-red-400";
  const bg = score >= 70 ? "bg-emerald-500" : score >= 50 ? "bg-amber-500" : "bg-red-500";

  return (
    <div className="flex items-center gap-5">
      {score !== null && (
        <div className="flex flex-col items-center">
          <span className={`text-4xl font-bold font-mono ${color}`}>{score}</span>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">/ 100</span>
          <div className="w-20 h-1.5 bg-surface-primary rounded-full mt-2 overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${score}%` }}
              transition={{ duration: 0.8 }}
              className={`h-full rounded-full ${bg}`}
            />
          </div>
        </div>
      )}
      {justification && <p className="text-sm text-muted-foreground flex-1 leading-relaxed">{justification}</p>}
    </div>
  );
}

function BulletSection({ content }) {
  const lines = content
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  return (
    <div className="space-y-2">
      {lines.map((line, i) => {
        const isBullet = /^[-•]/.test(line);
        const cleaned = line.replace(/^[-•]\s*/, "");

        const inlineBold = cleaned.replace(
          /\*\*([^*]+)\*\*/g,
          (_, m) => `<strong class="text-foreground font-semibold">${m}</strong>`
        );

        if (isBullet) {
          return (
            <div key={i} className="flex items-start gap-2.5 ml-1">
              <span className="text-ai-glow mt-1 text-xs">●</span>
              <span
                className="text-sm text-muted-foreground leading-relaxed"
                dangerouslySetInnerHTML={{ __html: inlineBold }}
              />
            </div>
          );
        }

        const isSubHeading = /^[A-Z][\w\s]+:/.test(cleaned);
        if (isSubHeading) {
          const [head, ...rest] = cleaned.split(":");
          return (
            <div key={i} className="mt-3 first:mt-0">
              <span className="text-xs font-semibold uppercase tracking-wider text-foreground/80">{head}:</span>
              <span className="text-sm text-muted-foreground ml-1">{rest.join(":")}</span>
            </div>
          );
        }

        return (
          <p
            key={i}
            className="text-sm text-muted-foreground leading-relaxed"
            dangerouslySetInnerHTML={{ __html: inlineBold }}
          />
        );
      })}
    </div>
  );
}

function TechnicalSection({ content }) {
  const lines = content
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        const isBullet = /^[-•]/.test(line);
        const cleaned = line.replace(/^[-•]\s*/, "");

        const labelMatch = cleaned.match(/^([^:]+):\s*(.*)/);
        if (labelMatch) {
          const label = labelMatch[1].trim();
          const value = labelMatch[2].trim();

          const highlightedValue = value
            .replace(/Rs\.?\s*([\d,.]+)/g, '<span class="font-mono font-bold text-foreground">Rs.$1</span>')
            .replace(
              /\b(bullish|accumulation|expanding|strong)\b/gi,
              '<span class="text-emerald-400 font-medium">$1</span>'
            )
            .replace(
              /\b(bearish|distribution|contracting|weak)\b/gi,
              '<span class="text-red-400 font-medium">$1</span>'
            );

          return (
            <div key={i} className={`flex gap-3 py-1.5 ${isBullet ? "ml-1" : ""}`}>
              {isBullet && <span className="text-cyan-400 mt-0.5 text-xs">▸</span>}
              <span className="text-xs font-semibold uppercase tracking-wider text-cyan-400/80 w-28 shrink-0 mt-0.5">
                {label}
              </span>
              <span
                className="text-sm text-muted-foreground flex-1"
                dangerouslySetInnerHTML={{ __html: highlightedValue }}
              />
            </div>
          );
        }

        return (
          <p key={i} className="text-sm text-muted-foreground ml-1 py-0.5">
            {isBullet && <span className="text-cyan-400 mr-2 text-xs">▸</span>}
            {cleaned}
          </p>
        );
      })}
    </div>
  );
}

function SectionRenderer({ section }) {
  const Icon = SECTION_ICONS[section.key] || Sparkles;
  const color = SECTION_COLORS[section.key] || "text-ai-glow";
  const bg = SECTION_BG[section.key] || "border-border-subtle bg-surface-secondary";

  if (section.key === "verdict") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <VerdictCard content={section.content} />
      </motion.div>
    );
  }

  const renderContent = () => {
    switch (section.key) {
      case "trading_plan":
        return <TradingPlanCard content={section.content} />;
      case "confidence":
        return <ConfidenceCard content={section.content} />;
      case "technical":
        return <TechnicalSection content={section.content} />;
      default:
        return <BulletSection content={section.content} />;
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: parseInt(section.num || "1") * 0.06 }}
      className={`rounded-lg border ${bg} overflow-hidden`}
    >
      <div className="flex items-center gap-2.5 px-4 py-3 border-b border-white/5">
        <Icon className={`w-4 h-4 ${color}`} />
        <h3 className={`font-heading font-semibold text-sm ${color}`}>{section.title}</h3>
      </div>
      <div className="px-4 py-3">{renderContent()}</div>
    </motion.div>
  );
}

export default function AIResearch() {
  const location = useLocation();
  const navigate = useNavigate();
  const [stocks, setStocks] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [selectedSector, setSelectedSector] = useState("all");
  const [selectedStock, setSelectedStock] = useState(location.state?.stock || null);
  const [searchTerm, setSearchTerm] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [scanningAll, setScanningAll] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [viewTab, setViewTab] = useState("hybrid");
  const [historyList, setHistoryList] = useState([]);

  const autoSelectDone = useRef(!!selectedStock);

  useEffect(() => {
    fetchStocks();
    fetchHistory();
    if (!selectedStock) fetchLatestAnalysis();
  }, []);

  useEffect(() => {
    if (selectedStock) fetchLatestAnalysis(selectedStock.symbol);
  }, [selectedStock?.symbol]);

  useEffect(() => {
    if (!autoSelectDone.current && stocks.length > 0 && analysis?.stock_symbol && !selectedStock) {
      autoSelectDone.current = true;
      const match = stocks.find((s) => s.symbol === analysis.stock_symbol);
      if (match) setSelectedStock(match);
    }
  }, [stocks, analysis, selectedStock]);

  const fetchStocks = async () => {
    try {
      const [stocksRes, sectorsRes] = await Promise.all([
        axios.get(`${API}/stocks`),
        axios.get(`${API}/stocks/sectors`),
      ]);
      setStocks(stocksRes.data);
      setSectors(sectorsRes.data);
    } catch (e) {
      console.error("Failed to fetch stocks:", e);
    }
  };

  const refreshPrices = async () => {
    setRefreshing(true);
    try {
      const res = await axios.post(`${API}/stocks/refresh`);
      await fetchStocks();
      toast.success(`Updated ${res.data.updated}/${res.data.total} stock prices`);
    } catch (e) {
      toast.error("Failed to refresh prices");
    } finally {
      setRefreshing(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await axios.get(`${API}/ai/analysis/history?limit=20`);
      setHistoryList(res.data || []);
    } catch {
      /* non-critical */
    }
  };

  const fetchLatestAnalysis = async (symbol) => {
    try {
      const url = symbol ? `${API}/ai/analysis/latest/${symbol}` : `${API}/ai/analysis/latest`;
      const res = await axios.get(url);
      setAnalysis(res.data || null);
    } catch (e) {
      console.error("Failed to fetch latest analysis:", e);
    }
  };

  const runAnalysis = async () => {
    if (!selectedStock) {
      toast.error("Please select a stock first");
      return;
    }
    setAnalyzing(true);
    setAnalysis(null);

    try {
      const res = await axios.post(`${API}/ai/analyze`, {
        stock_symbol: selectedStock.symbol,
        analysis_type: "hybrid",
      });
      setAnalysis(res.data);
      fetchHistory();

      const sig = res.data?.key_signals?.signal_generated;
      if (sig) {
        toast.success(`${sig.action} signal generated and added to Trade Queue`);
      } else {
        toast.success("Analysis complete — no actionable signal right now");
      }
    } catch (error) {
      console.error("Analysis failed:", error);
      toast.error("Failed to analyze stock");
    } finally {
      setAnalyzing(false);
    }
  };

  const scanAllStocks = async () => {
    setScanningAll(true);
    try {
      const res = await axios.post(`${API}/ai/scan-all`);
      toast.success(`Scan complete: ${res.data.generated} new recommendations`);
      navigate("/trades");
    } catch (error) {
      console.error("Scan failed:", error);
      toast.error("Failed to run scan");
    } finally {
      setScanningAll(false);
    }
  };

  const filteredStocks = stocks.filter((s) => {
    const matchesSearch =
      s.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSector = selectedSector === "all" || s.sector === selectedSector;
    return matchesSearch && matchesSector;
  });

  const handleHistoryClick = (item) => {
    const match = stocks.find((s) => s.symbol === item.stock_symbol);
    if (match) setSelectedStock(match);
    else setSelectedStock({ symbol: item.stock_symbol, name: item.stock_symbol });
  };

  const timeAgo = (iso) => {
    if (!iso) return "";
    const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  const analysisMode = analysis?.key_signals?.mode;
  const signalGenerated = analysis?.key_signals?.signal_generated;

  const parsedSections = parseAnalysisSections(analysis?.analysis);
  const visibleSections = parsedSections.filter((s) =>
    TAB_SECTIONS[viewTab]?.includes(s.key)
  );
  const sectionsToShow = visibleSections.length > 0 ? visibleSections : parsedSections;

  return (
    <div data-testid="ai-research-page" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight flex items-center gap-3">
            <Brain className="w-8 h-8 text-ai-glow" />
            Research
          </h1>
          <p className="text-muted-foreground mt-1">
            {stocks.length} stocks across {sectors.length} sectors — select any stock for AI analysis
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={refreshPrices} variant="outline" disabled={refreshing}>
            <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
            Refresh Prices
          </Button>
          <Button
            onClick={scanAllStocks}
            disabled={scanningAll}
            className="bg-ai-glow/20 text-ai-glow border border-ai-glow/30 hover:bg-ai-glow/30"
          >
            {scanningAll ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Zap className="w-4 h-4 mr-2" />
            )}
            Scan All Stocks
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Stock Selection */}
        <Card className="bg-surface-primary border-border-subtle">
          <CardHeader className="border-b border-border-subtle pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="font-heading text-lg flex items-center gap-2">
                <Layers className="w-4 h-4 text-muted-foreground" />
                Stocks
              </CardTitle>
              <span className="text-xs text-muted-foreground">{filteredStocks.length}</span>
            </div>
          </CardHeader>
          <CardContent className="p-4">
            <div className="relative mb-3">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search symbol or name..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 bg-surface-secondary border-border-subtle"
              />
            </div>

            {/* Sector Filter */}
            <div className="flex items-center gap-2 mb-3">
              <Filter className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
              <select
                value={selectedSector}
                onChange={(e) => setSelectedSector(e.target.value)}
                className="w-full bg-surface-secondary border border-border-subtle rounded-md px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="all">All Sectors</option>
                {sectors.map((s) => (
                  <option key={s.sector} value={s.sector}>{s.sector} ({s.count})</option>
                ))}
              </select>
            </div>

            <ScrollArea className="h-[350px]">
              <div className="space-y-1.5">
                {filteredStocks.map((stock) => (
                  <motion.div
                    key={stock.id || stock.symbol}
                    whileHover={{ scale: 1.01 }}
                    onClick={() => setSelectedStock(stock)}
                    className={`p-2.5 rounded-lg cursor-pointer transition-colors ${
                      selectedStock?.symbol === stock.symbol
                        ? "bg-ai-glow/20 border border-ai-glow/30"
                        : "bg-surface-secondary hover:bg-secondary"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <div className="flex items-center gap-2 min-w-0">
                        <p className="font-mono font-semibold text-sm">{stock.symbol}</p>
                        <Badge className={`text-[9px] py-0 px-1.5 border ${SECTOR_COLORS[stock.sector] || "bg-secondary"}`}>
                          {stock.sector}
                        </Badge>
                      </div>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-1 mb-1">{stock.name}</p>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-foreground">
                        {stock.current_price > 0
                          ? `₹${Number(stock.current_price).toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                          : "—"}
                      </span>
                      {stock.change_percent != null && stock.change_percent !== 0 && (
                        <span className={`font-mono text-[11px] flex items-center gap-0.5 ${stock.change_percent >= 0 ? "text-signal-success" : "text-signal-danger"}`}>
                          {stock.change_percent >= 0 ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
                          {stock.change_percent >= 0 ? "+" : ""}{Number(stock.change_percent).toFixed(2)}%
                        </span>
                      )}
                    </div>
                  </motion.div>
                ))}
                {filteredStocks.length === 0 && (
                  <div className="text-center py-6">
                    <Layers className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                    <p className="text-xs text-muted-foreground">No stocks found</p>
                  </div>
                )}
              </div>
            </ScrollArea>

            {/* Recent Analysis History */}
            {historyList.length > 0 && (
              <div className="mt-4 pt-4 border-t border-border-subtle">
                <div className="flex items-center gap-2 mb-3">
                  <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Recent Analyses
                  </span>
                </div>
                <ScrollArea className="h-[160px]">
                  <div className="space-y-1.5">
                    {historyList.map((item, idx) => (
                      <button
                        key={item.id || idx}
                        onClick={() => handleHistoryClick(item)}
                        className={`w-full text-left px-3 py-2 rounded-md transition-colors text-xs
                                   hover:bg-surface-secondary ${
                          selectedStock?.symbol === item.stock_symbol
                            ? "bg-ai-glow/10 border border-ai-glow/20"
                            : ""
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono font-semibold text-foreground">
                              {item.stock_symbol}
                            </span>
                            {(() => {
                              const action = item.key_signals?.action;
                              if (item.mode === "exit" || action === "SELL") {
                                return <ArrowDownCircle className="w-3 h-3 text-signal-danger" />;
                              }
                              if (action === "SHORT") {
                                return <TrendingDown className="w-3 h-3 text-orange-400" />;
                              }
                              if (item.mode === "entry" || action === "BUY") {
                                return <ArrowUpCircle className="w-3 h-3 text-signal-success" />;
                              }
                              return null;
                            })()}
                            {item.source === "agent_chat" && (
                              <MessageSquare className="w-3 h-3 text-purple-400" />
                            )}
                          </div>
                          <span
                            className={`font-mono font-bold ${
                              (item.confidence_score || 0) >= 70
                                ? "text-signal-success"
                                : (item.confidence_score || 0) >= 50
                                ? "text-signal-warning"
                                : "text-signal-danger"
                            }`}
                          >
                            {item.confidence_score || 0}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between mt-0.5">
                          <span className="text-muted-foreground/70">
                            {item.mode || item.analysis_type || "hybrid"}
                          </span>
                          <span className="text-muted-foreground/50">{timeAgo(item.created_at)}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Analysis Panel */}
        <div className="lg:col-span-3">
          <Card className="ai-panel min-h-[500px]">
            <CardHeader className="border-b border-ai-glow/20 relative z-10">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <CardTitle className="font-heading text-xl flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-ai-glow" />
                    {selectedStock ? `Analysis: ${selectedStock.symbol}` : "Select a Stock"}
                  </CardTitle>
                  {selectedStock && (
                    <p className="text-sm text-muted-foreground mt-1">{selectedStock.name}</p>
                  )}
                </div>
                {selectedStock && (
                  <Button
                    onClick={runAnalysis}
                    disabled={analyzing}
                    size="sm"
                    className="bg-ai-glow hover:bg-ai-glow/80 text-white"
                  >
                    {analyzing ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Analyzing...
                      </>
                    ) : (
                      <>
                        <Brain className="w-4 h-4 mr-2" />
                        Analyze
                      </>
                    )}
                  </Button>
                )}
              </div>
            </CardHeader>

            <CardContent className="p-6 relative z-10">
              {selectedStock ? (
                <>
                  {analysis ? (
                    <motion.div
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="space-y-5"
                    >
                      {/* Meta row */}
                      <div className="flex items-center flex-wrap gap-3 text-xs text-muted-foreground">
                        {analysis.created_at && (
                          <div className="flex items-center gap-1.5">
                            <RefreshCw className="w-3 h-3" />
                            <span>{new Date(analysis.created_at).toLocaleString()}</span>
                          </div>
                        )}
                        {analysisMode && (() => {
                          const sigAction = signalGenerated?.action;
                          const isShort = sigAction === "SHORT";
                          const isSell = analysisMode === "exit";
                          const badgeClass = isSell
                            ? "bg-signal-danger/20 text-signal-danger border-signal-danger/30"
                            : isShort
                            ? "bg-orange-500/20 text-orange-300 border-orange-500/30"
                            : "bg-signal-success/20 text-signal-success border-signal-success/30";
                          const label = isSell
                            ? "EXIT mode (in portfolio)"
                            : isShort
                            ? "ENTRY mode (SHORT - Intraday)"
                            : "ENTRY mode (BUY)";
                          const Icon = isSell || isShort ? ArrowDownCircle : ArrowUpCircle;
                          return (
                            <Badge className={`text-[10px] ${badgeClass}`}>
                              <Icon className="w-3 h-3 mr-1" />
                              {label}
                            </Badge>
                          );
                        })()}
                        {signalGenerated && (
                          <Badge className={`text-[10px] ${
                            signalGenerated.action === "SHORT"
                              ? "bg-orange-500/20 text-orange-300 border-orange-500/30"
                              : "bg-purple-500/20 text-purple-300 border-purple-500/30"
                          }`}>
                            <CheckCircle2 className="w-3 h-3 mr-1" />
                            {signalGenerated.action}{signalGenerated.action === "SHORT" ? " (Intraday)" : ""} signal added to Trade Queue
                          </Badge>
                        )}
                        {analysis.source === "agent_chat" && (
                          <Badge className="text-[10px] bg-purple-500/20 text-purple-300 border-purple-500/30">
                            <MessageSquare className="w-3 h-3 mr-1" />
                            via Agent Chat
                          </Badge>
                        )}
                      </div>

                      {/* View Tabs */}
                      <Tabs value={viewTab} onValueChange={setViewTab}>
                        <TabsList className="bg-surface-secondary border border-border-subtle">
                          <TabsTrigger value="hybrid" className="text-xs gap-1.5">
                            <Activity className="w-3.5 h-3.5" />
                            Full Report
                          </TabsTrigger>
                          <TabsTrigger value="momentum" className="text-xs gap-1.5">
                            <TrendingUp className="w-3.5 h-3.5" />
                            Technical
                          </TabsTrigger>
                          <TabsTrigger value="fundamental" className="text-xs gap-1.5">
                            <DollarSign className="w-3.5 h-3.5" />
                            Fundamental
                          </TabsTrigger>
                        </TabsList>
                      </Tabs>

                      {/* Key Signals Pills */}
                      {analysis.key_signals &&
                        Object.keys(analysis.key_signals).length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(analysis.key_signals)
                              .filter(([k]) => !["mode", "signal_generated"].includes(k))
                              .map(([key, value]) => (
                                <span
                                  key={key}
                                  className="text-[10px] px-2.5 py-1 rounded-full bg-surface-secondary border border-border-subtle text-muted-foreground"
                                >
                                  {key.replace(/_/g, " ")}:{" "}
                                  <span
                                    className={
                                      value === "bullish" || value === "positive" || value === "BUY"
                                        ? "text-signal-success font-semibold"
                                        : value === "bearish" || value === "negative" || value === "SELL" || value === "SHORT"
                                        ? "text-signal-danger font-semibold"
                                        : "text-foreground"
                                    }
                                  >
                                    {typeof value === "string" ? value : JSON.stringify(value)}
                                  </span>
                                </span>
                              ))}
                          </div>
                        )}

                      <Separator className="bg-border-subtle" />

                      {/* Sections */}
                      <ScrollArea className="h-[500px] pr-2">
                        <AnimatePresence mode="wait">
                          <motion.div
                            key={viewTab}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.15 }}
                            className="space-y-4"
                          >
                            {sectionsToShow.map((section) => (
                              <SectionRenderer key={section.id} section={section} />
                            ))}
                          </motion.div>
                        </AnimatePresence>
                      </ScrollArea>
                    </motion.div>
                  ) : (
                    <div className="text-center py-12">
                      <Brain className="w-16 h-16 text-ai-glow/30 mx-auto mb-4" />
                      <p className="text-muted-foreground">
                        Click &ldquo;Analyze&rdquo; to get AI insights
                      </p>
                      <p className="text-sm text-muted-foreground mt-2">
                        Stocks in your portfolio are evaluated for EXIT; others are scanned for ENTRY
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-20">
                  <Brain className="w-20 h-20 text-ai-glow/20 mx-auto mb-6" />
                  <h3 className="font-heading text-xl mb-2">Select a Stock to Analyze</h3>
                  <p className="text-muted-foreground max-w-md mx-auto">
                    Portfolio holdings are evaluated for EXIT signals; others are scanned for ENTRY
                    (BUY) signals. Signals are auto-added to the Trade Queue.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
