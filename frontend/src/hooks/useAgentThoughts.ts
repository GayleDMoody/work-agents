/**
 * Subscribe to the backend's live agent-thought stream over WebSocket.
 *
 * Yields a map of agentId → recent AgentThought events. Each panel can pull
 * the slice for its own agent. Auto-reconnects on disconnect with exponential
 * backoff so the demo stays solid under brief blips.
 */
import { useEffect, useRef, useState } from 'react';
import { api, WS_URL, type AgentThought } from '../api/client';

interface ThoughtsState {
  /** Per-agent backlog. Newest at the end. Capped to MAX_PER_AGENT. */
  byAgent: Record<string, AgentThought[]>;
  /** True while the WS is connected. */
  connected: boolean;
  /** Set of agent ids that have been seen in agent_started events. We track
   *  this independently of the polled `agent.status` because Haiku-tier
   *  agents can finish their task in <1s, well below the dashboard's 3s poll
   *  interval, so state transitions would otherwise be missed. */
  startedAgents: Set<string>;
}

const MAX_PER_AGENT = 80;

export function useAgentThoughts(): ThoughtsState {
  const [state, setState] = useState<ThoughtsState>({ byAgent: {}, connected: false, startedAgents: new Set() });
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(500);

  // Append helper that respects the per-agent cap.
  const append = (agentId: string, t: AgentThought) => {
    setState(prev => {
      const list = (prev.byAgent[agentId] || []).concat(t);
      const trimmed = list.length > MAX_PER_AGENT ? list.slice(list.length - MAX_PER_AGENT) : list;
      return { ...prev, byAgent: { ...prev.byAgent, [agentId]: trimmed } };
    });
  };

  const markStarted = (agentId: string) => {
    setState(prev => {
      if (prev.startedAgents.has(agentId)) return prev;
      const next = new Set(prev.startedAgents);
      next.add(agentId);
      return { ...prev, startedAgents: next };
    });
  };

  useEffect(() => {
    let cancelled = false;
    let reconnectTimer: number | undefined;

    const connect = () => {
      try {
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
          backoffRef.current = 500;
          setState(prev => ({ ...prev, connected: true }));
        };

        ws.onmessage = (evt) => {
          try {
            const env = JSON.parse(evt.data);
            // Backend wraps every event as {type, data, timestamp}
            if (env.type === 'agent_thought' && env.data?.agent_id) {
              append(env.data.agent_id, env.data as AgentThought);
            } else if (env.type === 'agent_started' && env.data?.agent_id) {
              // Synthesise a "task started" pseudo-thought so the panel header
              // shows the kickoff event in the chat history. Also mark the
              // agent as started so the panel auto-opens (we can't rely on
              // polled agent.status — Haiku agents finish in <1s).
              markStarted(env.data.agent_id);
              append(env.data.agent_id, {
                agent_id: env.data.agent_id,
                kind: 'message_received',
                content: env.data.task_description
                  ? `▸ Started task: ${env.data.task_description}`
                  : '▸ Task started',
                timestamp: Date.now() / 1000,
              });
            }
          } catch { /* ignore malformed */ }
        };

        ws.onerror = () => { /* swallow — onclose fires next */ };

        ws.onclose = () => {
          setState(prev => ({ ...prev, connected: false }));
          if (cancelled) return;
          // Exponential backoff up to ~10s
          const wait = Math.min(backoffRef.current, 10_000);
          backoffRef.current = Math.min(backoffRef.current * 2, 10_000);
          reconnectTimer = window.setTimeout(connect, wait);
        };
      } catch {
        if (cancelled) return;
        reconnectTimer = window.setTimeout(connect, 2_000);
      }
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      try { wsRef.current?.close(); } catch { /* ignore */ }
    };
  }, []);

  return state;
}

/** Replay an agent's recent thought backlog from the REST endpoint.
 *  Useful when a chat panel opens AFTER messages have already been emitted. */
export async function replayAgentThoughts(agentId: string): Promise<AgentThought[]> {
  try {
    return await api.getAgentThoughts(agentId);
  } catch {
    return [];
  }
}
