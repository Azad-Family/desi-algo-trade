import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Bot,
  User,
  TrendingUp,
  TrendingDown,
  Target,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
  Loader2,
  RefreshCw,
  Sparkles,
  Brain,
  PanelRightOpen,
  PanelRightClose,
  Clock,
  RotateCcw,
  Wallet,
  Search,
  Zap,
  BarChart3,
  FlaskConical,
  Globe,
  AlertTriangle,
  ArrowUpDown,
  Newspaper,
} from "lucide-react";
import { Card, CardContent } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../components/ui/tooltip";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"}/api`;
const USER_NAME = "Azad";

// ---------------------------------------------------------------------------
// Markdown renderer
// ---------------------------------------------------------------------------
function renderMarkdown(text) {
  if (!text) return null;
  return text.split("\n").map((line, i) => {
    if (line.startsWith("### "))
      return <h4 key={i} className="text-sm font-bold text-foreground mt-3 mb-1">{fmt(line.slice(4))}</h4>;
    if (line.startsWith("## "))
      return <h3 key={i} className="text-base font-bold text-foreground mt-4 mb-1">{fmt(line.slice(3))}</h3>;
    if (line.startsWith("# "))
      return <h2 key={i} className="text-lg font-bold text-foreground mt-4 mb-2">{fmt(line.slice(2))}</h2>;
    if (line.startsWith("- ") || line.startsWith("* "))
      return <li key={i} className="ml-4 text-sm text-muted-foreground list-disc">{fmt(line.slice(2))}</li>;
    if (/^\d+\.\s/.test(line))
      return <li key={i} className="ml-4 text-sm text-muted-foreground list-decimal">{fmt(line.replace(/^\d+\.\s/, ""))}</li>;
    if (line.trim() === "") return <div key={i} className="h-2" />;
    return <p key={i} className="text-sm text-muted-foreground leading-relaxed">{fmt(line)}</p>;
  });
}
function fmt(t) {
  return t.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i} className="text-foreground font-semibold">{p.slice(2, -2)}</strong>;
    if (p.startsWith("*") && p.endsWith("*")) return <em key={i}>{p.slice(1, -1)}</em>;
    return p;
  });
}

// ---------------------------------------------------------------------------
// Block renderers (unchanged logic, compact)
// ---------------------------------------------------------------------------
function TextBlock({ content }) {
  return <div className="space-y-0.5">{renderMarkdown(content)}</div>;
}

function StockCardsBlock({ data, onStockClick }) {
  if (!data?.length) return null;
  return (
    <div className="flex gap-3 overflow-x-auto pb-2 custom-scrollbar">
      {data.map((s) => (
        <motion.div key={s.symbol} whileHover={{ scale: 1.02 }} className="min-w-[200px] max-w-[240px] cursor-pointer" onClick={() => onStockClick(s.symbol)}>
          <Card className="bg-surface-primary border-border-subtle hover:border-border-active transition-colors h-full">
            <CardContent className="p-3">
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-mono font-bold text-foreground text-sm">{s.symbol}</span>
                {s.change_percent !== undefined && s.change_percent !== 0 && (
                  <span className={`text-xs font-mono font-semibold ${s.change_percent >= 0 ? "text-signal-success" : "text-signal-danger"}`}>
                    {s.change_percent >= 0 ? "+" : ""}{s.change_percent.toFixed(2)}%
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground truncate mb-1">{s.name}</p>
              {s.price > 0 && <p className="text-sm font-mono text-foreground mb-1">Rs.{s.price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</p>}
              {s.sector && <Badge variant="outline" className="text-[10px]">{s.sector}</Badge>}
              {s.rationale && <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{s.rationale}</p>}
            </CardContent>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}

function AnalysisBlock({ data }) {
  const [expanded, setExpanded] = useState(false);
  if (!data) return null;
  const preview = data.analysis_text?.slice(0, 300) + (data.analysis_text?.length > 300 ? "..." : "");
  const ks = data.key_signals || {};
  const action = ks.action;
  const hasSignals = action && action !== "HOLD";

  return (
    <div className="ai-panel p-4 my-2">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-purple-400" />
          <span className="font-bold text-foreground text-sm">{data.name} ({data.symbol})</span>
          {data.sector && <Badge variant="outline" className="text-[10px]">{data.sector}</Badge>}
        </div>
        <div className="flex items-center gap-2">
          {action && (
            <Badge className={`text-[10px] ${action === "BUY" ? "badge-buy" : action === "SELL" || action === "SHORT" ? "badge-sell" : "badge-pending"}`}>
              {action}
            </Badge>
          )}
          {data.confidence_score > 0 && (
            <Badge className={`text-[10px] ${data.confidence_score >= 70 ? "badge-buy" : data.confidence_score >= 40 ? "badge-pending" : "badge-sell"}`}>
              {data.confidence_score}%
            </Badge>
          )}
          <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setExpanded(!expanded)}>
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </Button>
        </div>
      </div>

      {hasSignals && (
        <div className="flex gap-4 mb-3 px-2 py-2 rounded-md bg-surface-secondary/40">
          {ks.target_price > 0 && (
            <div className="flex items-center gap-1.5 text-xs">
              <Target className="w-3 h-3 text-signal-success" />
              <span className="text-muted-foreground">Target</span>
              <span className="font-mono font-semibold text-signal-success">{parseFloat(ks.target_price).toFixed(2)}</span>
            </div>
          )}
          {ks.stop_loss > 0 && (
            <div className="flex items-center gap-1.5 text-xs">
              <ShieldAlert className="w-3 h-3 text-signal-danger" />
              <span className="text-muted-foreground">SL</span>
              <span className="font-mono font-semibold text-signal-danger">{parseFloat(ks.stop_loss).toFixed(2)}</span>
            </div>
          )}
          {data.trade_horizon && (
            <div className="flex items-center gap-1.5 text-xs">
              <Clock className="w-3 h-3 text-muted-foreground" />
              <span className="text-muted-foreground">{data.trade_horizon.replace(/_/g, " ")}</span>
            </div>
          )}
        </div>
      )}

      <div className="space-y-1">{expanded ? renderMarkdown(data.analysis_text) : renderMarkdown(preview)}</div>
      {!expanded && data.analysis_text?.length > 300 && (
        <button className="text-xs text-purple-400 hover:text-purple-300 mt-2" onClick={() => setExpanded(true)}>Show full analysis</button>
      )}
    </div>
  );
}

function TradeSignalBlock({ data, onApprove, onReject }) {
  if (!data) return null;
  const isBuy = data.action === "BUY";
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={`recommendation-card ${isBuy ? "buy" : "sell"} my-2`}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono font-bold text-foreground">{data.symbol}</span>
            <Badge className={isBuy ? "badge-buy" : "badge-sell"}>{data.action}</Badge>
            {data.trade_horizon && <Badge variant="outline" className="text-[10px]">{data.trade_horizon.replace("_", " ")}</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">{data.name}</p>
        </div>
        {data.confidence > 0 && (
          <span className={`text-xs font-semibold ${data.confidence >= 70 ? "text-signal-success" : data.confidence >= 40 ? "text-signal-warning" : "text-signal-danger"}`}>{data.confidence}%</span>
        )}
      </div>
      <div className="grid grid-cols-4 gap-3 mb-3">
        <div><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Price</p><p className="text-sm font-mono text-foreground">{data.current_price?.toFixed(2)}</p></div>
        <div><p className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1"><Target className="w-3 h-3" /> Target</p><p className="text-sm font-mono text-signal-success">{data.target_price?.toFixed(2)}</p></div>
        <div><p className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1"><ShieldAlert className="w-3 h-3" /> SL</p><p className="text-sm font-mono text-signal-danger">{data.stop_loss?.toFixed(2) || "\u2014"}</p></div>
        <div><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Qty</p><p className="text-sm font-mono text-foreground">{data.quantity}</p></div>
      </div>
      {data.reasoning && <p className="text-xs text-muted-foreground mb-3 leading-relaxed">{data.reasoning}</p>}
      <div className="flex gap-2">
        <Button size="sm" className="bg-signal-success/20 text-signal-success hover:bg-signal-success/30 border border-signal-success/30" onClick={() => onApprove(data.rec_id, data.symbol)}>
          <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Approve
        </Button>
        <Button size="sm" variant="ghost" className="text-signal-danger hover:bg-signal-danger/10" onClick={() => onReject(data.rec_id, data.symbol)}>
          <XCircle className="w-3.5 h-3.5 mr-1" /> Reject
        </Button>
      </div>
    </motion.div>
  );
}

function SuggestedPromptsBlock({ data, onSelect }) {
  if (!data?.length) return null;
  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {data.map((p, i) => (
        <button key={i} onClick={() => onSelect(p)} className="px-3 py-1.5 text-xs rounded-full border border-border-subtle text-muted-foreground hover:text-foreground hover:border-border-active bg-surface-primary transition-colors">{p}</button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Typing indicator
// ---------------------------------------------------------------------------
function TypingIndicator() {
  return (
    <div className="flex items-center gap-3 py-3 px-4">
      <div className="w-7 h-7 rounded-full bg-purple-500/20 flex items-center justify-center flex-shrink-0">
        <Bot className="w-4 h-4 text-purple-400" />
      </div>
      <div className="flex items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <motion.div key={i} className="w-2 h-2 rounded-full bg-purple-400" animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1, 0.8] }} transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }} />
        ))}
        <span className="text-xs text-muted-foreground ml-2">Thinking...</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Time helpers
// ---------------------------------------------------------------------------
function timeAgo(iso) {
  if (!iso) return "";
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
}

// ---------------------------------------------------------------------------
// Right sidebar — Agent Activity Panel
// ---------------------------------------------------------------------------
function AgentActivityPanel({ status }) {
  if (!status) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-5 h-5 text-muted-foreground animate-spin" />
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-5">
        {/* Stock Analyst */}
        <AgentSection
          icon={<Brain className="w-4 h-4 text-cyan-400" />}
          title="Stock Analyst"
          accentBg="bg-cyan-500/10"
          accentBorder="border-cyan-500/20"
          badge={status.stock_analyst?.analyses_today > 0 ? `${status.stock_analyst.analyses_today} today` : null}
          badgeClass="bg-cyan-500/20 text-cyan-300 border-cyan-500/30"
        >
          {status.stock_analyst?.recent?.length > 0 ? (
            <div className="space-y-1.5">
              {status.stock_analyst.recent.map((a, i) => (
                <div key={i} className="flex items-center justify-between px-2 py-1.5 rounded-md bg-surface-secondary/50 text-xs">
                  <span className="font-mono font-semibold text-foreground">{a.stock_symbol}</span>
                  <div className="flex items-center gap-2">
                    <span className={`font-mono font-bold ${(a.confidence_score || 0) >= 70 ? "text-signal-success" : (a.confidence_score || 0) >= 50 ? "text-signal-warning" : "text-signal-danger"}`}>
                      {a.confidence_score || 0}%
                    </span>
                    <span className="text-muted-foreground/50">{timeAgo(a.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground/60 italic">No analyses yet</p>
          )}
        </AgentSection>

        {/* Buy Signal Agent */}
        <AgentSection
          icon={<TrendingUp className="w-4 h-4 text-emerald-400" />}
          title="Buy Signal"
          accentBg="bg-emerald-500/10"
          accentBorder="border-emerald-500/20"
          badge={status.buy_signal?.pending > 0 ? `${status.buy_signal.pending} pending` : null}
          badgeClass="bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
        >
          {status.buy_signal?.recent?.length > 0 ? (
            <div className="space-y-1.5">
              {status.buy_signal.recent.map((r, i) => (
                <div key={i} className="flex items-center justify-between px-2 py-1.5 rounded-md bg-surface-secondary/50 text-xs">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono font-semibold text-foreground">{r.stock_symbol}</span>
                    <StatusDot status={r.status} />
                  </div>
                  <div className="flex items-center gap-2">
                    {r.target_price > 0 && <span className="text-signal-success font-mono">{r.target_price.toFixed(0)}</span>}
                    <span className="text-muted-foreground/50">{timeAgo(r.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground/60 italic">No buy signals yet</p>
          )}
        </AgentSection>

        {/* Sell Signal Agent */}
        <AgentSection
          icon={<TrendingDown className="w-4 h-4 text-amber-400" />}
          title="Sell Signal"
          accentBg="bg-amber-500/10"
          accentBorder="border-amber-500/20"
          badge={status.sell_signal?.pending > 0 ? `${status.sell_signal.pending} pending` : null}
          badgeClass="bg-amber-500/20 text-amber-300 border-amber-500/30"
        >
          {status.sell_signal?.recent?.length > 0 ? (
            <div className="space-y-1.5">
              {status.sell_signal.recent.map((r, i) => (
                <div key={i} className="flex items-center justify-between px-2 py-1.5 rounded-md bg-surface-secondary/50 text-xs">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono font-semibold text-foreground">{r.stock_symbol}</span>
                    <StatusDot status={r.status} />
                  </div>
                  <div className="flex items-center gap-2">
                    {r.target_price > 0 && <span className="text-signal-danger font-mono">{r.target_price.toFixed(0)}</span>}
                    <span className="text-muted-foreground/50">{timeAgo(r.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground/60 italic">No sell signals yet</p>
          )}
        </AgentSection>
      </div>
    </ScrollArea>
  );
}

function AgentSection({ icon, title, accentBg, accentBorder, badge, badgeClass, children }) {
  return (
    <div className={`rounded-xl border ${accentBorder} ${accentBg} p-3`}>
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-surface-primary/50 flex items-center justify-center">{icon}</div>
          <span className="text-xs font-bold text-foreground">{title}</span>
        </div>
        {badge && <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${badgeClass}`}>{badge}</span>}
      </div>
      {children}
    </div>
  );
}

