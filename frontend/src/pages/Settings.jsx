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
  Info
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
    auto_analysis_enabled: true
  });
  const [upstoxStatus, setUpstoxStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [checkingUpstox, setCheckingUpstox] = useState(false);

  useEffect(() => {
    Promise.all([fetchSettings(), fetchUpstoxStatus()]).finally(() => setLoading(false));
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
              <div className="flex items-center gap-2 text-sm">
                {upstoxStatus.market_data_connectivity === "ok" ? (
                  <>
                    <Wifi className="w-4 h-4 text-signal-success" />
                    <span className="text-signal-success font-medium">API connectivity OK</span>
                  </>
                ) : (
                  <>
                    <WifiOff className="w-4 h-4 text-signal-danger" />
                    <span className="text-signal-danger font-medium">
                      API connectivity: {upstoxStatus.market_data_connectivity}
                    </span>
                  </>
                )}
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
              <Bell className="w-5 h-5 text-ai-glow" />
            </div>
            <div>
              <CardTitle className="font-heading text-xl">AI Agent Settings</CardTitle>
              <CardDescription>Configure AI analysis behavior</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6">
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
