import { BrowserRouter, Routes, Route, NavLink, useLocation, Navigate } from "react-router-dom";
import { useState, useEffect } from "react";
import axios from "axios";
import { Toaster } from "./components/ui/sonner";
import "@/App.css";
import AgentChat from "./pages/AgentChat";
import TradeQueue from "./pages/TradeQueue";
import Portfolio from "./pages/Portfolio";
import Settings from "./pages/Settings";
import AIResearch from "./pages/AIResearch";
import Sandbox from "./pages/Sandbox";
import { 
  Brain, 
  ListChecks, 
  Wallet, 
  Settings as SettingsIcon,
  TrendingUp,
  MessageSquare,
  FlaskConical,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const API = `${BACKEND_URL}/api`;

const Sidebar = () => {
  const location = useLocation();
  const [marketOpen, setMarketOpen] = useState(null);
  const [currentTime, setCurrentTime] = useState(new Date());
  
  useEffect(() => {
    // Check market status on mount and setup polling
    const checkMarketStatus = async () => {
      try {
        const response = await axios.get(`${API}/market/status`);
        setMarketOpen(response.data.is_open);
      } catch (error) {
        console.warn("Failed to fetch market status", error);
      }
    };
    
    checkMarketStatus();
    
    // Update every minute (market hours can be expensive to check frequently)
    const interval = setInterval(checkMarketStatus, 60000);
    
    // Update time display
    const timeInterval = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);
    
    return () => {
      clearInterval(interval);
      clearInterval(timeInterval);
    };
  }, []);
  
  const navItems = [
    { path: "/", icon: MessageSquare, label: "Agent" },
    { path: "/research", icon: Brain, label: "Research" },
    { path: "/trades", icon: ListChecks, label: "Trades" },
    { path: "/portfolio", icon: Wallet, label: "Portfolio" },
    { path: "/sandbox", icon: FlaskConical, label: "Sandbox" },
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
            <h1 className="font-heading font-bold text-lg text-foreground">Desi Algo Trade</h1>
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
          <div 
            className={`w-2 h-2 rounded-full animate-pulse-glow ${
              marketOpen === true 
                ? "bg-signal-success" 
                : marketOpen === false 
                ? "bg-signal-danger" 
                : "bg-signal-warning"
            }`}
            title={marketOpen === true ? "Market Open" : "Market Closed"}
          />
          <div className="hidden lg:block">
            <p className="text-xs text-muted-foreground">
              {marketOpen === true 
                ? "🟢 Market Open" 
                : marketOpen === false 
                ? "🔴 Market Closed" 
                : "⏳ Loading..."}
            </p>
            {/* <p className="text-[10px] text-muted-foreground">
              {currentTime.toLocaleTimeString('en-IN')}
            </p> */}
          </div>
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
            <Route path="/" element={<AgentChat />} />
            <Route path="/research" element={<AIResearch />} />
            <Route path="/trades" element={<TradeQueue />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/sandbox" element={<Sandbox />} />
            <Route path="/settings" element={<Settings />} />
            {/* Redirects for old routes */}
            <Route path="/dashboard" element={<Navigate to="/portfolio" replace />} />
            <Route path="/stocks" element={<Navigate to="/research" replace />} />
            <Route path="/queue" element={<Navigate to="/trades" replace />} />
            <Route path="/history" element={<Navigate to="/trades" replace />} />
          </Routes>
        </main>
        <Toaster position="bottom-right" richColors />
      </BrowserRouter>
    </div>
  );
}

export default App;
