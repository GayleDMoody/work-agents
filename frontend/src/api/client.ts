import type { Pipeline, Agent, DashboardData, ServiceSettings } from '../types';

const BASE_URL = 'http://localhost:8000/api';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  getDashboard: () => fetchJSON<DashboardData>('/dashboard'),

  getPipelines: () => fetchJSON<Pipeline[]>('/pipelines'),

  getPipeline: (id: string) => fetchJSON<Pipeline>(`/pipelines/${id}`),

  triggerPipeline: (ticketKey: string, repo?: { kind: 'local' | 'github'; id: string }) =>
    fetchJSON<Pipeline>('/pipelines/trigger', {
      method: 'POST',
      body: JSON.stringify({
        ticket_key: ticketKey,
        ...(repo ? { repo_kind: repo.kind, repo_id: repo.id } : {}),
      }),
    }),

  getAgents: () => fetchJSON<Agent[]>('/agents'),

  getAgent: (id: string) => fetchJSON<Agent>(`/agents/${id}`),

  getSettings: () => fetchJSON<ServiceSettings>('/settings'),

  updateSettings: (service: string, config: Record<string, string>) =>
    fetchJSON<{ status: string }>('/settings', {
      method: 'POST',
      body: JSON.stringify({ service, config }),
    }),

  testConnection: (service: string) =>
    fetchJSON<{ success: boolean; message: string }>('/settings/test', {
      method: 'POST',
      body: JSON.stringify({ service }),
    }),

  health: () => fetchJSON<{ status: string; version: string }>('/health'),

  // App Config
  getAppConfig: () => fetchJSON<Record<string, unknown>>('/config'),

  saveAppConfig: (config: Record<string, unknown>) =>
    fetchJSON<{ status: string }>('/config', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  resetAppConfig: () =>
    fetchJSON<{ status: string }>('/config/reset', { method: 'POST' }),

  // Chat
  sendMessage: (agentId: string, message: string) =>
    fetchJSON<{ agent_id: string; response: string; timestamp: string }>(`/agents/${agentId}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),

  getChatHistory: (agentId: string) =>
    fetchJSON<{ role: string; content: string; timestamp: string }[]>(`/agents/${agentId}/chat`),

  clearChat: (agentId: string) =>
    fetchJSON<{ status: string }>(`/agents/${agentId}/chat`, { method: 'DELETE' }),

  // Jira OAuth
  jiraOAuthStatus: () =>
    fetchJSON<{ connected: boolean; site_url?: string; cloud_id?: string; expires_in_seconds?: number }>(
      '/jira/oauth/status',
    ),

  jiraOAuthStartUrl: () => `${BASE_URL}/jira/oauth/redirect`,

  jiraOAuthDisconnect: () =>
    fetchJSON<{ status: string }>('/jira/oauth/disconnect', { method: 'POST' }),

  jiraFetchTicket: (ticketKey: string) =>
    fetchJSON<{ source: string; ticket?: Record<string, unknown>; error?: string }>(
      `/jira/ticket/${encodeURIComponent(ticketKey)}`,
    ),

  // GitHub OAuth — same shape as Jira
  githubOAuthStatus: () =>
    fetchJSON<{ connected: boolean; user_login?: string; user_avatar?: string; scope?: string }>(
      '/github/oauth/status',
    ),

  githubOAuthStartUrl: () => `${BASE_URL}/github/oauth/redirect`,

  githubOAuthDisconnect: () =>
    fetchJSON<{ status: string }>('/github/oauth/disconnect', { method: 'POST' }),

  // Agent live-thought feed
  getAgentThoughts: (agentId: string) =>
    fetchJSON<AgentThought[]>(`/agents/${encodeURIComponent(agentId)}/thoughts`),

  // Local + GitHub repo discovery for the trigger flow
  listLocalRepos: (root: string = '') =>
    fetchJSON<{ root: string; repos: LocalRepoSummary[] }>(
      `/local-repos${root ? `?root=${encodeURIComponent(root)}` : ''}`,
    ),

  listGitHubRepos: () =>
    fetchJSON<GitHubRepoSummary[]>('/github/repos'),

  publishPRLocal: (runId: string, body: {
    repo_path: string;
    base_branch?: string;
    branch?: string;
    pr_title?: string;
    pr_body?: string;
    push?: boolean;
  }) =>
    fetchJSON<{
      branch: string;
      commit_sha: string;
      files_changed: string[];
      pushed: boolean;
      url?: string;
      number?: number;
      warning?: string;
    }>(`/pipelines/${encodeURIComponent(runId)}/publish-pr-local`, {
      method: 'POST',
      body: JSON.stringify({ run_id: runId, ...body }),
    }),

  // Notes board
  listNotes: (ticketKey?: string) =>
    fetchJSON<Note[]>(`/notes${ticketKey ? `?ticket_key=${encodeURIComponent(ticketKey)}` : ''}`),

  getNote: (id: string) =>
    fetchJSON<Note>(`/notes/${encodeURIComponent(id)}`),

  addNote: (body: { author?: string; title: string; body?: string; tags?: string[]; ticket_key?: string; pipeline_run_id?: string }) =>
    fetchJSON<Note>('/notes', { method: 'POST', body: JSON.stringify(body) }),

  addNoteComment: (id: string, body: { author?: string; body: string }) =>
    fetchJSON<NoteComment>(`/notes/${encodeURIComponent(id)}/comments`, { method: 'POST', body: JSON.stringify(body) }),

  deleteNote: (id: string) =>
    fetchJSON<{ status: string }>(`/notes/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};

export interface NoteComment {
  id: string;
  author: string;
  body: string;
  created_at: number;
}

export interface Note {
  id: string;
  author: string;       // agent_id or "user"
  title: string;
  body: string;
  tags: string[];
  ticket_key: string;
  pipeline_run_id: string;
  created_at: number;
  comments: NoteComment[];
}

/** Live thought event emitted by agents during a pipeline run. */
export interface AgentThought {
  agent_id: string;
  /** prompt, response, error, message_sent, message_received */
  kind: 'prompt' | 'response' | 'error' | 'message_sent' | 'message_received';
  content: string;
  timestamp: number;
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
  duration_seconds?: number;
}

/** WebSocket URL for live pipeline events (agent_thought, agent_started, etc.). */
export const WS_URL = BASE_URL.replace(/^http/, 'ws').replace(/\/api$/, '/ws');

export interface LocalRepoSummary {
  name: string;
  path: string;
  branch: string;
  remote: string;
  last_commit: string;
  github_owner_repo: string;
}

export interface GitHubRepoSummary {
  full_name: string;
  description: string;
  default_branch: string;
  private: boolean;
  language: string;
  updated_at: string;
  stargazers_count: number;
}
