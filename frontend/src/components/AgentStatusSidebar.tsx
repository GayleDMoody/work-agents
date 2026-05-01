/**
 * Persistent right sidebar showing every agent's live status + thought stream.
 *
 * Replaces the earlier floating LiveAgentPanels stack. Always visible, fixed
 * 380px wide, full height of the dashboard area. Each agent gets a card:
 *   - Avatar + role name + colored status pill
 *   - One-line "current task" (when busy) or "idle"
 *   - Click chevron → expand to see formatted thought stream
 *
 * Streamed events come from the same useAgentThoughts hook (WebSocket).
 * Content rendering is delegated to FormattedThought so JSON/code/text each
 * get sensible treatment instead of a raw dump.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronRight, ChevronDown, Bot, Brain, AlertTriangle, ArrowDownLeft, ArrowUpRight, MessageSquare, Wifi, WifiOff } from 'lucide-react';
import type { Agent } from '../types';
import type { AgentThought } from '../api/client';
import { useAgentThoughts } from '../hooks/useAgentThoughts';
import FormattedThought from './FormattedThought';

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

// Canonical pipeline order for the sidebar list
const ORDER = ['product', 'pm', 'architect', 'backend', 'frontend', 'devops', 'qa', 'code_review'];

interface Props {
  agents: Agent[];
}

export default function AgentStatusSidebar({ agents }: Props) {
  const { byAgent, connected, startedAgents } = useAgentThoughts();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // Auto-expand the latest started agent so the user sees what's currently happening
  // without having to manually click. Auto-collapse all others as new ones start.
  const lastStartedRef = useRef<string | null>(null);
  useEffect(() => {
    // The hook adds to startedAgents in order; pick the most recently added
    const recent = [...startedAgents];
    const current = recent[recent.length - 1] ?? null;
    if (current && current !== lastStartedRef.current) {
      lastStartedRef.current = current;
      setExpanded({ [current]: true });
    }
  }, [startedAgents]);

  // Sort agents by canonical pipeline order
  const orderedAgents = useMemo(() => {
    const map = new Map(agents.map(a => [a.id, a]));
    return ORDER.map(id => map.get(id)).filter(Boolean) as Agent[];
  }, [agents]);

  const totalMsgs = Object.values(byAgent).reduce((n, list) => n + (list?.length ?? 0), 0);

  return (
    <aside className="agent-sidebar">
      <div className="agent-sidebar-header">
        <div>
          <div className="agent-sidebar-title">Agent Status</div>
          <div className="agent-sidebar-sub">{totalMsgs} live event{totalMsgs === 1 ? '' : 's'}</div>
        </div>
        <span className={`agent-sidebar-conn ${connected ? 'on' : 'off'}`} title={connected ? 'Live stream connected' : 'Reconnecting…'}>
          {connected ? <Wifi size={12} /> : <WifiOff size={12} />}
        </span>
      </div>

      <div className="agent-sidebar-body">
        {orderedAgents.map(agent => {
          const vis = AGENT_VISUALS[agent.id] || { color: '#8b949e', label: agent.id, icon: '🤖' };
          const thoughts = byAgent[agent.id] || [];
          const isExpanded = !!expanded[agent.id];
          return (
            <AgentCard
              key={agent.id}
              agent={agent}
              vis={vis}
              thoughts={thoughts}
              expanded={isExpanded}
              onToggle={() => setExpanded(prev => ({ ...prev, [agent.id]: !prev[agent.id] }))}
            />
          );
        })}
      </div>
    </aside>
  );
}

function AgentCard({
  agent, vis, thoughts, expanded, onToggle,
}: {
  agent: Agent;
  vis: { color: string; label: string; icon: string };
  thoughts: AgentThought[];
  expanded: boolean;
  onToggle: () => void;
}) {
  const status = agent.status;
  const lastThought = thoughts[thoughts.length - 1];
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll the body to the latest message when expanded
  useEffect(() => {
    if (!expanded || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [expanded, thoughts.length]);

  const subText = agent.current_task
    ? agent.current_task
    : lastThought
      ? thoughtSummary(lastThought)
      : status === 'busy' ? 'Working…' : 'Idle';

  return (
    <div className={`agent-card agent-card--${status}`} style={{ borderLeftColor: vis.color }}>
      <button type="button" className="agent-card-header" onClick={onToggle}>
        <span className="agent-card-icon" style={{ background: vis.color + '22' }}>{vis.icon}</span>
        <div className="agent-card-titles">
          <div className="agent-card-name" style={{ color: vis.color }}>{vis.label}</div>
          <div className="agent-card-sub" title={subText}>{subText}</div>
        </div>
        <StatusPill status={status} count={thoughts.length} />
        <span className="agent-card-chevron">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>

      {expanded && (
        <div className="agent-card-body" ref={scrollRef}>
          {thoughts.length === 0 ? (
            <div className="agent-card-empty">No activity yet.</div>
          ) : (
            thoughts.map((t, i) => <ThoughtRow key={i} t={t} color={vis.color} />)
          )}
        </div>
      )}
    </div>
  );
}

function StatusPill({ status, count }: { status: string; count: number }) {
  if (status === 'busy') return <span className="agent-pill agent-pill--busy">{count > 0 ? `${count}` : 'busy'}</span>;
  if (status === 'error') return <span className="agent-pill agent-pill--error">error</span>;
  if (count > 0) return <span className="agent-pill agent-pill--idle">{count} msgs</span>;
  return <span className="agent-pill agent-pill--idle">idle</span>;
}

function ThoughtRow({ t, color }: { t: AgentThought; color: string }) {
  const meta = thoughtMeta(t);
  return (
    <div className={`thought thought--${meta.tone}`}>
      <div className="thought-meta" style={{ color }}>
        <span className="thought-icon">{meta.icon}</span>
        <span className="thought-label">{meta.label}</span>
        {typeof t.duration_seconds === 'number' && (
          <span className="thought-stat">{t.duration_seconds.toFixed(1)}s</span>
        )}
        {typeof t.input_tokens === 'number' && (
          <span className="thought-stat">↑{t.input_tokens}</span>
        )}
        {typeof t.output_tokens === 'number' && (
          <span className="thought-stat">↓{t.output_tokens}</span>
        )}
      </div>
      <div className="thought-body">
        <FormattedThought content={t.content} />
      </div>
    </div>
  );
}

function thoughtMeta(t: AgentThought): { icon: React.ReactNode; label: string; tone: string } {
  switch (t.kind) {
    case 'prompt':           return { icon: <Brain size={11} />,         label: 'thinking',      tone: 'prompt' };
    case 'response':         return { icon: <Bot size={11} />,           label: 'reply',         tone: 'response' };
    case 'error':            return { icon: <AlertTriangle size={11} />, label: 'error',         tone: 'error' };
    case 'message_sent':     return { icon: <ArrowUpRight size={11} />,  label: 'sent',          tone: 'msg-out' };
    case 'message_received': return { icon: <ArrowDownLeft size={11} />, label: 'received',      tone: 'msg-in' };
    default:                 return { icon: <MessageSquare size={11} />, label: t.kind || 'event', tone: 'default' };
  }
}

function thoughtSummary(t: AgentThought): string {
  const summary = humanSummary(t.content);
  switch (t.kind) {
    case 'prompt':           return `Thinking: ${summary}`;
    case 'response':         return summary;
    case 'error':            return `Error: ${summary}`;
    case 'message_sent':     return `Sent: ${summary}`;
    case 'message_received': return `Received: ${summary}`;
    default:                 return summary;
  }
}

/** Build a 1-line human-readable summary from arbitrary agent content.
 *  Skips markdown fences, strips obvious JSON syntax, and surfaces the
 *  most useful field (summary / decision / title / approach / verdict). */
