import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Clock, DollarSign, FileText, MessageSquare } from 'lucide-react';
import { api } from '../api/client';
import type { Pipeline } from '../types';

const MOCK: Pipeline = {
  id: 'def456', ticket_key: 'PROJ-102', status: 'running', current_phase: 'testing',
  phases: [
    { name: 'intake', status: 'completed', started_at: '2026-04-14T11:00:00Z', completed_at: '2026-04-14T11:00:02Z' },
    { name: 'classification', status: 'completed', started_at: '2026-04-14T11:00:02Z', completed_at: '2026-04-14T11:00:08Z' },
    { name: 'planning', status: 'completed', started_at: '2026-04-14T11:00:08Z', completed_at: '2026-04-14T11:00:30Z' },
    { name: 'architecture', status: 'completed', started_at: '2026-04-14T11:00:30Z', completed_at: '2026-04-14T11:01:15Z' },
    { name: 'execution', status: 'completed', started_at: '2026-04-14T11:01:15Z', completed_at: '2026-04-14T11:05:00Z' },
    { name: 'testing', status: 'running', started_at: '2026-04-14T11:05:00Z' },
    { name: 'review', status: 'pending' },
  ],
  agents_used: ['product', 'pm', 'architect', 'frontend', 'backend', 'qa'],
  artifacts: [
    { id: '1', artifact_type: 'document', name: 'requirements_analysis_PROJ-102', content: '...', agent_id: 'product', phase: 'planning', created_at: '2026-04-14T11:00:20Z', metadata: {} },
    { id: '2', artifact_type: 'plan', name: 'execution_plan_PROJ-102', content: '...', agent_id: 'pm', phase: 'planning', created_at: '2026-04-14T11:00:28Z', metadata: {} },
    { id: '3', artifact_type: 'architecture', name: 'architecture_PROJ-102', content: '...', agent_id: 'architect', phase: 'architecture', created_at: '2026-04-14T11:01:10Z', metadata: {} },
    { id: '4', artifact_type: 'code', name: 'src/components/Profile.tsx', content: '...', file_path: 'src/components/Profile.tsx', agent_id: 'frontend', phase: 'execution', created_at: '2026-04-14T11:03:00Z', metadata: {} },
    { id: '5', artifact_type: 'code', name: 'src/api/profile.py', content: '...', file_path: 'src/api/profile.py', agent_id: 'backend', phase: 'execution', created_at: '2026-04-14T11:04:30Z', metadata: {} },
  ],
  events: [
    { type: 'pipeline_started', timestamp: '2026-04-14T11:00:00Z', message: 'Pipeline started for PROJ-102' },
    { type: 'agent_started', timestamp: '2026-04-14T11:00:02Z', message: 'Product Agent analyzing ticket', agent_id: 'product' },
    { type: 'agent_finished', timestamp: '2026-04-14T11:00:20Z', message: 'Product Agent completed: 5 acceptance criteria', agent_id: 'product' },
    { type: 'agent_started', timestamp: '2026-04-14T11:00:20Z', message: 'PM Agent creating execution plan', agent_id: 'pm' },
    { type: 'agent_finished', timestamp: '2026-04-14T11:00:28Z', message: 'PM Agent completed: 6 steps planned', agent_id: 'pm' },
    { type: 'agent_started', timestamp: '2026-04-14T11:00:30Z', message: 'Architect Agent designing solution', agent_id: 'architect' },
    { type: 'feedback_loop', timestamp: '2026-04-14T11:05:30Z', message: 'QA found 2 test failures, sending feedback to backend agent' },
  ],
  total_cost: 4.12, total_tokens: 298000,
  created_at: '2026-04-14T11:00:00Z', updated_at: '2026-04-14T11:08:00Z',
  duration_seconds: 480, feedback_loops: 1, approvals: [],
};

const artifactIcon: Record<string, string> = {
  document: '📄', code: '💻', test: '🧪', config: '⚙️', review: '👀', plan: '📋', architecture: '🏗️',
};

export default function PipelineDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: pipeline } = useQuery({
    queryKey: ['pipeline', id],
    queryFn: () => api.getPipeline(id!),
    placeholderData: MOCK,
    enabled: !!id,
  });

  const p = pipeline ?? MOCK;

  return (
    <>
      <Link to="/pipelines" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 16, fontSize: 14, color: 'var(--text-secondary)' }}>
        <ArrowLeft size={14} /> Back to Pipelines
      </Link>

      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>{p.ticket_key}</h2>
          <p>Pipeline run {p.id}</p>
        </div>
        <span className={`badge ${p.status}`} style={{ fontSize: 14, padding: '4px 14px' }}>{p.status}</span>
      </div>

      {/* Phase timeline */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title" style={{ marginBottom: 12 }}>Phase Progress</div>
        <div className="phase-timeline" style={{ height: 10, gap: 6 }}>
          {p.phases.map(phase => (
            <div key={phase.name} className={`phase-step ${phase.status}`} title={`${phase.name}: ${phase.status}`} style={{ height: 10, borderRadius: 5 }} />
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
          {p.phases.map(phase => (
            <span key={phase.name} style={{ fontSize: 11, color: 'var(--text-muted)', flex: 1, textAlign: 'center' }}>{phase.name}</span>
          ))}
        </div>
      </div>

      <div className="grid-2" style={{ marginBottom: 20 }}>
        {/* Stats */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 16 }}>Summary</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <div className="stat-label"><DollarSign size={12} style={{ verticalAlign: 'middle' }} /> Cost</div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>${p.total_cost.toFixed(2)}</div>
            </div>
            <div>
              <div className="stat-label">Tokens</div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>{(p.total_tokens / 1000).toFixed(0)}k</div>
            </div>
            <div>
              <div className="stat-label"><Clock size={12} style={{ verticalAlign: 'middle' }} /> Duration</div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>{Math.round(p.duration_seconds)}s</div>
            </div>
            <div>
              <div className="stat-label">Feedback Loops</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: p.feedback_loops > 0 ? 'var(--warning)' : 'var(--text-primary)' }}>{p.feedback_loops}</div>
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <div className="stat-label" style={{ marginBottom: 8 }}>Agents Used</div>
            <div className="agent-chips">
              {p.agents_used.map(a => <span key={a} className={`agent-chip ${a}`}>{a}</span>)}
            </div>
          </div>
        </div>

        {/* Artifacts */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}><FileText size={14} style={{ verticalAlign: 'middle' }} /> Artifacts ({p.artifacts.length})</div>
          <div style={{ maxHeight: 280, overflowY: 'auto' }}>
            {p.artifacts.map(a => (
              <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                <span>{artifactIcon[a.artifact_type] || '📎'}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{a.artifact_type} · {a.agent_id}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Event log */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 12 }}><MessageSquare size={14} style={{ verticalAlign: 'middle' }} /> Event Log</div>
        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          {p.events.map((evt, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap', minWidth: 70 }}>
                {new Date(evt.timestamp).toLocaleTimeString()}
              </span>
              {evt.agent_id && <span className={`agent-chip ${evt.agent_id}`}>{evt.agent_id}</span>}
              <span style={{ fontSize: 13 }}>{evt.message}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
