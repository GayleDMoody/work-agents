import type { Agent } from '../types';

/**
 * Isometric office dashboard.
 *
 * Eight agents arranged as workstations (desk + monitor + nameplate) on an
 * isometric floor. Layout is two rows of four desks following the pipeline
 * order; connections between desks are drawn as glowing paths on the floor.
 *
 * Projection: pixel-art 2:1 dimetric (cos(30°) ≈ 0.866 is replaced by 1.0 so
 * tiles form a clean 2:1 diamond, which looks sharper at typical screen sizes
 * than a true 30° isometric).
 *
 *   screen_x = (world_x - world_y) * ISO_SX + OFFSET_X
 *   screen_y = (world_x + world_y) * ISO_SY - world_z * ISO_SY * 2 + OFFSET_Y
 *
 * The SVG viewBox is 2:1 (1000×500) to match the CSS container aspect ratio,
 * so preserveAspectRatio="none" produces zero distortion.
 */

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

const SVG_W = 1000;
const SVG_H = 500;

// Iso projection — scale + offset tuned so the 8-desk scene fills 1000×500
// with tight margins (no stage labels taking space above).
//
// Horizontal iso span ≈ (wx_max - wy_min + wy_max - wx_min) * ISO_SX
//   = (16.3 - 1.2 + 6.8 - 1.7) * 42 ≈ 848 → ~76 margin each side in 1000 wide.
// Vertical   iso span ≈ (wx_max + wy_max) * ISO_SY - (top of monitor) ≈ 489.
//   ISO_SY = ISO_SX / 2 keeps the pixel-art 2:1 dimetric aspect.
const ISO_SX = 42;
const ISO_SY = 21;
const OFFSET_X = 290;
const OFFSET_Y = 10;

function iso(wx: number, wy: number, wz: number = 0): [number, number] {
  return [
    (wx - wy) * ISO_SX + OFFSET_X,
    (wx + wy) * ISO_SY - wz * ISO_SY * 2 + OFFSET_Y,
  ];
}

function ptsToPath(pts: [number, number][]): string {
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ') + ' Z';
}

/**
 * Compute the three visible faces of an isometric box (top + front + right).
 * `cx, cy, cz` are the BOTTOM-CENTRE of the box; w/d/h are width, depth, height.
 */
function isoBox(cx: number, cy: number, cz: number, w: number, d: number, h: number) {
  const hw = w / 2;
  const hd = d / 2;
  const blf = iso(cx - hw, cy + hd, cz);           // bottom-left-front
  const brf = iso(cx + hw, cy + hd, cz);           // bottom-right-front
  const brb = iso(cx + hw, cy - hd, cz);           // bottom-right-back
  const tlf = iso(cx - hw, cy + hd, cz + h);       // top-left-front
  const trf = iso(cx + hw, cy + hd, cz + h);       // top-right-front
  const trb = iso(cx + hw, cy - hd, cz + h);       // top-right-back
  const tlb = iso(cx - hw, cy - hd, cz + h);       // top-left-back

  return {
    top:   ptsToPath([tlb, trb, trf, tlf]),
    right: ptsToPath([brb, brf, trf, trb]),
    front: ptsToPath([blf, brf, trf, tlf]),
    // Useful anchor points
    frontCentre: iso(cx, cy + hd, cz + h / 2),
    topCentre:   iso(cx, cy, cz + h),
    bottomCentre: iso(cx, cy + hd, cz),
  };
}

