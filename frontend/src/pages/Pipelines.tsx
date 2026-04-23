import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { GitBranch } from 'lucide-react';
import { api } from '../api/client';
import type { Pipeline } from '../types';

const MOCK_PIPELINES: Pipeline[] = [
  { id: 'abc123', ticket_key: 'PROJ-101', status: 'completed', current_phase: 'complete', phases: [{ name: 'intake', status: 'completed' }, { name: 'classification', status: 'completed' }, { name: 'planning', status: 'completed' }, { name: 'execution', status: 'completed' }, { name: 'testing', status: 'completed' }, { name: 'review', status: 'completed' }, { name: 'complete', status: 'completed' }], agents_used: ['product', 'pm', 'backend', 'qa', 'code_review'], artifacts: [], events: [], total_cost: 2.34, total_tokens: 156000, created_at: '2026-04-14T10:00:00Z', updated_at: '2026-04-14T10:05:00Z', duration_seconds: 312, feedback_loops: 0, approvals: [] },
  { id: 'def456', ticket_key: 'PROJ-102', status: 'running', current_phase: 'testing', phases: [{ name: 'intake', status: 'completed' }, { name: 'classification', status: 'completed' }, { name: 'planning', status: 'completed' }, { name: 'architecture', status: 'completed' }, { name: 'execution', status: 'completed' }, { name: 'testing', status: 'running' }, { name: 'review', status: 'pending' }], agents_used: ['product', 'pm', 'architect', 'frontend', 'backend', 'qa'], artifacts: [], events: [], total_cost: 4.12, total_tokens: 298000, created_at: '2026-04-14T11:00:00Z', updated_at: '2026-04-14T11:08:00Z', duration_seconds: 480, feedback_loops: 1, approvals: [] },
  { id: 'ghi789', ticket_key: 'PROJ-103', status: 'failed', current_phase: 'execution', phases: [{ name: 'intake', status: 'completed' }, { name: 'classification', status: 'completed' }, { name: 'planning', status: 'completed' }, { name: 'execution', status: 'failed' }], agents_used: ['product', 'pm', 'backend'], artifacts: [], events: [], total_cost: 0.89, total_tokens: 62000, created_at: '2026-04-14T09:00:00Z', updated_at: '2026-04-14T09:02:00Z', duration_seconds: 120, feedback_loops: 0, approvals: [] },
];

export default function Pipelines() {
  const { data: pipelines } = useQuery({
    queryKey: ['pipelines'],
    queryFn: api.getPipelines,
    placeholderData: MOCK_PIPELINES,
  });

  const list = pipelines ?? MOCK_PIPELINES;

  return (
    <>
      <div className="page-header">
        <h2>Pipeline Runs</h2>
        <p>All ticket processing pipeline executions</p>
      </div>

      {list.length === 0 ? (
        <div className="empty-state">
          <GitBranch size={48} />
          <h3>No pipeline runs yet</h3>
          <p>Trigger a pipeline from the Dashboard to get started.</p>
        </div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Status</th>
                <th>Phases</th>
                <th>Agents</th>
                <th>Cost</th>
                <th>Tokens</th>
                <th>Duration</th>
                <th>Loops</th>
              </tr>
            </thead>
            <tbody>
              {list.map(run => (
                <tr key={run.id}>
                  <td><Link to={`/pipelines/${run.id}`} style={{ fontWeight: 600 }}>{run.ticket_key}</Link></td>
                  <td><span className={`badge ${run.status}`}>{run.status}</span></td>
                  <td>
                    <div className="phase-timeline" style={{ minWidth: 120 }}>
                      {run.phases.map(p => (
                        <div key={p.name} className={`phase-step ${p.status}`} title={`${p.name}: ${p.status}`} />
                      ))}
                    </div>
                  </td>
                  <td>
                    <div className="agent-chips">
                      {run.agents_used.map(a => (
                        <span key={a} className={`agent-chip ${a}`}>{a}</span>
                      ))}
                    </div>
                  </td>
                  <td>${run.total_cost.toFixed(2)}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{(run.total_tokens / 1000).toFixed(0)}k</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{Math.round(run.duration_seconds)}s</td>
                  <td>{run.feedback_loops > 0 ? <span style={{ color: 'var(--warning)' }}>{run.feedback_loops}</span> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
