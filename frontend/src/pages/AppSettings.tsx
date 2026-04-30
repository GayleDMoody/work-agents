import { useState, useEffect } from 'react';
import { Settings, GitBranch, Shield, Bell, DollarSign, Terminal, RotateCcw, Save, Bot, Loader2, CheckCircle } from 'lucide-react';
import { api } from '../api/client';
import { applyTheme } from '../hooks/useTheme';

// Types for all settings
interface AppConfig {
  // General
  theme: 'dark' | 'light' | 'system';
  defaultModel: string;
  verbose: boolean;

  // Pipeline
  processType: 'sequential' | 'hierarchical';
  maxFeedbackLoops: number;
  maxRetries: number;
  taskTimeoutSeconds: number;
  maxConcurrentPipelines: number;

  // Cost
  costLimitPerRun: number;
  costLimitMonthly: number;
  warnAtPercent: number;

  // Approval gates
  requireArchitectureApproval: boolean;
  requirePreMergeApproval: boolean;
  requireDeploymentApproval: boolean;
  autoApproveSmallTickets: boolean;

  // Notifications
  notifyOnComplete: boolean;
  notifyOnFailure: boolean;
  notifyOnApprovalNeeded: boolean;
  notificationChannel: 'in-app' | 'slack' | 'email';

  // Per-agent model overrides
  agentModels: Record<string, string>;
}

const DEFAULT_CONFIG: AppConfig = {
  theme: 'dark',
  defaultModel: 'claude-haiku-4-5-20251001',
  verbose: false,
  processType: 'sequential',
  maxFeedbackLoops: 3,
  maxRetries: 2,
  taskTimeoutSeconds: 300,
  maxConcurrentPipelines: 5,
  costLimitPerRun: 5.0,
  costLimitMonthly: 200.0,
  warnAtPercent: 80,
  requireArchitectureApproval: true,
  requirePreMergeApproval: true,
  requireDeploymentApproval: false,
  autoApproveSmallTickets: true,
  notifyOnComplete: true,
  notifyOnFailure: true,
  notifyOnApprovalNeeded: true,
  notificationChannel: 'in-app',
  agentModels: {
    product: '', pm: '', architect: '', frontend: '',
    backend: '', qa: '', devops: '', code_review: '',
  },
};

/**
 * Available Anthropic models. Tier and approximate $/Mtok input/output prices
 * are shown in the picker so users can pick the right tradeoff per agent.
 * Pricing as of 2026-04. Prices may change — these are display hints only.
 */
type ModelTier = 'haiku' | 'sonnet' | 'opus';
interface ModelOption {
  value: string;
  label: string;
  tier: ModelTier;
  /** Rough $/Mtok input  */ priceIn?: number;
  /** Rough $/Mtok output */ priceOut?: number;
  /** True for the most-recommended pick at each tier */ recommended?: boolean;
}

const MODELS: ModelOption[] = [
  { value: '',                              label: 'Use default',                tier: 'haiku' },
  // Haiku — fastest + cheapest, great for high-volume agent calls
  { value: 'claude-haiku-4-5-20251001',     label: 'Claude Haiku 4.5',           tier: 'haiku',  priceIn: 1.00,  priceOut: 5.00,  recommended: true },
  // Sonnet — balanced reasoning + cost
  { value: 'claude-sonnet-4-5-20250929',    label: 'Claude Sonnet 4.5',          tier: 'sonnet', priceIn: 3.00,  priceOut: 15.00, recommended: true },
  { value: 'claude-sonnet-4-6',             label: 'Claude Sonnet 4.6',          tier: 'sonnet', priceIn: 3.00,  priceOut: 15.00 },
  // Opus — strongest reasoning, most expensive
  { value: 'claude-opus-4-1-20250805',      label: 'Claude Opus 4.1',            tier: 'opus',   priceIn: 15.00, priceOut: 75.00 },
  { value: 'claude-opus-4-5-20251101',      label: 'Claude Opus 4.5',            tier: 'opus',   priceIn: 15.00, priceOut: 75.00 },
  { value: 'claude-opus-4-6',               label: 'Claude Opus 4.6',            tier: 'opus',   priceIn: 15.00, priceOut: 75.00 },
  { value: 'claude-opus-4-7',               label: 'Claude Opus 4.7',            tier: 'opus',   priceIn: 15.00, priceOut: 75.00, recommended: true },
];