function StatusDot({ status }) {
  const cls =
    status === "pending" ? "bg-signal-warning" :
    status === "approved" ? "bg-signal-success" :
    status === "rejected" ? "bg-signal-danger" :
    "bg-muted-foreground";
  return <span className={`w-1.5 h-1.5 rounded-full ${cls}`} title={status} />;
}

// ---------------------------------------------------------------------------
// Welcome screen
// ---------------------------------------------------------------------------
function WelcomeScreen({ onPromptSelect, tradeMode }) {
  const actionCategories = [
    {
      label: "Market Intel",
      icon: Globe,
      color: "text-cyan-400",
      bg: "bg-cyan-500/10 border-cyan-500/20",
      actions: [
        { text: `${greeting()}! What's happening in the market?`, icon: Newspaper },
        { text: "What are the top movers today?", icon: BarChart3 },
      ],
    },
    {
      label: "Find Trades",
      icon: Search,
      color: "text-emerald-400",
      bg: "bg-emerald-500/10 border-emerald-500/20",
      actions: [
        { text: "I'm bullish on IT sector today", icon: TrendingUp },
        { text: "Find me short-term trading opportunities", icon: Zap },
      ],
    },
    {
      label: "Deep Analysis",
      icon: Brain,
      color: "text-purple-400",
      bg: "bg-purple-500/10 border-purple-500/20",
      actions: [
        { text: "Analyze INFY, TCS, HDFCBANK", icon: Sparkles },
        { text: "Run deep research on RELIANCE", icon: Search },
      ],
    },
    {
      label: "Portfolio",
      icon: Wallet,
      color: "text-amber-400",
      bg: "bg-amber-500/10 border-amber-500/20",
      actions: [
        { text: "Check my portfolio for sell signals", icon: ShieldAlert },
        { text: "How are my holdings doing?", icon: ArrowUpDown },
      ],
    },
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full px-4">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="text-center max-w-2xl w-full">
        <div className="w-16 h-16 rounded-2xl bg-purple-500/20 flex items-center justify-center mx-auto mb-6">
          <Bot className="w-8 h-8 text-purple-400" />
        </div>
        <h2 className="text-2xl font-bold text-foreground mb-2">
          {greeting()}, {USER_NAME}
        </h2>
        <p className="text-muted-foreground text-sm mb-2 leading-relaxed">
          Your AI trading assistant is ready. Tell me your market thesis and I'll handle the rest.
        </p>
        {tradeMode && (
          <p className="text-[10px] text-muted-foreground/60 mb-8 uppercase tracking-wider">
            Trading in <span className={tradeMode === "live" ? "text-signal-success font-semibold" : "text-amber-400 font-semibold"}>{tradeMode}</span> mode
          </p>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-left">
          {actionCategories.map((cat, ci) => (
            <motion.div
              key={ci}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.06 * ci }}
              className={`rounded-xl border p-4 ${cat.bg}`}
            >
              <div className="flex items-center gap-2 mb-3">
                <cat.icon className={`w-4 h-4 ${cat.color}`} />
                <span className={`text-xs font-bold uppercase tracking-wider ${cat.color}`}>{cat.label}</span>
              </div>
              <div className="space-y-2">
                {cat.actions.map((action, ai) => (
                  <button
                    key={ai}
                    onClick={() => onPromptSelect(action.text)}
                    className="w-full flex items-center gap-2.5 p-2.5 rounded-lg bg-surface-primary/50 hover:bg-surface-primary border border-transparent hover:border-border-subtle transition-colors text-sm text-muted-foreground hover:text-foreground"
                  >
                    <action.icon className="w-3.5 h-3.5 flex-shrink-0 opacity-50" />
                    <span className="text-left">{action.text}</span>
                  </button>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Market context block renderer
// ---------------------------------------------------------------------------
function MarketContextBlock({ data, content }) {
  if (content) return <TextBlock content={content} />;
  if (!data) return null;

  const indices = data.indices || {};
  const regime = data.regime || {};
  const ad = data.advance_decline || {};
  const sectors = data.sectors || {};

  const topSectors = Object.entries(sectors)
    .map(([name, info]) => ({ name, ...(typeof info === "object" ? info : { change: info }) }))
    .sort((a, b) => (b.change_1d || b.change || 0) - (a.change_1d || a.change || 0))
    .slice(0, 5);

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-primary p-4 my-2 space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <Globe className="w-4 h-4 text-cyan-400" />
        <span className="text-xs font-bold text-foreground uppercase tracking-wider">Market Overview</span>
        {regime.regime && (
          <Badge variant="outline" className={`text-[10px] ml-auto ${
            regime.regime.includes("BULL") ? "text-signal-success border-signal-success/30" :
            regime.regime.includes("BEAR") ? "text-signal-danger border-signal-danger/30" :
            "text-signal-warning border-signal-warning/30"
          }`}>{regime.regime.replace(/_/g, " ")}</Badge>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {["nifty50", "nifty_bank", "india_vix"].map((key) => {
          const idx = indices[key];
          if (!idx?.ltp) return null;
          const label = key === "nifty50" ? "Nifty 50" : key === "nifty_bank" ? "Bank Nifty" : "India VIX";
          const isVix = key === "india_vix";
          const changePct = idx.change_pct || 0;
          return (
            <div key={key} className="rounded-md bg-surface-secondary/50 px-3 py-2">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-0.5">{label}</p>
              <p className="text-sm font-mono font-semibold text-foreground">{idx.ltp.toLocaleString()}</p>
              {!isVix && <p className={`text-[10px] font-mono ${changePct >= 0 ? "text-signal-success" : "text-signal-danger"}`}>{changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%</p>}
              {isVix && <p className={`text-[10px] font-mono ${idx.ltp > 20 ? "text-signal-danger" : "text-muted-foreground"}`}>{idx.ltp > 20 ? "High volatility" : "Normal"}</p>}
            </div>
          );
        })}
        {ad.ad_ratio && (
          <div className="rounded-md bg-surface-secondary/50 px-3 py-2">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-0.5">Breadth</p>
            <p className="text-sm font-mono font-semibold text-foreground">{ad.ad_ratio.toFixed(2)}</p>
            <p className="text-[10px] text-muted-foreground">{ad.advancing}↑ {ad.declining}↓</p>
          </div>
        )}
      </div>

      {topSectors.length > 0 && (
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1.5">Top Sectors</p>
          <div className="flex gap-2 flex-wrap">
            {topSectors.map((s) => {
              const change = s.change_1d || s.change || 0;
              return (
                <span key={s.name} className={`text-[10px] font-mono px-2 py-1 rounded-md border ${change >= 0 ? "text-signal-success border-signal-success/20 bg-signal-success/5" : "text-signal-danger border-signal-danger/20 bg-signal-danger/5"}`}>
                  {s.name} {change >= 0 ? "+" : ""}{change.toFixed(1)}%
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Portfolio holdings table block
// ---------------------------------------------------------------------------
function HoldingsTableBlock({ data, onStockClick }) {
  if (!data?.length) return null;

  const hasPortfolioData = data[0]?.rationale?.includes("Qty:");
  if (!hasPortfolioData) return <StockCardsBlock data={data} onStockClick={onStockClick} />;

  return (
    <div className="rounded-lg border border-border-subtle overflow-hidden my-2">
      <table className="data-table w-full">
        <thead>
          <tr>
            <th>Stock</th>
            <th className="text-right">Price</th>
            <th className="text-right">P&L</th>
            <th className="text-right">Change</th>
          </tr>
        </thead>
        <tbody>
          {data.map((s) => (
            <tr key={s.symbol} className="cursor-pointer" onClick={() => onStockClick(s.symbol)}>
              <td>
                <span className="font-mono font-semibold text-foreground text-xs">{s.symbol}</span>
                <p className="text-[10px] text-muted-foreground truncate max-w-[120px]">{s.name}</p>
              </td>
              <td className="text-right">
                <span className="font-mono text-xs text-foreground">{s.price > 0 ? `Rs.${s.price.toFixed(2)}` : "--"}</span>
              </td>
              <td className="text-right">
                <span className={`font-mono text-xs font-semibold ${(s.change_percent || 0) >= 0 ? "text-signal-success" : "text-signal-danger"}`}>
                  {s.change_percent !== undefined ? `${s.change_percent >= 0 ? "+" : ""}${s.change_percent.toFixed(1)}%` : "--"}
                </span>
              </td>
              <td className="text-right">
                {(s.change_percent || 0) >= 0
                  ? <TrendingUp className="w-3.5 h-3.5 text-signal-success inline" />
                  : <TrendingDown className="w-3.5 h-3.5 text-signal-danger inline" />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat message
// ---------------------------------------------------------------------------
function ChatMessage({ message, onStockClick, onApprove, onReject, onPromptSelect, onRetry }) {
  const isUser = message.role === "user";
  const isError = message.isError;

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={`flex gap-3 py-3 px-4 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${isUser ? "bg-signal-success/20" : isError ? "bg-signal-danger/20" : "bg-purple-500/20"}`}>
        {isUser ? <User className="w-4 h-4 text-signal-success" /> : isError ? <AlertTriangle className="w-4 h-4 text-signal-danger" /> : <Bot className="w-4 h-4 text-purple-400" />}
      </div>
      <div className={`flex-1 min-w-0 ${isUser ? "text-right" : ""}`}>
        <div className={`flex items-center gap-2 mb-1 ${isUser ? "justify-end" : ""}`}>
          {isUser && <span className="text-[10px] text-muted-foreground/50">{USER_NAME}</span>}
          {message.timestamp && <span className="text-[10px] text-muted-foreground/30">{formatTime(message.timestamp)}</span>}
        </div>
        {message.blocks?.map((block, i) => (
          <div key={i} className={isUser ? "inline-block text-left" : ""}>
            {block.type === "text" && <TextBlock content={block.content} />}
            {block.type === "stock_cards" && <HoldingsTableBlock data={block.data} onStockClick={onStockClick} />}
            {block.type === "analysis" && <AnalysisBlock data={block.data} />}
            {block.type === "trade_signal" && <TradeSignalBlock data={block.data} onApprove={onApprove} onReject={onReject} />}
            {block.type === "suggested_prompts" && <SuggestedPromptsBlock data={block.data} onSelect={onPromptSelect} />}
            {block.type === "market_overview" && <MarketContextBlock data={block.data} content={block.content} />}
          </div>
        ))}
        {isError && onRetry && (
          <button onClick={onRetry} className="mt-2 flex items-center gap-1.5 text-xs text-signal-danger hover:text-signal-danger/80 transition-colors">
            <RotateCcw className="w-3 h-3" /> Retry
          </button>
        )}
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function AgentChat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [agentStatus, setAgentStatus] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [tradeMode, setTradeMode] = useState(null);
  const [pendingCount, setPendingCount] = useState(0);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, loading, scrollToBottom]);

  const fetchAgentStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/agent/status`);
      setAgentStatus(res.data);
    } catch { /* non-critical */ }
  }, []);

  const fetchMeta = useCallback(async () => {
    try {
      const [statusRes, pendingRes] = await Promise.allSettled([
        axios.get(`${API}/settings/upstox-status`),
        axios.get(`${API}/recommendations/pending`),
      ]);
      if (statusRes.status === "fulfilled") setTradeMode(statusRes.value.data.order_mode);
      if (pendingRes.status === "fulfilled") setPendingCount(pendingRes.value.data.length || 0);
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => {
    const loadSession = async () => {
      try {
        const res = await axios.get(`${API}/agent/session/current`);
        if (res.data.messages?.length > 0) {
          setMessages(res.data.messages);
          setSessionId(res.data.session_id);
        }
      } catch (err) {
        console.warn("No existing session", err);
      } finally {
        setInitialLoading(false);
      }
    };
    loadSession();
    fetchAgentStatus();
    fetchMeta();
    const metaInterval = setInterval(fetchMeta, 30000);
    return () => clearInterval(metaInterval);
  }, [fetchAgentStatus, fetchMeta]);

  const sendMessage = async (text) => {
    if (!text.trim() || loading) return;
    const userMsg = { role: "user", blocks: [{ type: "text", content: text }], timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await axios.post(`${API}/agent/message`, { message: text, session_id: sessionId });
      const agentMsg = { role: "agent", blocks: res.data.blocks, timestamp: new Date().toISOString() };
      setMessages((prev) => [...prev, agentMsg]);
      if (res.data.session_id) setSessionId(res.data.session_id);
      fetchAgentStatus();
      fetchMeta();
    } catch (err) {
      console.error("Agent error:", err);
      setMessages((prev) => [...prev, {
        role: "agent",
        blocks: [{ type: "text", content: `Something went wrong: ${err.response?.data?.detail || err.message}` }],
        timestamp: new Date().toISOString(),
        isError: true,
        _failedInput: text,
      }]);
      toast.error("Agent communication failed");
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleRetry = (failedText) => {
    setMessages((prev) => prev.slice(0, -1));
    sendMessage(failedText);
  };

  const handleStockClick = (symbol) => sendMessage(`Analyze ${symbol}`);
  const handleApprove = (_, symbol) => sendMessage(`Approve ${symbol}`);
  const handleReject = (_, symbol) => sendMessage(`Reject ${symbol}`);

  const handleNewSession = async () => {
    try {
      const res = await axios.post(`${API}/agent/session/new`);
      setSessionId(res.data.session_id);
      setMessages([]);
      fetchAgentStatus();
      toast.success("New session started");
    } catch { toast.error("Failed to start new session"); }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
  };

  const autoResize = (el) => {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  };

  if (initialLoading) {
    return <div className="flex items-center justify-center h-[80vh]"><Loader2 className="w-6 h-6 text-purple-400 animate-spin" /></div>;
  }

  const hasMessages = messages.length > 0;

  return (
    <TooltipProvider>
      <div className="flex h-[calc(100vh-48px)]">
        {/* ---- Left: Chat ---- */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-border-subtle">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center">
                <Bot className="w-4 h-4 text-purple-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="font-heading font-bold text-foreground text-base">
                    {hasMessages ? "Trading Agent" : `${greeting()}, ${USER_NAME}`}
                  </h1>
                  {tradeMode && (
                    <Tooltip>
                      <TooltipTrigger>
                        <Badge variant="outline" className={`text-[9px] uppercase tracking-wider ${tradeMode === "live" ? "text-signal-success border-signal-success/30 bg-signal-success/10" : "text-amber-400 border-amber-400/30 bg-amber-400/10"}`}>
                          {tradeMode === "live" ? <span className="w-1.5 h-1.5 rounded-full bg-signal-success mr-1 inline-block animate-pulse" /> : <FlaskConical className="w-2.5 h-2.5 mr-1 inline" />}
                          {tradeMode}
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="text-xs">{tradeMode === "live" ? "Orders execute on Upstox" : "Paper trading mode"}</p>
                      </TooltipContent>
                    </Tooltip>
                  )}
                </div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                  {agentStatus?.orchestrator?.focus || "AI-powered trading assistant"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {pendingCount > 0 && (
                <Tooltip>
                  <TooltipTrigger>
                    <Badge className="badge-pending text-[10px] cursor-default">
                      {pendingCount} pending
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="text-xs">{pendingCount} trade{pendingCount !== 1 ? "s" : ""} awaiting approval</p>
                  </TooltipContent>
                </Tooltip>
              )}
              <Button variant="ghost" size="sm" onClick={handleNewSession} className="text-muted-foreground hover:text-foreground">
                <RefreshCw className="w-4 h-4 mr-1" /> New
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setSidebarOpen(!sidebarOpen)} className="text-muted-foreground hover:text-foreground">
                {sidebarOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
              </Button>
            </div>
          </div>

          {/* Messages */}
          <ScrollArea className="flex-1">
            <div className="max-w-3xl mx-auto">
              {!hasMessages ? (
                <WelcomeScreen onPromptSelect={sendMessage} tradeMode={tradeMode} />
              ) : (
                <AnimatePresence>
                  {messages.map((msg, i) => (
                    <ChatMessage
                      key={i}
                      message={msg}
                      onStockClick={handleStockClick}
                      onApprove={handleApprove}
                      onReject={handleReject}
                      onPromptSelect={sendMessage}
                      onRetry={msg.isError && msg._failedInput ? () => handleRetry(msg._failedInput) : undefined}
                    />
                  ))}
                </AnimatePresence>
              )}
              {loading && <TypingIndicator />}
              <div ref={messagesEndRef} className="h-4" />
            </div>
          </ScrollArea>

          {/* Input */}
          <div className="border-t border-border-subtle px-4 py-3">
            <div className="max-w-3xl mx-auto">
              <div className="flex items-end gap-3">
                <div className="flex-1 relative">
                  <textarea
                    ref={inputRef}
                    rows={1}
                    value={input}
                    onChange={(e) => { setInput(e.target.value); autoResize(e.target); }}
                    onKeyDown={handleKeyDown}
                    placeholder={`Talk to your agent, ${USER_NAME}...`}
                    disabled={loading}
                    className="w-full bg-surface-primary border border-border-subtle rounded-lg px-4 py-3 pr-10 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-purple-500/50 focus:ring-1 focus:ring-purple-500/20 disabled:opacity-50 transition-colors resize-none overflow-hidden"
                    style={{ minHeight: "46px", maxHeight: "150px" }}
                  />
                </div>
                <Button onClick={() => sendMessage(input)} disabled={!input.trim() || loading} className="bg-purple-600 hover:bg-purple-700 text-white px-4 h-[46px]">
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </Button>
              </div>
              <p className="text-[10px] text-muted-foreground/40 mt-1.5 text-right">
                <kbd className="px-1 py-0.5 rounded bg-surface-secondary/50 font-mono text-[9px]">Enter</kbd> to send
                <span className="mx-1.5">·</span>
                <kbd className="px-1 py-0.5 rounded bg-surface-secondary/50 font-mono text-[9px]">Shift+Enter</kbd> new line
              </p>
            </div>
          </div>
        </div>

        {/* ---- Right: Agent Activity Sidebar ---- */}
        <AnimatePresence>
          {sidebarOpen && (
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 280, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="border-l border-border-subtle bg-surface-primary/50 overflow-hidden flex-shrink-0 hidden lg:block"
            >
              <div className="h-full flex flex-col" style={{ width: 280 }}>
                <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Agent Activity</span>
                  </div>
                  <button onClick={() => setSidebarOpen(false)} className="text-muted-foreground hover:text-foreground p-1 transition-colors">
                    <PanelRightClose className="w-3.5 h-3.5" />
                  </button>
                </div>
                <div className="flex-1 overflow-hidden">
                  <AgentActivityPanel status={agentStatus} />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Floating toggle for desktop when sidebar is closed */}
        {!sidebarOpen && (
          <button
            onClick={() => setSidebarOpen(true)}
            className="hidden lg:flex fixed right-4 top-1/2 -translate-y-1/2 z-10 w-8 h-16 rounded-l-lg bg-surface-primary border border-border-subtle border-r-0 items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
          >
            <PanelRightOpen className="w-4 h-4" />
          </button>
        )}
      </div>
    </TooltipProvider>
  );
}
