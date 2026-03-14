import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import { 
  Brain, 
  Search, 
  Loader2, 
  Sparkles,
  TrendingUp,
  Target,
  AlertTriangle,
  Zap,
  RefreshCw
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"}/api`;

export default function AIResearch() {
  const location = useLocation();
  const navigate = useNavigate();
  const [stocks, setStocks] = useState([]);
  const [selectedStock, setSelectedStock] = useState(location.state?.stock || null);
  const [searchTerm, setSearchTerm] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [scanningAll, setScanningAll] = useState(false);
  const [analysisType, setAnalysisType] = useState("hybrid");

  const autoSelectDone = useRef(!!selectedStock);

  useEffect(() => {
    fetchStocks();
    if (!selectedStock) fetchLatestAnalysis();
  }, []);

  useEffect(() => {
    if (selectedStock) {
      fetchLatestAnalysis(selectedStock.symbol);
    }
  }, [selectedStock?.symbol]);

  // Auto-select the stock from the latest analysis once stocks are loaded
  useEffect(() => {
    if (!autoSelectDone.current && stocks.length > 0 && analysis?.stock_symbol && !selectedStock) {
      autoSelectDone.current = true;
      const match = stocks.find(s => s.symbol === analysis.stock_symbol);
      if (match) setSelectedStock(match);
    }
  }, [stocks, analysis, selectedStock]);

  const fetchStocks = async () => {
    try {
      const res = await axios.get(`${API}/stocks`);
      setStocks(res.data);
    } catch (error) {
      console.error("Failed to fetch stocks:", error);
    }
  };

  const fetchLatestAnalysis = async (symbol) => {
    try {
      const url = symbol
        ? `${API}/ai/analysis/latest/${symbol}`
        : `${API}/ai/analysis/latest`;
      const res = await axios.get(url);
      setAnalysis(res.data || null);
    } catch (error) {
      console.error("Failed to fetch latest analysis:", error);
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
        analysis_type: analysisType
      });
      setAnalysis(res.data);
      toast.success("Analysis complete");
    } catch (error) {
      console.error("Analysis failed:", error);
      toast.error("Failed to analyze stock");
    } finally {
      setAnalyzing(false);
    }
  };

  const generateRecommendation = async () => {
    if (!selectedStock) {
      toast.error("Please select a stock first");
      return;
    }
    
    setGenerating(true);
    
    try {
      await axios.post(`${API}/ai/generate-recommendation/${selectedStock.symbol}`);
      toast.success("Trade recommendation generated! Check Trade Queue.");
    } catch (error) {
      console.error("Failed to generate recommendation:", error);
      toast.error("Failed to generate recommendation");
    } finally {
      setGenerating(false);
    }
  };

  const scanAllStocks = async () => {
    setScanningAll(true);
    try {
      const res = await axios.post(`${API}/ai/scan-all`);
      const { generated } = res.data;
      toast.success(`Scan complete: ${generated} new recommendations generated`);
      navigate("/queue");
    } catch (error) {
      console.error("Scan failed:", error);
      toast.error("Failed to run scan");
    } finally {
      setScanningAll(false);
    }
  };

  const filteredStocks = stocks.filter(s => 
    s.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const formatAnalysis = (text) => {
    if (!text) return null;
    
    // Split into sections and format
    const sections = text.split(/\*\*([^*]+)\*\*/g);
    return sections.map((section, idx) => {
      if (idx % 2 === 1) {
        // This is a header
        return (
          <h3 key={idx} className="font-heading font-semibold text-lg mt-6 mb-3 text-foreground flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-ai-glow" />
            {section}
          </h3>
        );
      }
      // This is content
      return (
        <div key={idx} className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
          {section.split('\n').map((line, lineIdx) => {
            if (line.trim().startsWith('-') || line.trim().startsWith('•')) {
              return (
                <div key={lineIdx} className="flex items-start gap-2 my-1 ml-4">
                  <span className="text-ai-glow mt-1.5">•</span>
                  <span>{line.replace(/^[-•]\s*/, '')}</span>
                </div>
              );
            }
            return <p key={lineIdx} className="my-1">{line}</p>;
          })}
        </div>
      );
    });
  };

  return (
    <div data-testid="ai-research-page" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight flex items-center gap-3">
            <Brain className="w-8 h-8 text-ai-glow" />
            AI Research
          </h1>
          <p className="text-muted-foreground mt-1">Deep analysis powered by Gemini 2.5 Flash</p>
        </div>
        <Button 
          onClick={scanAllStocks}
          disabled={scanningAll}
          className="bg-ai-glow/20 text-ai-glow border border-ai-glow/30 hover:bg-ai-glow/30"
          data-testid="scan-all-btn"
        >
          {scanningAll ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <Zap className="w-4 h-4 mr-2" />
          )}
          Scan All Stocks
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Stock Selection */}
        <Card className="bg-surface-primary border-border-subtle">
          <CardHeader className="border-b border-border-subtle pb-3">
            <CardTitle className="font-heading text-lg">Select Stock</CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search stocks..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 bg-surface-secondary border-border-subtle"
                data-testid="stock-search"
              />
            </div>
            
            <ScrollArea className="h-[400px]">
              <div className="space-y-2">
                {filteredStocks.map((stock) => (
                  <motion.div
                    key={stock.id}
                    whileHover={{ scale: 1.02 }}
                    onClick={() => setSelectedStock(stock)}
                    className={`p-3 rounded-lg cursor-pointer transition-colors ${
                      selectedStock?.symbol === stock.symbol 
                        ? 'bg-ai-glow/20 border border-ai-glow/30' 
                        : 'bg-surface-secondary hover:bg-secondary'
                    }`}
                    data-testid={`stock-option-${stock.symbol}`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-mono font-semibold">{stock.symbol}</p>
                        <p className="text-xs text-muted-foreground line-clamp-1">{stock.name}</p>
                      </div>
                      <Badge className="text-[10px]">{stock.sector}</Badge>
                    </div>
                  </motion.div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Analysis Panel */}
        <div className="lg:col-span-2">
          <Card className="ai-panel min-h-[500px]">
            <CardHeader className="border-b border-ai-glow/20 relative z-10">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="font-heading text-xl flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-ai-glow" />
                    {selectedStock ? `Analysis: ${selectedStock.symbol}` : 'Select a Stock'}
                  </CardTitle>
                  {selectedStock && (
                    <p className="text-sm text-muted-foreground mt-1">{selectedStock.name}</p>
                  )}
                </div>
                
                {selectedStock && (
                  <div className="flex gap-2">
                    <Button
                      onClick={generateRecommendation}
                      disabled={generating}
                      size="sm"
                      className="bg-signal-success/20 text-signal-success border border-signal-success/30 hover:bg-signal-success/30"
                      data-testid="generate-rec-btn"
                    >
                      {generating ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <Target className="w-4 h-4 mr-2" />
                      )}
                      Generate Trade
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
            
            <CardContent className="p-6 relative z-10">
              {selectedStock ? (
                <>
                  {/* Analysis Type Tabs */}
                  <Tabs value={analysisType} onValueChange={setAnalysisType} className="mb-6">
                    <TabsList className="bg-surface-secondary border border-border-subtle">
                      <TabsTrigger value="fundamental">Fundamental</TabsTrigger>
                      <TabsTrigger value="momentum">Momentum</TabsTrigger>
                      <TabsTrigger value="hybrid">Hybrid</TabsTrigger>
                    </TabsList>
                  </Tabs>

                  <Button 
                    onClick={runAnalysis} 
                    disabled={analyzing}
                    className="w-full mb-6 bg-ai-glow hover:bg-ai-glow/80 text-white"
                    data-testid="run-analysis-btn"
                  >
                    {analyzing ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Analyzing with AI...
                      </>
                    ) : (
                      <>
                        <Brain className="w-4 h-4 mr-2" />
                        Run {analysisType.charAt(0).toUpperCase() + analysisType.slice(1)} Analysis
                      </>
                    )}
                  </Button>

                  {/* Analysis Results */}
                  {analysis ? (
                    <motion.div
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="space-y-4"
                    >
                      {/* Analysis Meta */}
                      {analysis.created_at && (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <RefreshCw className="w-3 h-3" />
                          <span>
                            Analyzed {new Date(analysis.created_at).toLocaleString()}
                            {analysis.analysis_type && ` · ${analysis.analysis_type}`}
                          </span>
                        </div>
                      )}

                      {/* Confidence + Horizon + Key Signals */}
                      <div className="flex flex-col gap-3 p-4 bg-surface-secondary rounded-lg">
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <p className="data-label">AI Confidence Score</p>
                            <div className="flex items-center gap-2 mt-2">
                              <div className="flex-1 h-2 bg-surface-primary rounded-full overflow-hidden">
                                <motion.div
                                  initial={{ width: 0 }}
                                  animate={{ width: `${analysis.confidence_score}%` }}
                                  className={`h-full ${
                                    analysis.confidence_score >= 70 ? 'bg-signal-success' :
                                    analysis.confidence_score >= 50 ? 'bg-signal-warning' : 'bg-signal-danger'
                                  }`}
                                />
                              </div>
                              <span className="data-value">{analysis.confidence_score.toFixed(0)}%</span>
                            </div>
                          </div>
                          {analysis.trade_horizon && (
                            <Badge className={`ml-4 text-xs ${
                              analysis.trade_horizon === 'short_term' ? 'bg-signal-warning/20 text-signal-warning border-signal-warning/30' :
                              analysis.trade_horizon === 'long_term' ? 'bg-ai-glow/20 text-ai-glow border-ai-glow/30' :
                              'bg-signal-success/20 text-signal-success border-signal-success/30'
                            }`}>
                              {analysis.trade_horizon === 'short_term' ? 'Short Term (1-2w)' :
                               analysis.trade_horizon === 'long_term' ? 'Long Term (3-12m)' :
                               'Medium Term (1-3m)'}
                            </Badge>
                          )}
                        </div>
                        {analysis.key_signals && Object.keys(analysis.key_signals).length > 0 && (
                          <div className="flex flex-wrap gap-2 pt-2 border-t border-border-subtle">
                            {Object.entries(analysis.key_signals).map(([key, value]) => (
                              <span key={key} className="text-[10px] px-2 py-0.5 rounded-full bg-surface-primary text-muted-foreground">
                                {key.replace(/_/g, ' ')}: <span className={
                                  value === 'bullish' || value === 'positive' || value === 'BUY' ? 'text-signal-success' :
                                  value === 'bearish' || value === 'negative' || value === 'SELL' ? 'text-signal-danger' :
                                  'text-foreground'
                                }>{value}</span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Full Analysis */}
                      <ScrollArea className="h-[400px] pr-4">
                        <div className="prose prose-invert max-w-none">
                          {formatAnalysis(analysis.analysis)}
                        </div>
                      </ScrollArea>
                    </motion.div>
                  ) : (
                    <div className="text-center py-12">
                      <Brain className="w-16 h-16 text-ai-glow/30 mx-auto mb-4" />
                      <p className="text-muted-foreground">Click "Run Analysis" to get AI insights</p>
                      <p className="text-sm text-muted-foreground mt-2">
                        Analysis includes fundamentals, technicals, and trading recommendation
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-20">
                  <Brain className="w-20 h-20 text-ai-glow/20 mx-auto mb-6" />
                  <h3 className="font-heading text-xl mb-2">Select a Stock to Analyze</h3>
                  <p className="text-muted-foreground max-w-md mx-auto">
                    Choose a stock from the list to run AI-powered fundamental and technical analysis
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
