import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Agent } from '../types';

const MOCK_AGENTS: Agent[] = [
  { id: 'product', name: 'Product Agent', role: 'Product Analyst', description: 'Analyzes requirements, writes acceptance criteria, identifies gaps', status: 'idle', total_runs: 18, successful_runs: 17, total_cost: 1.23, capabilities: ['requirements_analysis'], model: 'claude-sonnet-4-20250514' },
  { id: 'pm', name: 'PM Agent', role: 'Project Manager', description: 'Creates execution plans, assigns agents, tracks progress', status: 'idle', total_runs: 18, successful_runs: 18, total_cost: 0.98, capabilities: ['planning'], model: 'claude-sonnet-4-20250514' },
  { id: 'architect', name: 'Architect Agent', role: 'Software Architect', description: 'Designs technical solutions, defines interfaces and patterns', status: 'busy', total_runs: 8, successful_runs: 8, total_cost: 2.15, capabilities: ['architecture'], model: 'claude-sonnet-4-20250514' },
  { id: 'frontend', name: 'Frontend Agent', role: 'Frontend Developer', description: 'Writes React/TypeScript frontend code', status: 'busy', total_runs: 10, successful_runs: 9, total_cost: 3.45, capabilities: ['frontend_code'], model: 'claude-sonnet-4-20250514' },
  { id: 'backend', name: 'Backend Agent', role: 'Backend Developer', description: 'Writes Python backend code, APIs, services', status: 'busy', total_runs: 14, successful_runs: 13, total_cost: 4.12, capabilities: ['backend_code'], model: 'claude-sonnet-4-20250514' },
  { id: 'qa', name: 'QA Agent', role: 'QA Engineer', description: 'Writes test plans, automated tests, validates quality', status: 'idle', total_runs: 16, successful_runs: 14, total_cost: 2.67, capabilities: ['testing'], model: 'claude-sonnet-4-20250514' },
  { id: 'devops', name: 'DevOps Agent', role: 'DevOps Engineer', description: 'Handles CI/CD, deployment configs, infrastructure', status: 'idle', total_runs: 3, successful_runs: 3, total_cost: 0.34, capabilities: ['devops'], model: 'claude-sonnet-4-20250514' },
  { id: 'code_review', name: 'Code Review Agent', role: 'Senior Engineer', description: 'Reviews PRs for correctness, security, and quality', status: 'idle', total_runs: 15, successful_runs: 15, total_cost: 1.89, capabilities: ['code_review'], model: 'claude-sonnet-4-20250514' },
];

export default function Agents() {
  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: api.getAgents,
    placeholderData: MOCK_AGENTS,
  });

  const list = agents ?? MOCK_AGENTS;

  return (
    <>
      <div className="page-header">
        <h2>Agents</h2>
        <p>AI team members and their performance</p>
      </div>

      <div className="grid-4">
        {list.map(agent => {
          const successRate = agent.total_runs > 0 ? Math.round((agent.successful_runs / agent.total_runs) * 100) : 0;
          return (
            <div key={agent.id} className="agent-card">
              <div className="agent-header">
                <div>
                  <div className="agent-role">{agent.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{agent.role}</div>
                </div>
                <span className={`badge ${agent.status === 'busy' ? 'running' : agent.status === 'error' ? 'failed' : 'pending'}`}>
                  {agent.status}
                </span>
              </div>
              <div className="agent-desc">{agent.description}</div>
              <div className="agent-stats">
                <div>
                  <div className="agent-stat-label">Runs</div>
                  <div className="agent-stat-value">{agent.total_runs}</div>
                </div>
                <div>
                  <div className="agent-stat-label">Success</div>
                  <div className="agent-stat-value" style={{ color: successRate >= 90 ? 'var(--success)' : successRate >= 70 ? 'var(--warning)' : 'var(--danger)' }}>
                    {successRate}%
                  </div>
                </div>
                <div>
                  <div className="agent-stat-label">Cost</div>
                  <div className="agent-stat-value">${agent.total_cost.toFixed(2)}</div>
                </div>
              </div>
              <div style={{ marginTop: 12, display: 'flex', gap: 6 }}>
                {agent.capabilities.map(cap => (
                  <span key={cap} className={`agent-chip ${agent.id}`}>{cap}</span>
                ))}
              </div>
              <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
                Model: {agent.model.replace('claude-', '').replace('-20250514', '')}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
