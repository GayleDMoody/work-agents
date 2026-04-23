import type { Agent } from '../types';

const AGENT_VISUALS: Record<string, { color: string; label: string; busyText: string; icon: string }> = {
  product:     { color: '#bc8cff', label: 'Product',   busyText: 'Analyzing requirements...', icon: '📋' },
  pm:          { color: '#58a6ff', label: 'PM',        busyText: 'Planning execution...',      icon: '📊' },
  architect:   { color: '#f0883e', label: 'Architect', busyText: 'Designing architecture...',  icon: '🏗️' },
  frontend:    { color: '#3fb950', label: 'Frontend',  busyText: 'Writing components...',      icon: '🎨' },
  backend:     { color: '#d29922', label: 'Backend',   busyText: 'Building endpoints...',      icon: '⚙️' },
  qa:          { color: '#f85149', label: 'QA',        busyText: 'Writing tests...',           icon: '🧪' },
  devops:      { color: '#56d4dd', label: 'DevOps',    busyText: 'Configuring CI/CD...',       icon: '🚀' },
  code_review: { color: '#a371f7', label: 'Reviewer',  busyText: 'Reviewing code...',          icon: '👁️' },
};

/**
 * All positions are defined in SVG coordinate space (SVG_W × SVG_H).
 * HTML node positions are derived as percentages from those same coordinates,
 * so nodes stay perfectly aligned with connection lines at every viewport size.
 *
 * Pipeline topology:
 *
 *           [Product]          x=500  (center)
 *               ↓
 *             [PM]             x=500
 *               ↓
 *          [Architect]         x=500
 *         ↙    ↓    ↘
 * [Frontend] [Backend] [DevOps]   x=175, 500, 825 (symmetric)
 *         ↘   ↙
 *          [QA]                x=337 (midpoint of Frontend + Backend)
 *            ↓
 *       [Code Review]          x=337
 */
const SVG_W = 1000;
const SVG_H = 760;

// Each consecutive vertically-stacked pair needs ≥ ~120 SVG units between centers
// so the upper node's label + margin don't cover the connection line.
const SVG_NODES: { id: string; x: number; y: number }[] = [
  { id: 'product',     x: 500, y: 45  },
  { id: 'pm',          x: 500, y: 175 },   // 130-unit gap from product
  { id: 'architect',   x: 500, y: 325 },   // 150-unit gap from pm (extra clearance for speech bubble)
  { id: 'frontend',    x: 175, y: 455 },   // 130-unit gap from architect
  { id: 'backend',     x: 500, y: 455 },
  { id: 'devops',      x: 825, y: 455 },
  { id: 'qa',          x: 337, y: 575 },   // midpoint x of frontend(175) + backend(500) = 337
  { id: 'code_review', x: 337, y: 690 },   // 115-unit gap from qa
];

const STAGE_LABELS: { label: string; y: number }[] = [
  { label: 'INTAKE',  y: 45  },
  { label: 'PLAN',    y: 175 },
  { label: 'DESIGN',  y: 325 },
  { label: 'BUILD',   y: 455 },
  { label: 'TEST',    y: 575 },
  { label: 'REVIEW',  y: 690 },
];

const CONNECTIONS: [string, string][] = [
  ['product',   'pm'],
  ['pm',        'architect'],
  ['architect', 'frontend'],
  ['architect', 'backend'],
  ['architect', 'devops'],
  ['frontend',  'qa'],
  ['backend',   'qa'],
  ['qa',        'code_review'],
];

interface Props {
  agents: Agent[];
  onAgentClick?: (agentId: string) => void;
}

