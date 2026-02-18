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
  ExternalLink
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Separator } from "../components/ui/separator";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Settings() {
  const [settings, setSettings] = useState({
    upstox_api_key: '',
    upstox_api_secret: '',
    upstox_access_token: '',
    max_trade_value: 100000,
    max_position_size: 100,
    risk_per_trade_percent: 2,
    auto_analysis_enabled: true
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const res = await axios.get(`${API}/settings`);
      setSettings(res.data);
    } catch (error) {
      console.error("Failed to fetch settings:", error);
    } finally {
      setLoading(false);
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

  return (
    <div data-testid="settings-page" className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="font-heading text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1">Configure your trading agent</p>
      </div>

      {/* Upstox API Configuration */}
      <Card className="bg-surface-primary border-border-subtle">
        <CardHeader className="border-b border-border-subtle">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-signal-warning/10 rounded-lg">
              <Key className="w-5 h-5 text-signal-warning" />
            </div>
            <div>
              <CardTitle className="font-heading text-xl">Upstox API Configuration</CardTitle>
              <CardDescription>Connect your Upstox trading account</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6 space-y-6">
          <div className="p-4 bg-signal-warning/10 border border-signal-warning/20 rounded-lg flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-signal-warning flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-signal-warning">Important</p>
              <p className="text-sm text-muted-foreground mt-1">
                Get your API credentials from{" "}
                <a 
                  href="https://account.upstox.com/developer/apps" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-signal-warning underline inline-flex items-center gap-1"
                >
                  Upstox Developer Portal
                  <ExternalLink className="w-3 h-3" />
                </a>
              </p>
            </div>
          </div>

          <div className="grid gap-6">
            <div className="space-y-2">
              <Label>API Key</Label>
              <Input
                type="password"
                value={settings.upstox_api_key || ''}
                onChange={(e) => handleChange('upstox_api_key', e.target.value)}
                placeholder="Enter your Upstox API Key"
                className="bg-surface-secondary border-border-subtle font-mono"
                data-testid="api-key-input"
              />
            </div>
            
            <div className="space-y-2">
              <Label>API Secret</Label>
              <Input
                type="password"
                value={settings.upstox_api_secret || ''}
                onChange={(e) => handleChange('upstox_api_secret', e.target.value)}
                placeholder="Enter your Upstox API Secret"
                className="bg-surface-secondary border-border-subtle font-mono"
                data-testid="api-secret-input"
              />
            </div>
            
            <div className="space-y-2">
              <Label>Access Token</Label>
              <Input
                type="password"
                value={settings.upstox_access_token || ''}
                onChange={(e) => handleChange('upstox_access_token', e.target.value)}
                placeholder="Enter your Access Token (valid for 24 hours)"
                className="bg-surface-secondary border-border-subtle font-mono"
                data-testid="access-token-input"
              />
              <p className="text-xs text-muted-foreground">
                Access tokens expire daily. You'll need to refresh this regularly.
              </p>
            </div>
          </div>
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
              <Label>Max Trade Value (₹)</Label>
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
