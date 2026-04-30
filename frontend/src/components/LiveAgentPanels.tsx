/**
 * Stack of live chat-style panels — one per currently-busy agent.
 *
 * Each panel auto-opens when its agent flips to status=busy and shows the
 * agent's streamed thought feed (Claude prompts, Claude responses, inter-agent
 * messages) as message bubbles in real time. When the agent finishes the
 * panel stays visible (collapsed) so the user can scroll through what
 * happened. User can pin / unpin or close manually.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Bot, Brain, MessageSquare, X, ChevronDown, ChevronUp, AlertTriangle, ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import type { Agent } from '../types';
import type { AgentThought } from '../api/client';
import { useAgentThoughts, replayAgentThoughts } from '../hooks/useAgentThoughts';

const AGENT_VISUALS: Record<string, { color: string; label: string; icon: string }> = {
  product:     { color: '#bc8cff', label: 'Product',   icon: '📋' },
  pm:          { color: '#58a6ff', label: 'PM',        icon: '📊' },
  architect:   { color: '#f0883e', label: 'Architect', icon: '🏗️' },
  frontend:    { color: '#3fb950', label: 'Frontend',  icon: '🎨' },
  backend:     { color: '#d29922', label: 'Backend',   icon: '⚙️' },
  qa:          { color: '#f85149', label: 'QA',        icon: '🧪' },
  devops:      { color: '#56d4dd', label: 'DevOps',    icon: '🚀' },
  code_review: { color: '#a371f7', label: 'Reviewer',  icon: '👁️' },
};

interface Props {
  agents: Agent[];
}

export default function LiveAgentPanels({ agents }: Props) {
  const { byAgent, connected, startedAgents } = useAgentThoughts();

  // Track which agent panels should be visible. An agent is added the moment
  // we see its agent_started event over the WebSocket (independent of the
  // dashboard's polled status). User can manually close which dismisses it
  // for the rest of the session unless re-triggered.
  const [openIds, setOpenIds] = useState<string[]>([]);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const dismissedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    let didChange = false;
    const next = [...openIds];
    for (const id of startedAgents) {
      if (!dismissedRef.current.has(id) && !next.includes(id)) {
        next.push(id);
        didChange = true;
        // Best-effort backlog replay (REST). The WS will pick up new events.
        replayAgentThoughts(id).then(() => { /* hook state already merged */ });
      }
    }
    if (didChange) setOpenIds(next);
  }, [startedAgents, openIds]);

  const close = (id: string) => {
    dismissedRef.current.add(id);
    setOpenIds(prev => prev.filter(x => x !== id));
  };
  const toggleCollapse = (id: string) => {
    setCollapsed(prev => ({ ...prev, [id]: !prev[id] }));
  };

  if (openIds.length === 0) return null;

  return (
    <div className="live-panels-stack">
      {!connected && (
        <div className="live-panels-status">live stream reconnecting…</div>
      )}
      {openIds.map(id => {
        const agent = agents.find(a => a.id === id);
        if (!agent) return null;
        const thoughts = byAgent[id] || [];
        return (
          <LivePanel
            key={id}
            agent={agent}
            thoughts={thoughts}
            collapsed={!!collapsed[id]}
            onClose={() => close(id)}
            onToggle={() => toggleCollapse(id)}
          />
        );
      })}
    </div>
  );
}

function LivePanel({
  agent, thoughts, collapsed, onClose, onToggle,
}: {
  agent: Agent;
  thoughts: AgentThought[];
  collapsed: boolean;
  onClose: () => void;
  onToggle: () => void;
}) {
  const vis = AGENT_VISUALS[agent.id] || { color: '#888', label: agent.id, icon: '🤖' };
  const isBusy = agent.status === 'busy';
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [thoughts.length]);

  return (
    <div className="live-panel" style={{ borderColor: vis.color + '55' }}>
      <div className="live-panel-header" style={{ background: vis.color + '14' }}>
        <span className="live-panel-icon">{vis.icon}</span>
        <div className="live-panel-titles">
          <div className="live-panel-name" style={{ color: vis.color }}>{vis.label}</div>
          <div className="live-panel-sub">
            {isBusy ? (
              <span className="live-panel-pulse">●</span>
            ) : (
              <span style={{ color: 'var(--text-muted)' }}>idle</span>
            )}
            <span className="live-panel-count">{thoughts.length} msgs</span>
          </div>
        </div>
        <div className="live-panel-actions">
          <button className="live-panel-btn" onClick={onToggle} aria-label={collapsed ? 'Expand' : 'Collapse'}>
            {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          <button className="live-panel-btn" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="live-panel-body" ref={scrollRef}>
          {thoughts.length === 0 ? (
            <div className="live-panel-empty">Waiting for first thought…</div>
          ) : (
            thoughts.map((t, i) => <ThoughtBubble key={i} t={t} color={vis.color} />)
          )}
        </div>
      )}
    </div>
  );
}

function ThoughtBubble({ t, color }: { t: AgentThought; color: string }) {
  const meta = useMemo(() => {
    switch (t.kind) {
      case 'prompt':           return { icon: <Brain size={12} />,           label: 'thinking',           tone: 'prompt' };
      case 'response':         return { icon: <Bot size={12} />,             label: 'reply',              tone: 'response' };
      case 'error':            return { icon: <AlertTriangle size={12} />,   label: 'error',              tone: 'error' };
      case 'message_sent':     return { icon: <ArrowUpRight size={12} />,    label: 'msg sent',           tone: 'msg-out' };
      case 'message_received': return { icon: <ArrowDownLeft size={12} />,   label: 'msg received',       tone: 'msg-in' };
      default:                 return { icon: <MessageSquare size={12} />,   label: t.kind,               tone: 'default' };
    }
  }, [t.kind]);

  return (
    <div className={`live-thought live-thought--${meta.tone}`}>
      <div className="live-thought-meta" style={{ color }}>
        {meta.icon}
        <span>{meta.label}</span>
        {typeof t.duration_seconds === 'number' && (
          <span className="live-thought-stat">{t.duration_seconds.toFixed(1)}s</span>
        )}
        {typeof t.input_tokens === 'number' && (
          <span className="live-thought-stat">↑{t.input_tokens} ↓{t.output_tokens}</span>
        )}
      </div>
      <div className="live-thought-content">{t.content}</div>
    </div>
  );
}
