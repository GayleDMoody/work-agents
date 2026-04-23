import { X, Maximize2, Minimize2 } from 'lucide-react';
import { useState } from 'react';
import AgentChat from './AgentChat';

const AGENT_META: Record<string, { name: string; role: string; color: string }> = {
  product:     { name: 'Product',   role: 'Product Analyst',     color: '#bc8cff' },
  pm:          { name: 'PM',        role: 'Project Manager',     color: '#58a6ff' },
  architect:   { name: 'Architect', role: 'Software Architect',  color: '#f0883e' },
  frontend:    { name: 'Frontend',  role: 'Frontend Developer',  color: '#3fb950' },
  backend:     { name: 'Backend',   role: 'Backend Developer',   color: '#d29922' },
  qa:          { name: 'QA',        role: 'QA Engineer',         color: '#f85149' },
  devops:      { name: 'DevOps',    role: 'DevOps Engineer',     color: '#56d4dd' },
  code_review: { name: 'Reviewer',  role: 'Code Reviewer',       color: '#a371f7' },
};

interface Props {
  agentId: string;
  onClose: () => void;
}

export default function ChatPopup({ agentId, onClose }: Props) {
  const [expanded, setExpanded] = useState(false);
  const meta = AGENT_META[agentId] || { name: agentId, role: 'Agent', color: '#888' };

  return (
    <div className={`chat-popup-overlay ${expanded ? 'chat-popup--expanded' : ''}`} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`chat-popup ${expanded ? 'chat-popup--big' : ''}`}>
        {/* Title bar */}
        <div className="chat-popup-titlebar" style={{ borderBottomColor: meta.color + '44' }}>
          <div className="chat-popup-title">
            <div className="chat-popup-dot" style={{ background: meta.color }} />
            <span style={{ color: meta.color, fontWeight: 700 }}>{meta.name}</span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{meta.role}</span>
          </div>
          <div className="chat-popup-actions">
            <button className="chat-popup-btn" onClick={() => setExpanded(!expanded)} title={expanded ? 'Minimize' : 'Expand'}>
              {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
            <button className="chat-popup-btn" onClick={onClose} title="Close">
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Chat body */}
        <div className="chat-popup-body">
          <AgentChat
            key={agentId}
            agentId={agentId}
            agentName={meta.name}
            agentRole={meta.role}
            color={meta.color}
          />
        </div>
      </div>
    </div>
  );
}
