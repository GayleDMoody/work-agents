import PixelCharacter from './PixelCharacter';

type AgentStatus = 'idle' | 'busy' | 'error';

interface Props {
  agentId: string;
  name: string;
  role: string;
  status: AgentStatus;
  color: string;
  hairColor?: string;
  taskText?: string;
  onClick?: () => void;
}

export default function AgentDesk({ agentId, name, role, status, color, hairColor, taskText, onClick }: Props) {
  const charState = status === 'busy' ? 'typing' : status === 'error' ? 'error' : 'idle';
  const statusColor = status === 'busy' ? 'var(--accent)' : status === 'error' ? 'var(--danger)' : 'var(--success)';

  return (
    <div
      className={`agent-desk-wrapper agent-desk--${status} ${onClick ? 'agent-desk--clickable' : ''}`}
      data-agent={agentId}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {/* Speech bubble */}
      {status === 'busy' && taskText && (
        <div className="speech-bubble">
          <span className="speech-text">{taskText}</span>
          <div className="speech-tail" />
        </div>
      )}

      {/* Error indicator */}
      {status === 'error' && (
        <div className="error-indicator">!</div>
      )}

      {/* Celebration particles */}
      <div className="particle-container">
        {status === 'idle' && (
          <>
            <div className="particle p1" style={{ '--pc': color } as React.CSSProperties} />
            <div className="particle p2" style={{ '--pc': color } as React.CSSProperties} />
            <div className="particle p3" style={{ '--pc': color } as React.CSSProperties} />
          </>
        )}
      </div>

      {/* Status light */}
      <div className="desk-status-light" style={{ background: statusColor, boxShadow: `0 0 8px ${statusColor}` }} />

      {/* Character */}
      <div className="desk-character">
        <PixelCharacter color={color} hairColor={hairColor} state={charState} />
      </div>

      {/* Desk surface (isometric) */}
      <div className="desk-surface">
        {/* Monitor */}
        <div className={`desk-monitor monitor--${status}`}>
          <div className="monitor-screen" />
          <div className="monitor-stand" />
        </div>
        {/* Keyboard */}
        <div className="desk-keyboard" />
      </div>

      {/* Chair */}
      <div className="desk-chair" />

      {/* Name plate */}
      <div className="desk-nameplate">
        <span className="nameplate-name" style={{ color }}>{name}</span>
        <span className="nameplate-role">{role}</span>
      </div>

      {/* Task card (small floating card when busy) */}
      {status === 'busy' && (
        <div className="desk-task-card" style={{ borderLeftColor: color }}>
          <div className="task-card-dot" style={{ background: color }} />
          <span>Working...</span>
        </div>
      )}
    </div>
  );
}