function modelLabel(value: string): string {
  if (!value) return 'Use default';
  const m = MODELS.find(x => x.value === value);
  return m ? m.label : value;
}

const AGENTS = [
  { id: 'product', name: 'Product Analyst' },
  { id: 'pm', name: 'Project Manager' },
  { id: 'architect', name: 'Architect' },
  { id: 'frontend', name: 'Frontend Dev' },
  { id: 'backend', name: 'Backend Dev' },
  { id: 'qa', name: 'QA Engineer' },
  { id: 'devops', name: 'DevOps' },
  { id: 'code_review', name: 'Code Reviewer' },
];

/**
 * Sensible per-role model defaults if the user clicks "Apply suggested".
 *  - Reasoning-heavy roles (architect, code_review) → Opus
 *  - Planning / synthesis roles (product, pm) → Sonnet
 *  - High-volume execution roles (frontend, backend, qa, devops) → Haiku for cost
 */
const SUGGESTED_AGENT_MODELS: Record<string, string> = {
  product:     'claude-sonnet-4-5-20250929',
  pm:          'claude-sonnet-4-5-20250929',
  architect:   'claude-opus-4-1-20250805',
  frontend:    'claude-haiku-4-5-20251001',
  backend:     'claude-haiku-4-5-20251001',
  qa:          'claude-haiku-4-5-20251001',
  devops:      'claude-haiku-4-5-20251001',
  code_review: 'claude-opus-4-1-20250805',
};

const SUGGESTED_RATIONALE: Record<string, string> = {
  product:     'Synthesises ambiguous requirements; benefits from stronger reasoning.',
  pm:          'Plans dependencies and parallelism; benefits from stronger reasoning.',
  architect:   'Design tradeoffs + ADRs benefit from the strongest reasoning model.',
  frontend:    'Code generation against a locked architect contract — Haiku is fast + cheap.',
  backend:     'Code generation against a locked architect contract — Haiku is fast + cheap.',
  qa:          'Test generation against acceptance criteria — Haiku handles this well.',
  devops:      'CI/CD config generation — Haiku is more than enough.',
  code_review: 'Final quality gate; benefits from the strongest reasoning model.',
};

type Section = 'general' | 'pipeline' | 'agents' | 'cost' | 'approvals' | 'notifications' | 'advanced';

const SECTIONS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: 'General', icon: <Settings size={16} /> },
  { id: 'pipeline', label: 'Pipeline', icon: <GitBranch size={16} /> },
  { id: 'agents', label: 'Agent Models', icon: <Bot size={16} /> },
  { id: 'cost', label: 'Cost Limits', icon: <DollarSign size={16} /> },
  { id: 'approvals', label: 'Approval Gates', icon: <Shield size={16} /> },
  { id: 'notifications', label: 'Notifications', icon: <Bell size={16} /> },
  { id: 'advanced', label: 'Advanced', icon: <Terminal size={16} /> },
];