export default function IsometricOffice({ agents, onAgentClick }: Props) {
  const agentMap = new Map(agents.map(a => [a.id, a]));
  const posMap = Object.fromEntries(SVG_NODES.map(n => [n.id, { x: n.x, y: n.y }]));

  return (
    <div className="hex-office-viewport">
      {/* Ambient background particles — deterministic positions to avoid re-render flicker */}
      <div className="hex-bg-particles" aria-hidden="true">
        {Array.from({ length: 20 }).map((_, i) => (
          <div
            key={i}
            className="hex-particle"
            style={{
              left:              `${(i * 37 + 11) % 100}%`,
              top:               `${(i * 53 + 7) % 100}%`,
              animationDelay:    `${(i * 0.71) % 8}s`,
              animationDuration: `${6 + (i % 6)}s`,
              width:             `${2 + (i % 3)}px`,
              height:            `${2 + (i % 3)}px`,
              opacity:           0.12 + (i % 5) * 0.03,
            }}
          />
        ))}
      </div>

      {/*
        SVG layer — connection lines + stage labels.
        Uses preserveAspectRatio="none" so it exactly fills the container,
        matching the percentage-based HTML node positions derived below.
      */}
      <svg
        className="hex-connections"
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <filter id="conn-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Stage labels — SVG user units for consistent scaling */}
        {STAGE_LABELS.map(({ label, y }) => (
          <text
            key={label}
            x={870}
            y={y}
            fontSize="20"
            fontWeight="800"
            letterSpacing="3"
            fill="rgba(88,166,255,.15)"
            dominantBaseline="middle"
            style={{ userSelect: 'none', fontFamily: 'inherit' }}
          >
            {label}
          </text>
        ))}

        {/*
          Connection lines — drawn center-to-center. Each node's opaque body
          sits on top of the SVG (z-index 10 vs the SVG's default) and naturally
          hides the line segments that would otherwise run through it, so the
          visible line terminates exactly at the body edge at every viewport size.
        */}
        {CONNECTIONS.map(([from, to], i) => {
          const a = posMap[from];
          const b = posMap[to];
          if (!a || !b) return null;
          const fromAgent = agentMap.get(from);
          const toAgent   = agentMap.get(to);
          const isActive  = fromAgent?.status === 'busy' || toAgent?.status === 'busy';

          return (
            <g key={i}>
              <line
                x1={a.x} y1={a.y}
                x2={b.x} y2={b.y}
                vectorEffect="non-scaling-stroke"
                className={`hex-conn-line${isActive ? ' hex-conn-active' : ''}`}
              />
              {isActive && (
                <circle r="6" className="hex-conn-dot">
                  <animateMotion
                    dur="2s"
                    repeatCount="indefinite"
                    path={`M${a.x},${a.y} L${b.x},${b.y}`}
                  />
                </circle>
              )}
            </g>
          );
        })}
      </svg>

      {/*
        HTML overlay — agent nodes.
        left/top are percentages derived from SVG coordinates,
        so they stay in sync with the connection lines above.
      */}
      {SVG_NODES.map(({ id, x, y }) => {
        const agent = agentMap.get(id);
        const vis   = AGENT_VISUALS[id];
        if (!vis) return null;
        const status   = agent?.status ?? 'idle';
        const isCenter = id === 'pm';

        return (
          <div
            key={id}
            className={`hex-node hex-node--${status}${isCenter ? ' hex-node--center' : ''}`}
            style={{
              left: `${(x / SVG_W) * 100}%`,
              top:  `${(y / SVG_H) * 100}%`,
              '--node-color': vis.color,
            } as React.CSSProperties}
            onClick={() => onAgentClick?.(id)}
            onKeyDown={e => e.key === 'Enter' && onAgentClick?.(id)}
            role="button"
            tabIndex={0}
            aria-label={`${vis.label} — ${status}`}
          >
            {/* Ambient glow behind body */}
            <div className="hex-node-glow" />

            {/* Main body */}
            <div className="hex-node-body">
              <div className="hex-node-icon">{vis.icon}</div>
              <div className={`hex-node-status hex-node-status--${status}`} />
            </div>

            {/* Label */}
            <div className="hex-node-label">
              <span className="hex-node-name" style={{ color: vis.color }}>{vis.label}</span>
              <span className="hex-node-role">{agent?.role ?? ''}</span>
            </div>

            {/* Speech bubble for busy agents */}
            {status === 'busy' && (
              <div className="hex-speech" style={{ borderColor: vis.color }}>
                {vis.busyText}
              </div>
            )}

            {/* Error badge */}
            {status === 'error' && (
              <div className="hex-error-badge">!</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
