import { BrowserRouter, Routes, Route, NavLink, useLocation } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import "@/App.css";
import Dashboard from "./pages/Dashboard";
import StockUniverse from "./pages/StockUniverse";
import TradeQueue from "./pages/TradeQueue";
import Portfolio from "./pages/Portfolio";
import TradeHistory from "./pages/TradeHistory";
import Settings from "./pages/Settings";
import AIResearch from "./pages/AIResearch";
import { 
  LayoutDashboard, 
  Layers, 
  Brain, 
  ListChecks, 
  Wallet, 
  History, 
  Settings as SettingsIcon,
  TrendingUp
} from "lucide-react";

const Sidebar = () => {
  const location = useLocation();
  
  const navItems = [
    { path: "/", icon: LayoutDashboard, label: "Dashboard" },
    { path: "/stocks", icon: Layers, label: "Stock Universe" },
    { path: "/research", icon: Brain, label: "AI Research" },
    { path: "/queue", icon: ListChecks, label: "Trade Queue" },
    { path: "/portfolio", icon: Wallet, label: "Portfolio" },
    { path: "/history", icon: History, label: "Trade History" },
    { path: "/settings", icon: SettingsIcon, label: "Settings" },
  ];

  return (
    <aside className="sidebar" data-testid="sidebar">
      <div className="p-4 border-b border-border-subtle">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-signal-success/20 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-signal-success" />
          </div>
          <div className="hidden lg:block">
            <h1 className="font-heading font-bold text-lg text-foreground">AlgoTrade</h1>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">AI Trading Agent</p>
          </div>
        </div>
      </div>
      
      <nav className="py-4" data-testid="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => 
              `sidebar-item ${isActive || (item.path === "/" && location.pathname === "/") ? "active" : ""}`
            }
            data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
          >
            <item.icon className="w-5 h-5 flex-shrink-0" />
            <span className="hidden lg:inline">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      
      <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-border-subtle">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-signal-success animate-pulse-glow" />
          <span className="text-xs text-muted-foreground hidden lg:inline">Market Open</span>
        </div>
      </div>
    </aside>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/stocks" element={<StockUniverse />} />
            <Route path="/research" element={<AIResearch />} />
            <Route path="/queue" element={<TradeQueue />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/history" element={<TradeHistory />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
        <Toaster position="bottom-right" richColors />
      </BrowserRouter>
    </div>
  );
}

export default App;
