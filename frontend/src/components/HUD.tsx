import { useEffect, useState } from 'react';
import { Play, Zap, DollarSign, Bot, Activity, Folder } from 'lucide-react';
import type { DashboardData } from '../types';
import { api, type LocalRepoSummary, type GitHubRepoSummary } from '../api/client';

interface Props {
  data: DashboardData;
  onTrigger: (ticketKey: string, repo?: { kind: 'local' | 'github'; id: string }) => void;
}

interface RepoChoice {
  key: string;             // unique key for the dropdown
  label: string;           // display name
  kind: 'local' | 'github';
  id: string;              // repo_id on the backend (folder name or owner/repo)
  hint?: string;           // small subtitle
}

export default function HUD({ data, onTrigger }: Props) {
  const [ticketKey, setTicketKey] = useState('');
  const [repos, setRepos] = useState<RepoChoice[]>([]);
  const [selectedRepoKey, setSelectedRepoKey] = useState<string>('');

  // Discover available repos (local + GitHub) once on mount + every 30s
  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      const out: RepoChoice[] = [];
      try {
        const r = await api.listLocalRepos();
        for (const lr of r.repos as LocalRepoSummary[]) {
          out.push({
            key: `local:${lr.path}`,
            label: lr.name,
            kind: 'local',
            id: lr.name,
            hint: lr.branch ? `local · ${lr.branch}` : 'local',
          });
        }
      } catch { /* ignore */ }
      try {
        const gh = await api.listGitHubRepos();
        for (const r of gh.slice(0, 30) as GitHubRepoSummary[]) {
          out.push({
            key: `github:${r.full_name}`,
            label: r.full_name,
            kind: 'github',
            id: r.full_name,
            hint: r.private ? 'github · private' : 'github · public',
          });
        }
      } catch { /* ignore — likely not authenticated */ }
      if (mounted) setRepos(out);
    };
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => { mounted = false; clearInterval(t); };
  }, []);

  const selected = repos.find(r => r.key === selectedRepoKey);

  const handleTrigger = () => {
    if (!ticketKey.trim()) return;
    const repo = selected ? { kind: selected.kind, id: selected.id } : undefined;
    onTrigger(ticketKey.trim(), repo);
    setTicketKey('');
  };

  // Build event ticker from recent runs, falling back to a status summary
  // when there's nothing to show so the bar never sits empty.
  const runEvents = data.recent_runs.flatMap(run => {
    const statusEmoji = run.status === 'completed' ? '✅' : run.status === 'running' ? '⚡' : '❌';
    return [`${statusEmoji} ${run.ticket_key} — ${run.current_phase} (${run.agents_used.length} agents, $${run.total_cost.toFixed(2)})`];
  });

  const anyServiceConnected = Object.values(data.services).some(s => s?.connected);
  const connectedCount = Object.values(data.services).filter(s => s?.connected).length;
  const totalServices = Object.keys(data.services).length;

  const idleSummary = [
    anyServiceConnected
      ? `🟢 System ready — ${connectedCount}/${totalServices} services connected`
      : `🔴 Backend offline — start the API (uvicorn src.api.app:app) to run pipelines`,
    `🤖 ${data.busy_agents + data.idle_agents} agents available · ${data.busy_agents} busy · ${data.idle_agents} idle`,
    `💬 Tip: enter a JIRA ticket key above and click Deploy to kick off a pipeline`,
    `📊 Lifetime: ${data.completed_pipelines} completed · ${data.failed_pipelines} failed · $${data.total_cost.toFixed(2)} spent`,
  ];

  const events = runEvents.length > 0 ? runEvents : idleSummary;

  return (
    <>
      {/* Top-left: Trigger bar */}
      <div className="hud-trigger">
        <div className="hud-panel">
          <div className="hud-trigger-row">
            <input
              className="hud-input"
              placeholder="JIRA ticket key..."
              value={ticketKey}
              onChange={e => setTicketKey(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleTrigger()}
            />
            <select
              className="hud-input hud-repo-select"
              value={selectedRepoKey}
              onChange={e => setSelectedRepoKey(e.target.value)}
              title={selected ? `${selected.kind}: ${selected.id}${selected.hint ? ' · ' + selected.hint : ''}` : 'Optional: pick a repo so agents work on real code'}
            >
              <option value="">— No repo (artifacts only) —</option>
              {repos.length > 0 && (
                <optgroup label="Local clones">
                  {repos.filter(r => r.kind === 'local').map(r => (
                    <option key={r.key} value={r.key}>{r.label}</option>
                  ))}
                </optgroup>
              )}
              {repos.some(r => r.kind === 'github') && (
                <optgroup label="GitHub (OAuth)">
                  {repos.filter(r => r.kind === 'github').map(r => (
                    <option key={r.key} value={r.key}>{r.label}</option>
                  ))}
                </optgroup>
              )}
            </select>
            <button className="hud-btn" onClick={handleTrigger} disabled={!ticketKey.trim()}>
              <Play size={14} /> Deploy
            </button>
          </div>
          {selected && (
            <div className="hud-repo-hint">
              <Folder size={11} />
              <span>{selected.kind === 'local' ? selected.id : selected.label}</span>
              <span className="hud-repo-hint-sub">— agents will read this repo and propose changes</span>
            </div>
          )}
        </div>
      </div>

      {/* Top-right: Stats */}
      <div className="hud-stats">
        <div className="hud-panel">
          <div className="hud-stat-row">
            <div className="hud-stat">
              <Activity size={12} />
              <span className="hud-stat-val" style={{ color: 'var(--accent)' }}>{data.active_pipelines}</span>
              <span className="hud-stat-label">Active</span>
            </div>
            <div className="hud-stat">
              <Zap size={12} />
              <span className="hud-stat-val" style={{ color: 'var(--success)' }}>{data.completed_pipelines}</span>
              <span className="hud-stat-label">Done</span>
            </div>
            <div className="hud-stat">
              <Bot size={12} />
              <span className="hud-stat-val" style={{ color: 'var(--warning)' }}>{data.busy_agents}/{data.busy_agents + data.idle_agents}</span>
              <span className="hud-stat-label">Busy</span>
            </div>
            <div className="hud-stat">
              <DollarSign size={12} />
              <span className="hud-stat-val">${data.total_cost.toFixed(2)}</span>
              <span className="hud-stat-label">Cost</span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom: Event ticker */}
      <div className="hud-ticker">
        <div className="hud-panel hud-ticker-panel">
          <div className="ticker-track">
            <div className="ticker-content">
              {events.map((evt, i) => (
                <span key={i} className="ticker-item">{evt}</span>
              ))}
              {/* Duplicate for seamless loop */}
              {events.map((evt, i) => (
                <span key={`dup-${i}`} className="ticker-item">{evt}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
