import { useState } from 'react';
import { CheckCircle, XCircle, Loader2, Search, X, ExternalLink, Puzzle, ChevronRight } from 'lucide-react';
import { api } from '../api/client';
import ConnectorLogo from '../components/ConnectorLogos';

// ---------------------------------------------------------------------------
// Plugin registry — all available connectors
// ---------------------------------------------------------------------------

interface PluginField {
  key: string;
  label: string;
  type?: string;
  placeholder: string;
}

interface Plugin {
  id: string;
  name: string;
  category: 'project-management' | 'source-control' | 'ai-model' | 'communication' | 'ci-cd' | 'monitoring' | 'documentation';
  description: string;
  icon: string;        // emoji icon
  color: string;
  installed: boolean;  // has config saved
  connected: boolean;  // connection verified
  fields: PluginField[];
  docsUrl?: string;
}

const PLUGINS: Plugin[] = [
  // Project Management
  {
    id: 'jira', name: 'Jira', category: 'project-management',
    description: 'Fetch tickets, post updates, and track work across sprints. Supports JQL polling for automatic ticket intake.',
    icon: '🔵', color: '#2684FF', installed: false, connected: false,
    fields: [
      { key: 'server_url', label: 'Server URL', placeholder: 'https://your-company.atlassian.net' },
      { key: 'email', label: 'Email', placeholder: 'your-email@company.com' },
      { key: 'api_token', label: 'API Token', type: 'password', placeholder: 'Your Jira API token' },
    ],
    docsUrl: 'https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/',
  },
  {
    id: 'linear', name: 'Linear', category: 'project-management',
    description: 'Sync issues from Linear. Supports webhooks for real-time ticket intake and status updates.',
    icon: '🟣', color: '#5E6AD2', installed: false, connected: false,
    fields: [
      { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'lin_api_...' },
      { key: 'team_id', label: 'Team ID', placeholder: 'Your Linear team ID' },
    ],
  },
  {
    id: 'asana', name: 'Asana', category: 'project-management',
    description: 'Import tasks from Asana projects. Map sections to pipeline phases automatically.',
    icon: '🟠', color: '#F06A6A', installed: false, connected: false,
    fields: [
      { key: 'access_token', label: 'Access Token', type: 'password', placeholder: 'Your Asana access token' },
      { key: 'project_id', label: 'Project ID', placeholder: 'Project GID' },
    ],
  },
  // Source Control
  {
    id: 'github', name: 'GitHub', category: 'source-control',
    description: 'Create branches, commit code, open PRs, and post review comments. Full Git workflow automation.',
    icon: '⚫', color: '#8b949e', installed: false, connected: false,
    fields: [
      { key: 'token', label: 'Personal Access Token', type: 'password', placeholder: 'ghp_...' },
      { key: 'repo', label: 'Repository', placeholder: 'owner/repo-name' },
    ],
  },
  {
    id: 'gitlab', name: 'GitLab', category: 'source-control',
    description: 'Manage merge requests, branches, and CI pipelines on GitLab. Supports self-hosted instances.',
    icon: '🟧', color: '#FC6D26', installed: false, connected: false,
    fields: [
      { key: 'url', label: 'GitLab URL', placeholder: 'https://gitlab.com or self-hosted URL' },
      { key: 'token', label: 'Access Token', type: 'password', placeholder: 'glpat-...' },
      { key: 'project_id', label: 'Project ID', placeholder: 'Numeric project ID' },
    ],
  },
  {
    id: 'bitbucket', name: 'Bitbucket', category: 'source-control',
    description: 'Create pull requests and manage repositories on Bitbucket Cloud or Server.',
    icon: '🔷', color: '#2684FF', installed: false, connected: false,
    fields: [
      { key: 'username', label: 'Username', placeholder: 'Your Bitbucket username' },
      { key: 'app_password', label: 'App Password', type: 'password', placeholder: 'App password' },
      { key: 'workspace', label: 'Workspace', placeholder: 'workspace-slug' },
    ],
  },
  // AI Models
  {
    id: 'anthropic', name: 'Anthropic', category: 'ai-model',
    description: 'Powers all agents with Claude. Required for the pipeline to function. Supports Sonnet and Opus models.',
    icon: '🤖', color: '#D4A574', installed: false, connected: false,
    fields: [
      { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'sk-ant-...' },
      { key: 'model', label: 'Default Model', placeholder: 'claude-sonnet-4-20250514' },
    ],
  },
  {
    id: 'openai', name: 'OpenAI', category: 'ai-model',
    description: 'Alternative AI provider. Use GPT-4o for agents that don\'t require Claude-specific features.',
    icon: '🟢', color: '#10A37F', installed: false, connected: false,
    fields: [
      { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'sk-...' },
      { key: 'model', label: 'Model', placeholder: 'gpt-4o' },
    ],
  },
  // Communication
  {
    id: 'slack', name: 'Slack', category: 'communication',
    description: 'Send pipeline notifications, approval requests, and status updates to Slack channels.',
    icon: '💬', color: '#E01E5A', installed: false, connected: false,
    fields: [
      { key: 'webhook_url', label: 'Webhook URL', placeholder: 'https://hooks.slack.com/services/...' },
      { key: 'channel', label: 'Default Channel', placeholder: '#engineering' },
    ],
  },
  {
    id: 'discord', name: 'Discord', category: 'communication',
    description: 'Post pipeline updates and agent activity to Discord channels via webhooks.',
    icon: '🎮', color: '#5865F2', installed: false, connected: false,
    fields: [
      { key: 'webhook_url', label: 'Webhook URL', placeholder: 'https://discord.com/api/webhooks/...' },
    ],
  },
  {
    id: 'teams', name: 'Microsoft Teams', category: 'communication',
    description: 'Send adaptive cards with pipeline status to Teams channels.',
    icon: '🟦', color: '#6264A7', installed: false, connected: false,
    fields: [
      { key: 'webhook_url', label: 'Incoming Webhook URL', placeholder: 'https://outlook.office.com/webhook/...' },
    ],
  },
  // CI/CD
  {
    id: 'github_actions', name: 'GitHub Actions', category: 'ci-cd',
    description: 'Trigger workflows, monitor runs, and update pipeline status from GitHub Actions.',
    icon: '⚡', color: '#2088FF', installed: false, connected: false,
    fields: [
      { key: 'token', label: 'GitHub Token', type: 'password', placeholder: 'ghp_...' },
      { key: 'repo', label: 'Repository', placeholder: 'owner/repo' },
    ],
  },
  {
    id: 'jenkins', name: 'Jenkins', category: 'ci-cd',
    description: 'Trigger Jenkins builds and monitor job status for deployment verification.',
    icon: '🔴', color: '#D33833', installed: false, connected: false,
    fields: [
      { key: 'url', label: 'Jenkins URL', placeholder: 'https://jenkins.company.com' },
      { key: 'username', label: 'Username', placeholder: 'admin' },
      { key: 'token', label: 'API Token', type: 'password', placeholder: 'Jenkins API token' },
    ],
  },
  // Monitoring
  {
    id: 'datadog', name: 'Datadog', category: 'monitoring',
    description: 'Send pipeline metrics and traces to Datadog for observability dashboards.',
    icon: '🐕', color: '#632CA6', installed: false, connected: false,
    fields: [
      { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'Datadog API key' },
      { key: 'site', label: 'Site', placeholder: 'datadoghq.com' },
    ],
  },
  {
    id: 'sentry', name: 'Sentry', category: 'monitoring',
    description: 'Track errors from pipeline runs and agent failures in Sentry.',
    icon: '🔺', color: '#362D59', installed: false, connected: false,
    fields: [
      { key: 'dsn', label: 'DSN', placeholder: 'https://...@sentry.io/...' },
    ],
  },
  // Documentation
  {
    id: 'notion', name: 'Notion', category: 'documentation',
    description: 'Push architecture docs, test plans, and review summaries to Notion pages.',
    icon: '📝', color: '#999', installed: false, connected: false,
    fields: [
      { key: 'api_key', label: 'Integration Token', type: 'password', placeholder: 'ntn_...' },
      { key: 'database_id', label: 'Database ID', placeholder: 'Notion database ID' },
    ],
  },
  {
    id: 'confluence', name: 'Confluence', category: 'documentation',
    description: 'Publish architecture decisions and sprint documentation to Confluence spaces.',
    icon: '📘', color: '#1868DB', installed: false, connected: false,
    fields: [
      { key: 'url', label: 'Confluence URL', placeholder: 'https://your-company.atlassian.net/wiki' },
      { key: 'email', label: 'Email', placeholder: 'your-email@company.com' },
      { key: 'api_token', label: 'API Token', type: 'password', placeholder: 'Confluence API token' },
      { key: 'space_key', label: 'Space Key', placeholder: 'ENG' },
    ],
  },
];

