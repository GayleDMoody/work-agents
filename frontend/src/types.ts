export interface Pipeline {
  id: string;
  ticket_key: string;
  status: 'running' | 'completed' | 'failed' | 'pending';
  current_phase: string;
  phases: Phase[];
  agents_used: string[];
  artifacts: Artifact[];
  events: PipelineEvent[];
  total_cost: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
  duration_seconds: number;
  feedback_loops: number;
  approvals: Approval[];
}

export interface Phase {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  started_at?: string;
  completed_at?: string;
  agent_id?: string;
}

export interface Artifact {
  id: string;
  artifact_type: string;
  name: string;
  content: string;
  file_path?: string;
  agent_id: string;
  phase: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface PipelineEvent {
  type: string;
  timestamp: string;
  message: string;
  agent_id?: string;
}

export interface Approval {
  gate: string;
  status: 'pending' | 'approved' | 'rejected';
  reviewer?: string;
  feedback?: string;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  description: string;
  status: 'idle' | 'busy' | 'error';
  total_runs: number;
  successful_runs: number;
  total_cost: number;
  capabilities: string[];
  model: string;
  /** Short description of what the agent is currently working on,
   *  populated by the orchestrator on agent_started. Empty when idle. */
  current_task?: string;
}

export interface DashboardData {
  active_pipelines: number;
  completed_pipelines: number;
  failed_pipelines: number;
  total_pipelines: number;
  busy_agents: number;
  idle_agents: number;
  total_cost: number;
  total_tokens: number;
  recent_runs: Pipeline[];
  services: Record<string, { connected: boolean }>;
}

export interface ServiceSettings {
  jira: {
    connected: boolean;
    server_url: string;
    email: string;
    api_token: string;
  };
  github: {
    connected: boolean;
    token: string;
    repo: string;
  };
  anthropic: {
    connected: boolean;
    api_key: string;
    model: string;
  };
}

export interface WSMessage {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}
