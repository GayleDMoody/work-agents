import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import IsometricOffice from '../components/IsometricOffice';
import HUD from '../components/HUD';
import ChatPopup from '../components/ChatPopup';
import LiveAgentPanels from '../components/LiveAgentPanels';
import ArtifactViewer from '../components/ArtifactViewer';
import { Code as CodeIcon } from 'lucide-react';
import { api } from '../api/client';
import type { DashboardData, Agent } from '../types';

/**
 * Static topology skeleton — the 8 agents that make up the pipeline.
 * The dashboard always renders this layout; live status/metrics from the API
 * are merged over the top. This means the office view stays meaningful even
 * if the backend is slow, offline, or hasn't run any pipelines yet.
 */
const AGENT_SKELETON: Agent[] = [
  { id: 'product',     name: 'Product',   role: 'Analyst',    description: '', status: 'idle', total_runs: 0, successful_runs: 0, total_cost: 0, capabilities: [], model: '' },
  { id: 'pm',          name: 'PM',        role: 'Manager',    description: '', status: 'idle', total_runs: 0, successful_runs: 0, total_cost: 0, capabilities: [], model: '' },
  { id: 'architect',   name: 'Architect', role: 'Architect',  description: '', status: 'idle', total_runs: 0, successful_runs: 0, total_cost: 0, capabilities: [], model: '' },
  { id: 'frontend',    name: 'Frontend',  role: 'Developer',  description: '', status: 'idle', total_runs: 0, successful_runs: 0, total_cost: 0, capabilities: [], model: '' },
  { id: 'backend',     name: 'Backend',   role: 'Developer',  description: '', status: 'idle', total_runs: 0, successful_runs: 0, total_cost: 0, capabilities: [], model: '' },
  { id: 'qa',          name: 'QA',        role: 'Engineer',   description: '', status: 'idle', total_runs: 0, successful_runs: 0, total_cost: 0, capabilities: [], model: '' },
  { id: 'devops',      name: 'DevOps',    role: 'Engineer',   description: '', status: 'idle', total_runs: 0, successful_runs: 0, total_cost: 0, capabilities: [], model: '' },
  { id: 'code_review', name: 'Reviewer',  role: 'Senior Eng', description: '', status: 'idle', total_runs: 0, successful_runs: 0, total_cost: 0, capabilities: [], model: '' },
];

const EMPTY_DASHBOARD: DashboardData = {
  active_pipelines: 0,
  completed_pipelines: 0,
  failed_pipelines: 0,
  total_pipelines: 0,
  busy_agents: 0,
  idle_agents: AGENT_SKELETON.length,
  total_cost: 0,
  total_tokens: 0,
  recent_runs: [],
  services: {},
};

/** Overlay live agent data onto the skeleton, preserving the pipeline order. */
function mergeAgents(live: Agent[] | undefined): Agent[] {
  if (!live || live.length === 0) return AGENT_SKELETON;
  const liveMap = new Map(live.map(a => [a.id, a]));
  return AGENT_SKELETON.map(skel => {
    const fresh = liveMap.get(skel.id);
    return fresh ? { ...skel, ...fresh } : skel;
  });
}

export default function Dashboard() {
  const [chatAgent, setChatAgent] = useState<string | null>(null);
  const [viewerPipelineId, setViewerPipelineId] = useState<string | null>(null);

  // Poll both endpoints every 3s so busy/idle status + recent runs stay current.
  const { data: dashboard } = useQuery({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    refetchInterval: 3000,
    placeholderData: EMPTY_DASHBOARD,
  });

  const { data: agentsLive } = useQuery({
    queryKey: ['agents'],
    queryFn: api.getAgents,
    refetchInterval: 3000,
  });

  const agents = mergeAgents(agentsLive);
  const dash = dashboard ?? EMPTY_DASHBOARD;

  async function handleTrigger(ticketKey: string) {
    if (!ticketKey.trim()) return;
    try {
      await api.triggerPipeline(ticketKey.trim());
    } catch (err) {
      console.error('Failed to trigger pipeline:', err);
    }
  }

  // Pick the most-recent run that produced any artifacts for the "View output"
  // shortcut button. Demo viewer button is suppressed when there's nothing to show.
  const latestRunWithArtifacts = (dash.recent_runs || []).find(
    r => Array.isArray(r.artifacts) && r.artifacts.length > 0,
  );
  const viewerPipeline = viewerPipelineId
    ? (dash.recent_runs || []).find(r => r.id === viewerPipelineId)
    : undefined;

  return (
    <div className="office-dashboard">
      <IsometricOffice agents={agents} onAgentClick={(id) => setChatAgent(id)} />
      <HUD data={dash} onTrigger={handleTrigger} />
      {/* Live thought panels — auto-open per busy agent showing real-time
          Claude prompts/responses + inter-agent messages. */}
      <LiveAgentPanels agents={agents} />
      {/* Quick "view artifacts" button — appears only when at least one
          recent run has artifacts to show. */}
      {latestRunWithArtifacts && (
        <button
          type="button"
          className="dashboard-view-artifacts"
          onClick={() => setViewerPipelineId(latestRunWithArtifacts.id)}
          title="Open the artifact / code viewer for the latest pipeline run"
        >
          <CodeIcon size={14} />
          View output ({latestRunWithArtifacts.ticket_key})
        </button>
      )}
      {chatAgent && (
        <ChatPopup agentId={chatAgent} onClose={() => setChatAgent(null)} />
      )}
      {viewerPipeline && (
        <ArtifactViewer
          pipeline={viewerPipeline}
          onClose={() => setViewerPipelineId(null)}
        />
      )}
    </div>
  );
}