const CATEGORIES: { id: string; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'project-management', label: 'Project Management' },
  { id: 'source-control', label: 'Source Control' },
  { id: 'ai-model', label: 'AI Models' },
  { id: 'communication', label: 'Communication' },
  { id: 'ci-cd', label: 'CI/CD' },
  { id: 'monitoring', label: 'Monitoring' },
  { id: 'documentation', label: 'Documentation' },
];

// ---------------------------------------------------------------------------
// Connector config modal
// ---------------------------------------------------------------------------

function ConnectorModal({ plugin, onClose }: { plugin: Plugin; onClose: () => void }) {
  const [form, setForm] = useState<Record<string, string>>(
    Object.fromEntries(plugin.fields.map(f => [f.key, '']))
  );
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    try {
      await api.updateSettings(plugin.id, form);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch { /* ok */ }
  };

  const handleTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      const res = await api.testConnection(plugin.id);
      setResult(res);
    } catch {
      setResult({ success: false, message: 'Could not reach the API server' });
    }
    setTesting(false);
  };

  return (
    <div className="connector-modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="connector-modal">
        <div className="connector-modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span className="connector-modal-icon" style={{ background: plugin.color + '22', borderColor: plugin.color + '44' }}><ConnectorLogo id={plugin.id} size={22} /></span>
            <div>
              <h3 style={{ margin: 0, fontSize: 18 }}>{plugin.name}</h3>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'capitalize' }}>{plugin.category.replace('-', ' ')}</span>
            </div>
          </div>
          <button className="chat-popup-btn" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="connector-modal-body">
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20, lineHeight: 1.6 }}>{plugin.description}</p>

          {plugin.fields.map(field => (
            <div className="form-group" key={field.key}>
              <label>{field.label}</label>
              <input
                className="form-input"
                type={field.type || 'text'}
                placeholder={field.placeholder}
                value={form[field.key] || ''}
                onChange={e => setForm({ ...form, [field.key]: e.target.value })}
              />
            </div>
          ))}

          {result && (
            <div className={`alert ${result.success ? 'success' : 'error'}`}>
              {result.success ? <CheckCircle size={14} /> : <XCircle size={14} />}
              {result.message}
            </div>
          )}

          {saved && (
            <div className="alert success"><CheckCircle size={14} /> Configuration saved</div>
          )}

          {plugin.docsUrl && (
            <a href={plugin.docsUrl} target="_blank" rel="noopener" className="connector-docs-link">
              <ExternalLink size={12} /> View setup documentation <ChevronRight size={12} />
            </a>
          )}
        </div>

        <div className="connector-modal-footer">
          <button className="btn btn-outline" onClick={handleTest} disabled={testing}>
            {testing ? <><Loader2 size={14} className="spin" /> Testing...</> : 'Test Connection'}
          </button>
          <button className="btn btn-primary" onClick={handleSave}>
            Save & Connect
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('all');
  const [configuring, setConfiguring] = useState<Plugin | null>(null);

  const filtered = PLUGINS.filter(p => {
    const matchesSearch = !search || p.name.toLowerCase().includes(search.toLowerCase()) || p.description.toLowerCase().includes(search.toLowerCase());
    const matchesCat = category === 'all' || p.category === category;
    return matchesSearch && matchesCat;
  });

  const installed = PLUGINS.filter(p => p.installed);

  return (
    <>
      <div className="page-header">
        <h2><Puzzle size={24} style={{ verticalAlign: 'middle', marginRight: 8 }} />Connectors</h2>
        <p>Browse and install integrations for your pipeline</p>
      </div>

      {/* Search + filter bar */}
      <div className="connector-toolbar">
        <div className="connector-search">
          <Search size={16} className="connector-search-icon" />
          <input
            className="connector-search-input"
            placeholder="Search connectors..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {search && (
            <button className="connector-search-clear" onClick={() => setSearch('')}><X size={14} /></button>
          )}
        </div>
        <div className="connector-categories">
          {CATEGORIES.map(cat => (
            <button
              key={cat.id}
              className={`connector-cat-btn ${category === cat.id ? 'active' : ''}`}
              onClick={() => setCategory(cat.id)}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* Installed section */}
      {installed.length > 0 && (
        <>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 12 }}>
            Installed ({installed.length})
          </div>
          <div className="connector-grid" style={{ marginBottom: 32 }}>
            {installed.map(p => (
              <PluginCard key={p.id} plugin={p} onConfigure={() => setConfiguring(p)} />
            ))}
          </div>
        </>
      )}

      {/* Available */}
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 12 }}>
        {category === 'all' ? 'All Connectors' : CATEGORIES.find(c => c.id === category)?.label} ({filtered.length})
      </div>
      <div className="connector-grid">
        {filtered.map(p => (
          <PluginCard key={p.id} plugin={p} onConfigure={() => setConfiguring(p)} />
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="empty-state">
          <h3>No connectors found</h3>
          <p>Try a different search term or category.</p>
        </div>
      )}

      {/* Config modal */}
      {configuring && (
        <ConnectorModal plugin={configuring} onClose={() => setConfiguring(null)} />
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </>
  );
}

// ---------------------------------------------------------------------------
// Plugin card
// ---------------------------------------------------------------------------

function PluginCard({ plugin, onConfigure }: { plugin: Plugin; onConfigure: () => void }) {
  return (
    <div className="connector-card" onClick={onConfigure}>
      <div className="connector-card-top">
        <span className="connector-card-icon" style={{ background: plugin.color + '18', borderColor: plugin.color + '33' }}>
          <ConnectorLogo id={plugin.id} size={22} />
        </span>
        {plugin.connected ? (
          <span className="badge completed" style={{ fontSize: 11 }}>Connected</span>
        ) : plugin.installed ? (
          <span className="badge running" style={{ fontSize: 11 }}>Installed</span>
        ) : null}
      </div>
      <div className="connector-card-name">{plugin.name}</div>
      <div className="connector-card-cat">{plugin.category.replace('-', ' ')}</div>
      <div className="connector-card-desc">{plugin.description}</div>
      <button className="connector-card-btn" onClick={e => { e.stopPropagation(); onConfigure(); }}>
        {plugin.installed ? 'Configure' : 'Connect'}
      </button>
    </div>
  );
}
