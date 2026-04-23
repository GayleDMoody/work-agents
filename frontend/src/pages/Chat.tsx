import { useState } from 'react';
import { MessageSquare } from 'lucide-react';
import AgentChat from '../components/AgentChat';

const CHAT_AGENTS = [
  { id: 'product', name: 'Product', role: 'Product Analyst', color: '#bc8cff' },
  { id: 'pm', name: 'PM', role: 'Project Manager', color: '#58a6ff' },
  { id: 'architect', name: 'Architect', role: 'Software Architect', color: '#f0883e' },
  { id: 'frontend', name: 'Frontend', role: 'Frontend Developer', color: '#3fb950' },
  { id: 'backend', name: 'Backend', role: 'Backend Developer', color: '#d29922' },
  { id: 'qa', name: 'QA', role: 'QA Engineer', color: '#f85149' },
  { id: 'devops', name: 'DevOps', role: 'DevOps Engineer', color: '#56d4dd' },
  { id: 'code_review', name: 'Reviewer', role: 'Code Reviewer', color: '#a371f7' },
];

export default function Chat() {
  const [selected, setSelected] = useState(CHAT_AGENTS[0]);

  return (
    <div className="chat-page">
      {/* Agent list sidebar */}
      <div className="chat-sidebar">
        <div className="chat-sidebar-header">
          <MessageSquare size={16} />
          <span>Agent Chat</span>
        </div>
        <div className="chat-agent-list">
          {CHAT_AGENTS.map(agent => (
            <button
              key={agent.id}
              className={`chat-agent-item ${selected.id === agent.id ? 'active' : ''}`}
              onClick={() => setSelected(agent)}
            >
              <div className="chat-agent-dot" style={{ background: agent.color }} />
              <div className="chat-agent-item-info">
                <div className="chat-agent-item-name">{agent.name}</div>
                <div className="chat-agent-item-role">{agent.role}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="chat-main">
        <AgentChat
          key={selected.id}
          agentId={selected.id}
          agentName={selected.name}
          agentRole={selected.role}
          color={selected.color}
        />
      </div>
    </div>
  );
}