export default function AppSettings() {
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  const [section, setSection] = useState<Section>('general');
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);

  // Load config from API on mount
  useEffect(() => {
    (async () => {
      try {
        const remote = await api.getAppConfig() as unknown as AppConfig;
        setConfig({ ...DEFAULT_CONFIG, ...remote, agentModels: { ...DEFAULT_CONFIG.agentModels, ...(remote.agentModels || {}) } });
      } catch {
        // API not available — fall back to localStorage
        const local = localStorage.getItem('work-agents-config');
        if (local) {
          try { setConfig({ ...DEFAULT_CONFIG, ...JSON.parse(local) }); } catch { /* ignore */ }
        }
      }
      setLoading(false);
    })();
  }, []);

  const update = <K extends keyof AppConfig>(key: K, value: AppConfig[K]) => {
    setConfig(prev => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const updateAgentModel = (agentId: string, model: string) => {
    setConfig(prev => ({ ...prev, agentModels: { ...prev.agentModels, [agentId]: model } }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      await api.saveAppConfig(config as unknown as Record<string, unknown>);
      // Also persist to localStorage as backup
      localStorage.setItem('work-agents-config', JSON.stringify(config));
      setSaved(true);
      setDirty(false);
      applyTheme(config.theme);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      // If API is down, still save to localStorage
      localStorage.setItem('work-agents-config', JSON.stringify(config));
      applyTheme(config.theme);
      setError('Saved locally (backend not running)');
      setSaved(true);
      setDirty(false);
      setTimeout(() => { setSaved(false); setError(''); }, 3000);
    }
    setSaving(false);
  };

  const handleReset = async () => {
    try {
      await api.resetAppConfig();
    } catch { /* ok */ }
    setConfig({ ...DEFAULT_CONFIG });
    localStorage.removeItem('work-agents-config');
    setDirty(true);
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '50vh', color: 'var(--text-muted)' }}>
        <Loader2 size={24} className="spin" style={{ marginRight: 8 }} /> Loading settings...
      </div>
    );
  }

  return (
    <div className="app-settings">
      {/* Sidebar nav */}
      <div className="settings-nav">
        <div className="settings-nav-header">
          <Settings size={16} /> App Settings
        </div>
        {SECTIONS.map(s => (
          <button
            key={s.id}
            className={`settings-nav-item ${section === s.id ? 'active' : ''}`}
            onClick={() => setSection(s.id)}
          >
            {s.icon} {s.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="settings-content">
        <div className="settings-content-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h2>{SECTIONS.find(s => s.id === section)?.label}</h2>
            {dirty && <span style={{ fontSize: 11, color: 'var(--warning)', fontWeight: 600 }}>Unsaved changes</span>}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {error && <span style={{ fontSize: 11, color: 'var(--warning)' }}>{error}</span>}
            {saved && !error && <span style={{ fontSize: 11, color: 'var(--success)', display: 'flex', alignItems: 'center', gap: 4 }}><CheckCircle size={12} /> Saved</span>}
            <button className="btn btn-outline" onClick={handleReset}><RotateCcw size={14} /> Reset</button>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? <><Loader2 size={14} className="spin" /> Saving...</> : <><Save size={14} /> Save</>}
            </button>
          </div>
        </div>

        <div className="settings-body">
          {section === 'general' && (
            <>
              <SettingRow label="Theme" description="Application color scheme — applies immediately">
                <select className="settings-select" value={config.theme} onChange={e => {
                  const t = e.target.value as AppConfig['theme'];
                  update('theme', t);
                  applyTheme(t);
                }}>
                  <option value="dark">Dark</option>
                  <option value="light">Light</option>
                  <option value="system">System</option>
                </select>
              </SettingRow>
              <SettingRow label="Default AI Model" description="Model used by agents unless overridden per-agent. Haiku is fast + cheap; Sonnet is balanced; Opus is strongest reasoning.">
                <select className="settings-select" value={config.defaultModel} onChange={e => update('defaultModel', e.target.value)}>
                  <optgroup label="Haiku — fast + cheap">
                    {MODELS.filter(m => m.value && m.tier === 'haiku').map(m => (
                      <option key={m.value} value={m.value}>{m.label}{m.recommended ? ' ★' : ''} {m.priceIn ? `· $${m.priceIn}/$${m.priceOut} per Mtok` : ''}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Sonnet — balanced">
                    {MODELS.filter(m => m.value && m.tier === 'sonnet').map(m => (
                      <option key={m.value} value={m.value}>{m.label}{m.recommended ? ' ★' : ''} {m.priceIn ? `· $${m.priceIn}/$${m.priceOut} per Mtok` : ''}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Opus — strongest reasoning">
                    {MODELS.filter(m => m.value && m.tier === 'opus').map(m => (
                      <option key={m.value} value={m.value}>{m.label}{m.recommended ? ' ★' : ''} {m.priceIn ? `· $${m.priceIn}/$${m.priceOut} per Mtok` : ''}</option>
                    ))}
                  </optgroup>
                </select>
              </SettingRow>
              <SettingRow label="Verbose Logging" description="Show detailed agent reasoning in pipeline output">
                <Toggle checked={config.verbose} onChange={v => update('verbose', v)} />
              </SettingRow>
            </>
          )}

          {section === 'pipeline' && (
            <>
              <SettingRow label="Process Type" description="How agents are coordinated during pipeline execution">
                <select className="settings-select" value={config.processType} onChange={e => update('processType', e.target.value as AppConfig['processType'])}>
                  <option value="sequential">Sequential (tasks in order, auto context passing)</option>
                  <option value="hierarchical">Hierarchical (PM agent delegates dynamically)</option>
                </select>
              </SettingRow>
              <SettingRow label="Max Feedback Loops" description="How many QA → Dev retry cycles before escalating to human">
                <NumberInput value={config.maxFeedbackLoops} min={0} max={10} onChange={v => update('maxFeedbackLoops', v)} />
              </SettingRow>
              <SettingRow label="Max Retries Per Agent" description="Retry attempts when an agent's output fails validation">
                <NumberInput value={config.maxRetries} min={0} max={5} onChange={v => update('maxRetries', v)} />
              </SettingRow>
              <SettingRow label="Task Timeout (seconds)" description="Maximum time an individual task can run before being killed">
                <NumberInput value={config.taskTimeoutSeconds} min={30} max={1800} step={30} onChange={v => update('taskTimeoutSeconds', v)} />
              </SettingRow>
              <SettingRow label="Max Concurrent Pipelines" description="Number of ticket pipelines that can run simultaneously">
                <NumberInput value={config.maxConcurrentPipelines} min={1} max={20} onChange={v => update('maxConcurrentPipelines', v)} />
              </SettingRow>
            </>
          )}

          {section === 'agents' && (
            <>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
                Choose which Claude model each agent uses. Use the default ({modelLabel(config.defaultModel)}) for agents
                where the default suits the task, or override with a stronger / cheaper model per role.
              </p>
              <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="settings-secondary-btn"
                  onClick={() => setConfig(prev => ({ ...prev, agentModels: SUGGESTED_AGENT_MODELS }))}
                  title="Apply a sensible per-role default (Sonnet for planning, Haiku for execution, Opus for review)"
                >
                  Apply suggested per-role defaults
                </button>
                <button
                  type="button"
                  className="settings-secondary-btn"
                  onClick={() => setConfig(prev => ({ ...prev, agentModels: Object.fromEntries(AGENTS.map(a => [a.id, ''])) }))}
                >
                  Reset all to default
                </button>
              </div>
              {AGENTS.map(agent => {
                const current = config.agentModels[agent.id] || '';
                const suggested = SUGGESTED_AGENT_MODELS[agent.id];
                const suggestedLabel = suggested ? modelLabel(suggested) : null;
                return (
                  <SettingRow
                    key={agent.id}
                    label={agent.name}
                    description={
                      suggestedLabel && current !== suggested
                        ? `Suggested: ${suggestedLabel} — ${SUGGESTED_RATIONALE[agent.id] || ''}`
                        : SUGGESTED_RATIONALE[agent.id] || `Model for the ${agent.name} agent`
                    }
                  >
                    <select
                      className="settings-select"
                      value={current}
                      onChange={e => updateAgentModel(agent.id, e.target.value)}
                    >
                      <option value="">Use default ({modelLabel(config.defaultModel)})</option>
                      <optgroup label="Haiku — fast + cheap">
                        {MODELS.filter(m => m.value && m.tier === 'haiku').map(m => (
                          <option key={m.value} value={m.value}>{m.label}{m.recommended ? ' ★' : ''}</option>
                        ))}
                      </optgroup>
                      <optgroup label="Sonnet — balanced">
                        {MODELS.filter(m => m.value && m.tier === 'sonnet').map(m => (
                          <option key={m.value} value={m.value}>{m.label}{m.recommended ? ' ★' : ''}</option>
                        ))}
                      </optgroup>
                      <optgroup label="Opus — strongest reasoning">
                        {MODELS.filter(m => m.value && m.tier === 'opus').map(m => (
                          <option key={m.value} value={m.value}>{m.label}{m.recommended ? ' ★' : ''}</option>
                        ))}
                      </optgroup>
                    </select>
                  </SettingRow>
                );
              })}
            </>
          )}

          {section === 'cost' && (
            <>
              <SettingRow label="Cost Limit Per Run ($)" description="Maximum spend on a single pipeline run. Pipeline stops if exceeded.">
                <NumberInput value={config.costLimitPerRun} min={0.5} max={100} step={0.5} onChange={v => update('costLimitPerRun', v)} prefix="$" />
              </SettingRow>
              <SettingRow label="Monthly Cost Limit ($)" description="Total monthly budget. New pipelines are blocked when reached.">
                <NumberInput value={config.costLimitMonthly} min={10} max={10000} step={10} onChange={v => update('costLimitMonthly', v)} prefix="$" />
              </SettingRow>
              <SettingRow label="Warning Threshold (%)" description="Show warning when this percentage of a limit is consumed">
                <NumberInput value={config.warnAtPercent} min={50} max={100} step={5} onChange={v => update('warnAtPercent', v)} suffix="%" />
              </SettingRow>
            </>
          )}

          {section === 'approvals' && (
            <>
              <SettingRow label="Architecture Approval" description="Require human approval for architecture decisions on L/XL tickets">
                <Toggle checked={config.requireArchitectureApproval} onChange={v => update('requireArchitectureApproval', v)} />
              </SettingRow>
              <SettingRow label="Pre-Merge Approval" description="Require human approval before merging PRs">
                <Toggle checked={config.requirePreMergeApproval} onChange={v => update('requirePreMergeApproval', v)} />
              </SettingRow>
              <SettingRow label="Deployment Approval" description="Require approval for infrastructure/deployment changes">
                <Toggle checked={config.requireDeploymentApproval} onChange={v => update('requireDeploymentApproval', v)} />
              </SettingRow>
              <SettingRow label="Auto-approve Small Tickets" description="Skip approval gates for S-complexity tickets">
                <Toggle checked={config.autoApproveSmallTickets} onChange={v => update('autoApproveSmallTickets', v)} />
              </SettingRow>
            </>
          )}

          {section === 'notifications' && (
            <>
              <SettingRow label="Pipeline Completed" description="Notify when a pipeline finishes successfully">
                <Toggle checked={config.notifyOnComplete} onChange={v => update('notifyOnComplete', v)} />
              </SettingRow>
              <SettingRow label="Pipeline Failed" description="Notify when a pipeline encounters an error">
                <Toggle checked={config.notifyOnFailure} onChange={v => update('notifyOnFailure', v)} />
              </SettingRow>
              <SettingRow label="Approval Needed" description="Notify when a pipeline is waiting for human approval">
                <Toggle checked={config.notifyOnApprovalNeeded} onChange={v => update('notifyOnApprovalNeeded', v)} />
              </SettingRow>
              <SettingRow label="Notification Channel" description="Where to send notifications">
                <select className="settings-select" value={config.notificationChannel} onChange={e => update('notificationChannel', e.target.value as AppConfig['notificationChannel'])}>
                  <option value="in-app">In-App</option>
                  <option value="slack">Slack (requires connector)</option>
                  <option value="email">Email</option>
                </select>
              </SettingRow>
            </>
          )}

          {section === 'advanced' && (
            <>
              <SettingRow label="Verbose Logging" description="Log detailed agent reasoning, prompts, and raw responses">
                <Toggle checked={config.verbose} onChange={v => update('verbose', v)} />
              </SettingRow>
              <div className="settings-danger-zone">
                <h4>Danger Zone</h4>
                <p>These actions cannot be undone.</p>
                <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                  <button className="btn btn-outline" style={{ borderColor: 'var(--danger-dim)', color: 'var(--danger)' }}>
                    Clear All Pipeline History
                  </button>
                  <button className="btn btn-outline" style={{ borderColor: 'var(--danger-dim)', color: 'var(--danger)' }}>
                    Reset All Agent Conversations
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Sub-components ---

function SettingRow({ label, description, children }: { label: string; description: string; children: React.ReactNode }) {
  return (
    <div className="setting-row">
      <div className="setting-row-info">
        <div className="setting-row-label">{label}</div>
        <div className="setting-row-desc">{description}</div>
      </div>
      <div className="setting-row-control">{children}</div>
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button className={`settings-toggle ${checked ? 'on' : ''}`} onClick={() => onChange(!checked)} role="switch" aria-checked={checked}>
      <span className="settings-toggle-knob" />
    </button>
  );
}

function NumberInput({ value, min, max, step = 1, onChange, prefix, suffix }: {
  value: number; min: number; max: number; step?: number;
  onChange: (v: number) => void; prefix?: string; suffix?: string;
}) {
  return (
    <div className="settings-number">
      {prefix && <span className="settings-number-affix">{prefix}</span>}
      <input
        type="number"
        className="settings-number-input"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={e => onChange(Number(e.target.value))}
      />
      {suffix && <span className="settings-number-affix">{suffix}</span>}
    </div>
  );
}