// Workstation world positions — 4 columns × 2 rows, pipeline-ordered
const WORKSTATIONS: { id: string; wx: number; wy: number }[] = [
  // Back row (farther from camera): planners / quality gate
  { id: 'product',     wx: 3,  wy: 2 },
  { id: 'pm',          wx: 7,  wy: 2 },
  { id: 'architect',   wx: 11, wy: 2 },
  { id: 'code_review', wx: 15, wy: 2 },
  // Front row (closer to camera): implementers + QA
  { id: 'frontend',    wx: 3,  wy: 6 },
  { id: 'backend',     wx: 7,  wy: 6 },
  { id: 'devops',      wx: 11, wy: 6 },
  { id: 'qa',          wx: 15, wy: 6 },
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

// Desk + monitor dimensions in world units
const DESK_W = 2.6;
const DESK_D = 1.6;
const DESK_H = 0.55;

const MON_W = 1.5;
const MON_D = 0.15;
const MON_H = 1.0;
/** Monitor sits toward the back of the desk (from the user's POV) — i.e. toward
 *  -y in world coords, so the screen face points +y toward the camera. */
const MON_Y_OFFSET = -0.35;

// Chair sits on the +y side of the desk (closer to camera)
const CHAIR_W = 0.8;
const CHAIR_D = 0.8;
const CHAIR_H = 0.95;
const CHAIR_Y_OFFSET = 1.15;

interface Props {
  agents: Agent[];
  onAgentClick?: (agentId: string) => void;
}

export default function IsometricOffice({ agents, onAgentClick }: Props) {
  const agentMap = new Map(agents.map(a => [a.id, a]));
  const wsMap = Object.fromEntries(WORKSTATIONS.map(ws => [ws.id, ws]));

  // Paint back-to-front so nearer workstations occlude farther ones.
  // In iso, "nearer the camera" = larger (wx + wy).
  const paintOrdered = [...WORKSTATIONS].sort((a, b) => (a.wx + a.wy) - (b.wx + b.wy));

  return (
    <div className="hex-office-viewport">
      <div className="hex-office-stage">
        <svg
          className="iso-office-svg"
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          preserveAspectRatio="none"
          aria-label="Isometric office layout"
        >
          <defs>
            <linearGradient id="floor-grad" x1="50%" y1="0%" x2="50%" y2="100%">
              <stop offset="0%"   stopColor="#0e1320" />
              <stop offset="100%" stopColor="#060912" />
            </linearGradient>
            <linearGradient id="desk-top-grad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%"   stopColor="#3a3f4a" />
              <stop offset="100%" stopColor="#2a2f3a" />
            </linearGradient>
            <linearGradient id="desk-front-grad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%"   stopColor="#1c2029" />
              <stop offset="100%" stopColor="#12151c" />
            </linearGradient>
            <linearGradient id="desk-right-grad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%"   stopColor="#262a34" />
              <stop offset="100%" stopColor="#181b22" />
            </linearGradient>
            <filter id="glow-soft" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="6" />
            </filter>
          </defs>

          <Floor />
          <FloorGrid />

          {/* Connections render below the desks (on the floor) */}
          <g className="iso-connections">
            {CONNECTIONS.map(([from, to], i) => {
              const a = wsMap[from];
              const b = wsMap[to];
              if (!a || !b) return null;
              const active =
                agentMap.get(from)?.status === 'busy' ||
                agentMap.get(to)?.status === 'busy';
              return <FloorLink key={i} a={a} b={b} active={active} />;
            })}
          </g>

          {/* Workstations, painted back-to-front */}
          {paintOrdered.map(ws => {
            const agent = agentMap.get(ws.id);
            const vis = AGENT_VISUALS[ws.id];
            if (!vis) return null;
            return (
              <Workstation
                key={ws.id}
                wx={ws.wx}
                wy={ws.wy}
                status={agent?.status ?? 'idle'}
                color={vis.color}
                icon={vis.icon}
                label={vis.label}
                role={agent?.role ?? ''}
                busyText={vis.busyText}
                onClick={() => onAgentClick?.(ws.id)}
              />
            );
          })}
        </svg>
      </div>
    </div>
  );
}

/** Large floor plane — a parallelogram in iso view */
function Floor() {
  const fx0 = 0, fx1 = 18;
  const fy0 = 0, fy1 = 8;
  const c1 = iso(fx0, fy0);
  const c2 = iso(fx1, fy0);
  const c3 = iso(fx1, fy1);
  const c4 = iso(fx0, fy1);
  const d = ptsToPath([c1, c2, c3, c4]);
  return (
    <g className="iso-floor">
      <path d={d} fill="url(#floor-grad)" opacity="0.9" />
      {/* Subtle perimeter accent */}
      <path d={d} fill="none" stroke="rgba(88,166,255,0.12)" strokeWidth="1" />
    </g>
  );
}

/** Grid lines on the floor — subtle, decorative */
function FloorGrid() {
  const lines: React.ReactNode[] = [];
  const fx0 = 0, fx1 = 18;
  const fy0 = 0, fy1 = 8;
  // Lines along x axis (parallel to x, at constant y)
  for (let y = fy0; y <= fy1; y += 2) {
    const [ax, ay] = iso(fx0, y);
    const [bx, by] = iso(fx1, y);
    lines.push(
      <line key={`gx${y}`} x1={ax} y1={ay} x2={bx} y2={by}
        stroke="rgba(88,166,255,0.06)" strokeWidth="0.8" strokeDasharray="4 4" />,
    );
  }
  // Lines along y axis (parallel to y, at constant x)
  for (let x = fx0; x <= fx1; x += 2) {
    const [ax, ay] = iso(x, fy0);
    const [bx, by] = iso(x, fy1);
    lines.push(
      <line key={`gy${x}`} x1={ax} y1={ay} x2={bx} y2={by}
        stroke="rgba(88,166,255,0.06)" strokeWidth="0.8" strokeDasharray="4 4" />,
    );
  }
  return <g className="iso-floor-grid">{lines}</g>;
}

/** Dashed glowing line on the floor between two workstations + animated dot when active */
function FloorLink({
  a, b, active,
}: {
  a: { wx: number; wy: number };
  b: { wx: number; wy: number };
  active: boolean;
}) {
  // End the line at the edge of each desk (halfway through the desk) so the
  // link appears to emerge from under the desk rather than overlap the whole box.
  const dx = b.wx - a.wx;
  const dy = b.wy - a.wy;
  const len = Math.hypot(dx, dy);
  const ux = dx / len;
  const uy = dy / len;
  const edge = 1.2; // world units from centre to desk edge along the line
  const sx = a.wx + ux * edge;
  const sy = a.wy + uy * edge;
  const ex = b.wx - ux * edge;
  const ey = b.wy - uy * edge;

  const [p1x, p1y] = iso(sx, sy, 0);
  const [p2x, p2y] = iso(ex, ey, 0);

  return (
    <g className={`iso-link${active ? ' iso-link--active' : ''}`}>
      <line
        x1={p1x} y1={p1y} x2={p2x} y2={p2y}
        vectorEffect="non-scaling-stroke"
        className="iso-link-line"
      />
      {active && (
        <circle r="4" className="iso-link-dot">
          <animateMotion
            dur="2s"
            repeatCount="indefinite"
            path={`M${p1x},${p1y} L${p2x},${p2y}`}
          />
        </circle>
      )}
    </g>
  );
}

/** A single desk + monitor + chair + nameplate */
function Workstation({
  wx, wy, status, color, icon, label, role, busyText, onClick,
}: {
  wx: number; wy: number;
  status: 'idle' | 'busy' | 'error';
  color: string; icon: string; label: string; role: string; busyText: string;
  onClick: () => void;
}) {
  // Desk base
  const desk = isoBox(wx, wy, 0, DESK_W, DESK_D, DESK_H);
  // Monitor on top of desk, toward the -y side (screen faces +y / camera)
  const monitor = isoBox(wx, wy + MON_Y_OFFSET, DESK_H, MON_W, MON_D, MON_H);
  // Chair on the +y side of desk (closer to camera)
  const chair = isoBox(wx, wy + CHAIR_Y_OFFSET, 0, CHAIR_W, CHAIR_D, CHAIR_H);
  // Chair back (thin panel at the top of chair, facing -y)
  const chairBackTopZ = CHAIR_H + 0.2;
  const chairBack = isoBox(wx, wy + CHAIR_Y_OFFSET - 0.3, CHAIR_H - 0.1, CHAIR_W, 0.1, 0.4);

  // Position anchors
  const [monScreenCx, monScreenCy] = iso(
    wx,
    wy + MON_Y_OFFSET + MON_D / 2,
    DESK_H + MON_H / 2 + 0.05,
  );
  const [labelCx, labelCy] = iso(wx, wy + DESK_D / 2 + 0.3, 0);
  // Underglow ellipse: large, soft, centred under the desk
  const [glowCx, glowCy] = iso(wx, wy, 0);
  // Bubble anchor — above the monitor
  const [bubbleX, bubbleY] = iso(wx, wy + MON_Y_OFFSET, DESK_H + MON_H + 0.7);

  // Status → accent strokes / fills
  const glowColor = status === 'error' ? '#f85149' : status === 'busy' ? color : '#2a3040';
  const screenColor = status === 'error' ? '#3a1418' : status === 'busy' ? color : '#0a1020';

  return (
    <g
      className={`iso-ws iso-ws--${status}`}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
      role="button"
      tabIndex={0}
      aria-label={`${label} workstation — ${status}`}
      style={{ cursor: 'pointer' }}
    >
      {/* Under-desk glow — signals status */}
      <ellipse
        cx={glowCx} cy={glowCy + 12}
        rx={DESK_W * ISO_SX * 0.8}
        ry={DESK_D * ISO_SY * 1.4}
        fill={glowColor}
        opacity={status === 'idle' ? 0.12 : 0.32}
        filter="url(#glow-soft)"
        className="iso-ws-glow"
      />

      {/* Chair (painted before desk so desk can occlude the parts behind it) */}
      <path d={chair.front} fill="#181c24" stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
      <path d={chair.right} fill="#14171f" stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
      <path d={chair.top}   fill="#1e2229" stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
      <path d={chairBack.front} fill="#0f1219" stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" />
      <path d={chairBack.right} fill="#0a0c12" stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" />
      <path d={chairBack.top}   fill="#151923" stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" />

      {/* Desk box */}
      <path d={desk.front} fill="url(#desk-front-grad)" stroke={color} strokeOpacity="0.35" strokeWidth="0.8" />
      <path d={desk.right} fill="url(#desk-right-grad)" stroke={color} strokeOpacity="0.3"  strokeWidth="0.8" />
      <path d={desk.top}   fill="url(#desk-top-grad)"   stroke={color} strokeOpacity="0.55" strokeWidth="0.8" />

      {/* Monitor body */}
      <path d={monitor.right} fill="#14171f" stroke="rgba(255,255,255,0.08)" strokeWidth="0.5" />
      <path d={monitor.top}   fill="#1a1d24" stroke="rgba(255,255,255,0.08)" strokeWidth="0.5" />
      {/* Monitor front = screen */}
      <path d={monitor.front} fill={screenColor} stroke={color} strokeOpacity="0.85" strokeWidth="1.2" />
      {/* Animated scanline-ish effect when busy */}
      {status === 'busy' && (
        <path d={monitor.front} fill={color} opacity="0.18" className="iso-screen-pulse" />
      )}

      {/* Icon on screen */}
      <text
        x={monScreenCx} y={monScreenCy + 2}
        fontSize="22"
        textAnchor="middle"
        dominantBaseline="middle"
        style={{ pointerEvents: 'none', userSelect: 'none' }}
      >
        {icon}
      </text>

      {/* Nameplate text — on the floor in front of the desk */}
      <text
        x={labelCx} y={labelCy + 4}
        textAnchor="middle"
        fontSize="11"
        fontWeight="800"
        fill={color}
        style={{ pointerEvents: 'none', userSelect: 'none', fontFamily: 'inherit' }}
      >
        {label}
      </text>
      <text
        x={labelCx} y={labelCy + 16}
        textAnchor="middle"
        fontSize="9"
        fill="rgba(200,210,225,0.55)"
        style={{ pointerEvents: 'none', userSelect: 'none', fontFamily: 'inherit' }}
      >
        {role}
      </text>

      {/* Speech bubble above monitor when busy */}
      {status === 'busy' && (
        <g className="iso-bubble" pointerEvents="none">
          <rect
            x={bubbleX - 55} y={bubbleY - 11}
            width="110" height="18"
            rx="4"
            fill="rgba(10,12,20,0.9)"
            stroke={color}
            strokeWidth="0.8"
            strokeOpacity="0.8"
          />
          <text
            x={bubbleX} y={bubbleY + 2}
            textAnchor="middle"
            fontSize="9"
            fontWeight="600"
            fill="#dde3ec"
            style={{ userSelect: 'none', fontFamily: 'inherit' }}
          >
            {busyText}
          </text>
        </g>
      )}

      {/* Error badge */}
      {status === 'error' && (
        <g className="iso-error-badge" pointerEvents="none">
          <circle cx={bubbleX + 45} cy={bubbleY} r="8" fill="#f85149" />
          <text
            x={bubbleX + 45} y={bubbleY + 3}
            textAnchor="middle"
            fontSize="11"
            fontWeight="900"
            fill="#fff"
          >!</text>
        </g>
      )}
    </g>
  );
}