function humanSummary(content: string): string {
  const text = (content || '').trim();
  if (!text) return '(no content)';

  // Try to find a JSON object anywhere in the content
  const json = tryExtractJson(text);
  if (json && typeof json === 'object' && !Array.isArray(json)) {
    const obj = json as Record<string, unknown>;
    // Look for canonical "main message" fields, in priority order
    const fieldPriority = [
      'plan_summary', 'summary', 'rationale', 'reasoning',
      'verdict', 'decision', 'approach',
      'title', 'description',
      'response', 'content', 'message',
    ];
    for (const key of fieldPriority) {
      const v = obj[key];
      if (typeof v === 'string' && v.trim()) return clip(v.trim());
    }
    // Fallback: list the top-level keys
    const keys = Object.keys(obj);
    if (keys.length > 0) return `JSON with ${keys.length} field${keys.length === 1 ? '' : 's'}: ${keys.slice(0, 4).join(', ')}${keys.length > 4 ? '…' : ''}`;
  }

  // Plain text: skip blank lines + markdown fences and pull the first real sentence
  const lines = text.split('\n');
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('```')) continue;            // fence
    if (line.startsWith('#')) continue;              // markdown heading
    if (/^[{\[]\s*$/.test(line)) continue;           // bare brace
    if (/^[}\]],?\s*$/.test(line)) continue;         // bare close
    if (/^"[^"]*":\s*[{\[]\s*$/.test(line)) continue; // "key": {
    return clip(line);
  }
  return clip(text);
}

