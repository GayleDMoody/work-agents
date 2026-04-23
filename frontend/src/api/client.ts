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

  triggerPipeline: (ticketKey: string) =>
    fetchJSON<Pipeline>('/pipelines/trigger', {
      method: 'POST',
      body: JSON.stringify({ ticket_key: ticketKey }),
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
};
