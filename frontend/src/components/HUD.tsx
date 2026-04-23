import { useState } from 'react';
import { Play, Zap, DollarSign, Bot, Activity } from 'lucide-react';
import type { DashboardData } from '../types';

interface Props {
  data: DashboardData;
  onTrigger: (ticketKey: string) => void;
}

export default function HUD({ data, onTrigger }: Props) {
  const [ticketKey, setTicketKey] = useState('');

  const handleTrigger = () => {
    if (!ticketKey.trim()) return;
    onTrigger(ticketKey.trim());
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
            <button className="hud-btn" onClick={handleTrigger} disabled={!ticketKey.trim()}>
              <Play size={14} /> Deploy
            </button>
          </div>
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