function clip(s: string, max = 70): string {
  const oneLine = s.replace(/\s+/g, ' ').trim();
  return oneLine.length > max ? oneLine.slice(0, max - 1) + '…' : oneLine;
}

function tryExtractJson(text: string): unknown | null {
  // Strip surrounding markdown fences first (handles unclosed fences too)
  const fencedFull = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  const fencedOpen = !fencedFull && text.match(/```(?:json)?\s*\n?([\s\S]*)$/);
  const candidate = fencedFull ? fencedFull[1] : (fencedOpen ? fencedOpen[1] : text);
  // Find the first { or [
  const firstBrace = Math.min(
    ...['{', '['].map(c => {
      const i = candidate.indexOf(c);
      return i === -1 ? Infinity : i;
    }),
  );
  if (firstBrace === Infinity) return null;
  const start = candidate.slice(firstBrace);

  // 1. Direct parse
  try { return JSON.parse(start); } catch { /* fall through */ }

  // 2. Try every prefix that closes a top-level object/array
  for (const end of findCloseCandidates(start)) {
    try { return JSON.parse(start.slice(0, end)); } catch { /* next */ }
  }

  // 3. Repair: balance unclosed quotes/brackets, strip a partial trailing
  //    entry, and try parsing the syntactically-completed string. Same
  //    strategy as FormattedThought.tryRepairJson — kept inline to avoid
  //    a cross-component import.
  let inStr = false, escape = false;
  const stack: ('O' | 'A')[] = [];
  for (let i = 0; i < start.length; i++) {
    const c = start[i];
    if (escape) { escape = false; continue; }
    if (c === '\\') { escape = true; continue; }
    if (c === '"')  { inStr = !inStr; continue; }
    if (inStr) continue;
    if (c === '{') stack.push('O');
    else if (c === '[') stack.push('A');
    else if (c === '}' || c === ']') stack.pop();
  }
  if (stack.length > 0 || inStr) {
    let r = start;
    if (escape) r = r.slice(0, -1);
    if (inStr) r += '"';
    r = r.replace(/[\s,]+$/, '');
    for (let attempt = 0; attempt < 4; attempt++) {
      let candidate = r;
      for (let i = stack.length - 1; i >= 0; i--) candidate += stack[i] === 'O' ? '}' : ']';
      try { return JSON.parse(candidate); } catch { /* trim and retry */ }
      const cut = Math.max(r.lastIndexOf(','), r.lastIndexOf('['), r.lastIndexOf('{'));
      if (cut <= 0) break;
      r = r.slice(0, cut).replace(/[\s,]+$/, '');
    }
  }
  return null;
}

function findCloseCandidates(s: string): number[] {
  const out: number[] = [];
  let depth = 0, inStr = false, escape = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (escape) { escape = false; continue; }
    if (c === '\\') { escape = true; continue; }
    if (c === '"') { inStr = !inStr; continue; }
    if (inStr) continue;
    if (c === '{' || c === '[') depth++;
    else if (c === '}' || c === ']') {
      depth--;
      if (depth === 0) out.unshift(i + 1);
    }
  }
  return out.slice(0, 5);
}
