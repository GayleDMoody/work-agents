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
 * Horizontal pipeline topology in a 2:1 SVG coordinate space.
 *
 * The container CSS locks a 2:1 aspect ratio so the SVG never distorts regardless
 * of viewport size. Everything scales together: lines, stage labels, and HTML
 * nodes (positioned via percentages derived from SVG coordinates).
 *
 *                     [Frontend]
 *                    ↗
 * [Product]→[PM]→[Architect]→[Backend]→[QA]→[Reviewer]
 *                    ↘
 *                     [DevOps]
 *
 *   INTAKE    PLAN    DESIGN    BUILD    TEST    REVIEW   ← column stage labels
 *
 * The main spine runs horizontally along y=250 (centre). Frontend sits above,
 * DevOps below — giving a layout that's symmetric about the horizontal axis
 * and about every column. Fits on short viewports without clipping.
 */
const SVG_W = 1000;
const SVG_H = 500;

const SVG_NODES: { id: string; x: number; y: number }[] = [
  { id: 'product',     x: 80,  y: 250 },
  { id: 'pm',          x: 240, y: 250 },
  { id: 'architect',   x: 400, y: 250 },
  { id: 'frontend',    x: 560, y: 130 },   // above the main spine
  { id: 'backend',     x: 560, y: 250 },   // on the main spine
  { id: 'devops',      x: 560, y: 370 },   // below the main spine, mirroring Frontend
  { id: 'qa',          x: 760, y: 250 },   // back on the spine
  { id: 'code_review', x: 920, y: 250 },
];

const STAGE_LABELS: { label: string; x: number }[] = [
  { label: 'INTAKE',  x: 80  },
  { label: 'PLAN',    x: 240 },
  { label: 'DESIGN',  x: 400 },
  { label: 'BUILD',   x: 560 },
  { label: 'TEST',    x: 760 },
  { label: 'REVIEW',  x: 920 },
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
      {/*
        Stage — fixed 2:1 aspect ratio box that centres itself in the available space.
        SVG viewBox is also 2:1, so preserveAspectRatio="none" never distorts. HTML
        node positions use percentages derived from SVG coords, so everything stays
        aligned at every viewport size.
      */}
      <div className="hex-office-stage">
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
          Container is 2:1 and viewBox is 2:1, so preserveAspectRatio="none" produces
          no distortion while keeping HTML percentage positions trivially aligned.
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

          {/* Stage labels — column headers above each node column */}
          {STAGE_LABELS.map(({ label, x }) => (
            <text
              key={label}
              x={x}
              y={40}
              fontSize="18"
              fontWeight="800"
              letterSpacing="3"
              fill="rgba(88,166,255,.18)"
              textAnchor="middle"
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
    </div>
  );
}
