import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { 
  Settings as SettingsIcon, 
  Key, 
  Shield, 
  Bell,
  Save,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
  Wifi,
  WifiOff,
  Info,
  Brain,
  Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Separator } from "../components/ui/separator";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"}/api`;

export default function Settings() {
  const [settings, setSettings] = useState({
    max_trade_value: 100000,
    max_position_size: 100,
    risk_per_trade_percent: 2,
    auto_analysis_enabled: true,
    min_confidence_to_trade: 70,
    min_confidence_for_live: 80,
    max_correlated_positions: 3,
    earnings_blackout_days: 3,
    daily_loss_limit_pct: 2,
    pairs_min_correlation: 0.75,
    pairs_zscore_entry: 2.0,
    pairs_zscore_exit: 0.5,
    pairs_max_holding_days: 10,
  });
  const [upstoxStatus, setUpstoxStatus] = useState(null);
  const [modelInfo, setModelInfo] = useState({ available: [], preferred: null, active: "" });
  const [modelSaving, setModelSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [checkingUpstox, setCheckingUpstox] = useState(false);

  useEffect(() => {
    Promise.all([fetchSettings(), fetchUpstoxStatus(), fetchModels()]).finally(() => setLoading(false));
  }, []);

  const fetchSettings = async () => {
    try {
      const res = await axios.get(`${API}/settings`);
      setSettings(prev => ({ ...prev, ...res.data }));
    } catch (error) {
      console.error("Failed to fetch settings:", error);
    }
  };

  const fetchUpstoxStatus = async () => {
    setCheckingUpstox(true);
    try {
      const res = await axios.get(`${API}/settings/upstox-status`);
      setUpstoxStatus(res.data);
    } catch (error) {
      console.error("Failed to fetch Upstox status:", error);
      setUpstoxStatus({ error: true });
    } finally {
      setCheckingUpstox(false);
    }
  };

  const fetchModels = async () => {
    try {
      const res = await axios.get(`${API}/settings/models`);
      setModelInfo(res.data);
    } catch (error) {
      console.warn("Failed to fetch models:", error);
    }
  };

  const handleModelChange = async (model) => {
    setModelSaving(true);
    try {
      const res = await axios.post(`${API}/settings/model`, { model: model || null });
      toast.success(`Model set to ${model || "auto"}`);
      setModelInfo((prev) => ({ ...prev, preferred: model || null, active: res.data.active }));
    } catch (error) {
      toast.error("Failed to set model");
    } finally {
      setModelSaving(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/settings`, settings);
      toast.success("Settings saved successfully");
    } catch (error) {
      console.error("Failed to save settings:", error);
      toast.error("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]">
        <div className="spinner" />
      </div>
    );
  }

  const modeColor = upstoxStatus?.order_mode === "sandbox"
    ? "text-signal-warning"
    : "text-signal-success";
  const modeBg = upstoxStatus?.order_mode === "sandbox"
    ? "bg-signal-warning/10 border-signal-warning/20"
    : "bg-signal-success/10 border-signal-success/20";

  return (
    <div data-testid="settings-page" className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="font-heading text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1">Configure your trading agent</p>
      </div>

      {/* Upstox Connection Status */}
      <Card className="bg-surface-primary border-border-subtle">
        <CardHeader className="border-b border-border-subtle">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-signal-warning/10 rounded-lg">
                <Key className="w-5 h-5 text-signal-warning" />
              </div>
              <div>
                <CardTitle className="font-heading text-xl">Upstox Connection</CardTitle>
                <CardDescription>Token status and connectivity (read-only)</CardDescription>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchUpstoxStatus}
              disabled={checkingUpstox}
              className="border-border-subtle"
            >
              <RefreshCw className={`w-4 h-4 mr-1.5 ${checkingUpstox ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-6 space-y-5">
          {upstoxStatus?.error ? (
            <div className="p-4 bg-signal-danger/10 border border-signal-danger/20 rounded-lg flex items-start gap-3">
              <WifiOff className="w-5 h-5 text-signal-danger flex-shrink-0 mt-0.5" />
              <p className="text-sm text-signal-danger">Could not fetch Upstox status. Is the backend running?</p>
            </div>
          ) : upstoxStatus ? (
            <>
              {/* Order Mode badge */}
              <div className={`p-4 border rounded-lg flex items-center gap-3 ${modeBg}`}>
                <Info className={`w-5 h-5 flex-shrink-0 ${modeColor}`} />
                <div>
                  <p className={`text-sm font-semibold ${modeColor} uppercase tracking-wide`}>
                    {upstoxStatus.order_mode} mode
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Orders are placed via the {upstoxStatus.order_mode} API. Market data always uses a live token.
                  </p>
                </div>
              </div>

              {/* Token status grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <StatusRow
                  label="Market Data Token"
                  masked={upstoxStatus.market_data_token}
                  ok={upstoxStatus.market_data_ok}
                />
                <StatusRow
                  label="Order Token"
                  masked={upstoxStatus.order_token}
                  ok={upstoxStatus.orders_ok}
                />
              </div>

              {/* Connectivity */}
              <div className="space-y-2">
                <ConnectivityRow label="Market Data API" status={upstoxStatus.market_data_connectivity} />
                <ConnectivityRow label="Order API" status={upstoxStatus.order_connectivity} />
              </div>

              <Separator />

              {/* How to update tokens */}
              <div className="p-4 bg-surface-secondary rounded-lg space-y-2">
                <p className="text-sm font-medium text-foreground">How to update tokens</p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Tokens are loaded from the <code className="px-1 py-0.5 bg-surface-primary rounded text-xs font-mono">backend/.env</code> file.
                  Edit <code className="px-1 py-0.5 bg-surface-primary rounded text-xs font-mono">UPSTOX_ACCESS_TOKEN</code>{" "}
                  (live) or <code className="px-1 py-0.5 bg-surface-primary rounded text-xs font-mono">UPSTOX_SANDBOX_ACCESS_TOKEN</code>{" "}
                  (sandbox), then restart the backend server.
                </p>
                <a
                  href="https://account.upstox.com/developer/apps"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-signal-warning hover:underline mt-1"
                >
                  Open Upstox Developer Portal <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>

      {/* Risk Management */}
      <Card className="bg-surface-primary border-border-subtle">
        <CardHeader className="border-b border-border-subtle">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-signal-danger/10 rounded-lg">
              <Shield className="w-5 h-5 text-signal-danger" />
            </div>
            <div>
              <CardTitle className="font-heading text-xl">Risk Management</CardTitle>
              <CardDescription>Set limits to protect your capital</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-2">
              <Label>Max Trade Value (&#x20B9;)</Label>
              <Input
                type="number"
                value={settings.max_trade_value}
                onChange={(e) => handleChange('max_trade_value', parseFloat(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
                data-testid="max-trade-value-input"
              />
              <p className="text-xs text-muted-foreground">Maximum value per single trade</p>
            </div>
            
            <div className="space-y-2">
              <Label>Max Position Size</Label>
              <Input
                type="number"
                value={settings.max_position_size}
                onChange={(e) => handleChange('max_position_size', parseInt(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
                data-testid="max-position-input"
              />
              <p className="text-xs text-muted-foreground">Maximum quantity per stock</p>
            </div>
            
            <div className="space-y-2">
              <Label>Risk Per Trade (%)</Label>
              <Input
                type="number"
                step="0.5"
                value={settings.risk_per_trade_percent}
                onChange={(e) => handleChange('risk_per_trade_percent', parseFloat(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
                data-testid="risk-percent-input"
              />
              <p className="text-xs text-muted-foreground">Maximum portfolio risk per trade</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* AI Settings */}
      <Card className="bg-surface-primary border-border-subtle">
        <CardHeader className="border-b border-border-subtle">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-ai-glow/10 rounded-lg">
              <Brain className="w-5 h-5 text-ai-glow" />
            </div>
            <div>
              <CardTitle className="font-heading text-xl">AI Agent Settings</CardTitle>
              <CardDescription>Configure AI model and analysis behavior</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6 space-y-6">
          {/* Model Selector */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Gemini Model</Label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                onClick={() => handleModelChange(null)}
                disabled={modelSaving}
                className={`flex items-center gap-3 p-3 rounded-lg border transition-colors text-left ${
                  !modelInfo.preferred
                    ? "border-purple-500/50 bg-purple-500/10"
                    : "border-border-subtle bg-surface-secondary hover:border-border-active"
                }`}
              >
                <Zap className={`w-4 h-4 flex-shrink-0 ${!modelInfo.preferred ? "text-purple-400" : "text-muted-foreground"}`} />
                <div>
                  <p className={`text-sm font-medium ${!modelInfo.preferred ? "text-purple-400" : "text-foreground"}`}>
                    Auto (Smart Fallback)
                  </p>
                  <p className="text-[10px] text-muted-foreground">Uses priority list with rate-limit fallback</p>
                </div>
              </button>
              {modelInfo.available.map((model) => (
                <button
                  key={model}
                  onClick={() => handleModelChange(model)}
                  disabled={modelSaving}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-colors text-left ${
                    modelInfo.preferred === model
                      ? "border-purple-500/50 bg-purple-500/10"
                      : "border-border-subtle bg-surface-secondary hover:border-border-active"
                  }`}
                >
                  <Brain className={`w-4 h-4 flex-shrink-0 ${modelInfo.preferred === model ? "text-purple-400" : "text-muted-foreground"}`} />
                  <div>
                    <p className={`text-sm font-mono font-medium ${modelInfo.preferred === model ? "text-purple-400" : "text-foreground"}`}>
                      {model}
                    </p>
                    {modelInfo.active === model && (
                      <p className="text-[10px] text-signal-success">currently active</p>
                    )}
                  </div>
                </button>
              ))}
            </div>
            {modelSaving && (
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <div className="spinner w-3 h-3" /> Switching model...
              </p>
            )}
          </div>

          <Separator />

          {/* Auto Analysis Toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Auto Analysis</p>
              <p className="text-sm text-muted-foreground mt-1">
                Automatically analyze stocks when market opens
              </p>
            </div>
            <Switch
              checked={settings.auto_analysis_enabled}
              onCheckedChange={(checked) => handleChange('auto_analysis_enabled', checked)}
              data-testid="auto-analysis-switch"
            />
          </div>
        </CardContent>
      </Card>

      {/* Confidence & Validation */}
      <Card className="bg-surface-primary border-border-subtle">
        <CardHeader className="border-b border-border-subtle">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/10 rounded-lg">
              <Shield className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <CardTitle className="font-heading text-xl">Smart Trading Thresholds</CardTitle>
              <CardDescription>Confidence gating, correlation limits, and risk controls</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-2">
              <Label>Min Confidence to Trade</Label>
              <Input
                type="number"
                value={settings.min_confidence_to_trade}
                onChange={(e) => handleChange('min_confidence_to_trade', parseInt(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
              />
              <p className="text-xs text-muted-foreground">Minimum AI confidence score (0-100) to generate any signal</p>
            </div>
            <div className="space-y-2">
              <Label>Min Confidence for Live</Label>
              <Input
                type="number"
                value={settings.min_confidence_for_live}
                onChange={(e) => handleChange('min_confidence_for_live', parseInt(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
              />
              <p className="text-xs text-muted-foreground">Higher bar for live trade signals</p>
            </div>
            <div className="space-y-2">
              <Label>Max Correlated Positions</Label>
              <Input
                type="number"
                value={settings.max_correlated_positions}
                onChange={(e) => handleChange('max_correlated_positions', parseInt(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
              />
              <p className="text-xs text-muted-foreground">Max stocks with &gt;0.7 correlation to hold simultaneously</p>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label>Earnings Blackout (days)</Label>
              <Input
                type="number"
                value={settings.earnings_blackout_days}
                onChange={(e) => handleChange('earnings_blackout_days', parseInt(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
              />
              <p className="text-xs text-muted-foreground">Warn if stock reports earnings within N days</p>
            </div>
            <div className="space-y-2">
              <Label>Daily Loss Limit (%)</Label>
              <Input
                type="number"
                step="0.5"
                value={settings.daily_loss_limit_pct}
                onChange={(e) => handleChange('daily_loss_limit_pct', parseFloat(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
              />
              <p className="text-xs text-muted-foreground">Pause new entries if daily loss exceeds this % of capital</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Pairs Trading */}
      <Card className="bg-surface-primary border-border-subtle">
        <CardHeader className="border-b border-border-subtle">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/10 rounded-lg">
              <SettingsIcon className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <CardTitle className="font-heading text-xl">Pairs Trading</CardTitle>
              <CardDescription>Configure correlation-based pair trade parameters</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="space-y-2">
              <Label>Min Correlation</Label>
              <Input
                type="number"
                step="0.05"
                value={settings.pairs_min_correlation}
                onChange={(e) => handleChange('pairs_min_correlation', parseFloat(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
              />
              <p className="text-xs text-muted-foreground">Min correlation to form a pair (0.5-1.0)</p>
            </div>
            <div className="space-y-2">
              <Label>Z-Score Entry</Label>
              <Input
                type="number"
                step="0.1"
                value={settings.pairs_zscore_entry}
                onChange={(e) => handleChange('pairs_zscore_entry', parseFloat(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
              />
              <p className="text-xs text-muted-foreground">Z-score threshold to enter a pair trade</p>
            </div>
            <div className="space-y-2">
              <Label>Z-Score Exit</Label>
              <Input
                type="number"
                step="0.1"
                value={settings.pairs_zscore_exit}
                onChange={(e) => handleChange('pairs_zscore_exit', parseFloat(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
              />
              <p className="text-xs text-muted-foreground">Z-score to close pair (mean reversion target)</p>
            </div>
            <div className="space-y-2">
              <Label>Max Holding Days</Label>
              <Input
                type="number"
                value={settings.pairs_max_holding_days}
                onChange={(e) => handleChange('pairs_max_holding_days', parseInt(e.target.value))}
                className="bg-surface-secondary border-border-subtle font-mono"
              />
              <p className="text-xs text-muted-foreground">Close pair if no convergence after N days</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button 
          onClick={handleSave} 
          disabled={saving}
          className="bg-signal-success text-black hover:bg-signal-success/80 px-8"
          data-testid="save-settings-btn"
        >
          {saving ? (
            <div className="spinner w-4 h-4 mr-2" />
          ) : (
            <Save className="w-4 h-4 mr-2" />
          )}
          Save Settings
        </Button>
      </div>
    </div>
  );
}

function StatusRow({ label, masked, ok }) {
  return (
    <div className="flex items-center justify-between p-3 bg-surface-secondary rounded-lg">
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-mono mt-0.5">
          {masked || <span className="text-signal-danger italic">not set</span>}
        </p>
      </div>
      {ok ? (
        <CheckCircle2 className="w-5 h-5 text-signal-success" />
      ) : (
        <AlertTriangle className="w-5 h-5 text-signal-danger" />
      )}
    </div>
  );
}

function ConnectivityRow({ label, status }) {
  const isOk = status === "ok";
  const isNoToken = status === "no token";
  return (
    <div className="flex items-center gap-2 text-sm">
      {isOk ? (
        <Wifi className="w-4 h-4 text-signal-success flex-shrink-0" />
      ) : (
        <WifiOff className={`w-4 h-4 flex-shrink-0 ${isNoToken ? "text-muted-foreground" : "text-signal-danger"}`} />
      )}
      <span className={`font-medium ${isOk ? "text-signal-success" : isNoToken ? "text-muted-foreground" : "text-signal-danger"}`}>
        {label}:
      </span>
      <span className={`text-xs ${isOk ? "text-signal-success" : isNoToken ? "text-muted-foreground" : "text-signal-danger"}`}>
        {isOk ? "connected" : status || "unknown"}
      </span>
    </div>
  );
}
