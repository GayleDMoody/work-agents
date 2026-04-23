import { useState, useCallback } from 'react';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
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

// Circular arrangement — 8 agents on a ring around a central hub.
// Pipeline order goes clockwise from the top so the visual flow matches
// the execution sequence: Product (top) → PM → Architect → Frontend → Backend →
// DevOps → QA → Code Review, back around to Product.
const HUB_X = 10;
const HUB_Y = 4.5;
const RING_R = 4;
const RING_ORDER = [
  'product',     // 90° (top)
  'pm',          // 45° (top-right)
  'architect',   // 0°  (right)
  'frontend',    // -45°
  'backend',     // -90° (bottom)
  'devops',      // -135°
  'qa',          // 180° (left)
  'code_review', // 135° (top-left)
];

const WORKSTATIONS: { id: string; wx: number; wy: number }[] = RING_ORDER.map((id, i) => {
  // In iso-2:1 projection, the world-top of the circle appears at SCREEN top-right,
  // not screen-top. Starting at θ=135° (world top-left) puts Product at the visual
  // top of the screen, so the pipeline reads clockwise from the top.
  const angleDeg = 135 - i * 45;
  const rad = (angleDeg * Math.PI) / 180;
  return {
    id,
    wx: HUB_X + RING_R * Math.cos(rad),
    // Screen/world y flips: positive sin is "up" in math, but we want smaller wy
    // for the top of the circle (i.e. farther from camera), so subtract.
    wy: HUB_Y - RING_R * Math.sin(rad),
  };
});

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

// Desk + monitor dimensions in world units.
// Smaller than the previous grid layout so 8 desks fit around a radius-4 ring
// without visual collision. The smaller desks also give the central hub room
// to breathe.
const DESK_W = 1.9;
const DESK_D = 1.15;
const DESK_H = 0.5;

const MON_W = 1.1;
const MON_D = 0.12;
const MON_H = 0.8;
/** Monitor sits toward the back of the desk (from the user's POV) — i.e. toward
 *  -y in world coords, so the screen face points +y toward the camera. */
const MON_Y_OFFSET = -0.26;

// Chair sits on the +y side of the desk (closer to camera)
const CHAIR_W = 0.55;
const CHAIR_D = 0.55;
const CHAIR_H = 0.7;
const CHAIR_Y_OFFSET = 0.82;

interface Props {
  agents: Agent[];
  onAgentClick?: (agentId: string) => void;
}

const ZOOM_MIN = 0.6;
const ZOOM_MAX = 2.4;
const ZOOM_STEP = 0.15;

export default function IsometricOffice({ agents, onAgentClick }: Props) {
  const agentMap = new Map(agents.map(a => [a.id, a]));
  const wsMap = Object.fromEntries(WORKSTATIONS.map(ws => [ws.id, ws]));

  // Paint back-to-front so nearer workstations occlude farther ones.
  // In iso, "nearer the camera" = larger (wx + wy).
  const paintOrdered = [...WORKSTATIONS].sort((a, b) => (a.wx + a.wy) - (b.wx + b.wy));

  // Zoom state — applied as a CSS transform on the stage. Clamped to a sensible range.
  const [zoom, setZoom] = useState(1);
  const zoomIn    = useCallback(() => setZoom(z => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(2))), []);
  const zoomOut   = useCallback(() => setZoom(z => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(2))), []);
  const zoomReset = useCallback(() => setZoom(1), []);

  // Mouse-wheel zoom: scroll up zooms in, scroll down zooms out.
  const handleWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    if (e.ctrlKey || e.metaKey) return; // let the browser handle page zoom
    e.preventDefault();
    const delta = -e.deltaY * 0.0015;
    setZoom(z => Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, +(z + delta).toFixed(3))));
  }, []);

  return (
    <div className="hex-office-viewport" onWheel={handleWheel}>
      <div className="iso-zoom-controls" aria-label="Zoom controls">
        <button type="button" className="iso-zoom-btn" onClick={zoomIn}
          disabled={zoom >= ZOOM_MAX} aria-label="Zoom in">
          <ZoomIn size={14} />
        </button>
        <button type="button" className="iso-zoom-btn iso-zoom-reset" onClick={zoomReset}
          aria-label="Reset zoom" title="Reset zoom">
          <span>{Math.round(zoom * 100)}%</span>
          <Maximize2 size={11} style={{ marginLeft: 4, opacity: 0.6 }} />
        </button>
        <button type="button" className="iso-zoom-btn" onClick={zoomOut}
          disabled={zoom <= ZOOM_MIN} aria-label="Zoom out">
          <ZoomOut size={14} />
        </button>
      </div>
      <div className="hex-office-stage" style={{ transform: `scale(${zoom})` }}>
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
          <Hub />

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

// Floor extent. Dimensions chosen so every axis divides cleanly by the tile
// size (TILE=2) — span x = 22 = 11 tiles, span y = 10 = 5 tiles. No tile
// bleeds past the floor and every desk sits fully on it (Backend at wy=8.5
// has its front at wy~9.08 which fits inside FLOOR_Y1=9.5).
const FLOOR_X0 = -2;
const FLOOR_X1 = 20;
const FLOOR_Y0 = -0.5;
const FLOOR_Y1 = 9.5;
const TILE = 2;

/** Large floor plane with diamond tile pattern — a parallelogram in iso view. */
function Floor() {
  const c1 = iso(FLOOR_X0, FLOOR_Y0);
  const c2 = iso(FLOOR_X1, FLOOR_Y0);
  const c3 = iso(FLOOR_X1, FLOOR_Y1);
  const c4 = iso(FLOOR_X0, FLOOR_Y1);
  const d = ptsToPath([c1, c2, c3, c4]);

  // Unique clip-path id per mount in case multiple offices ever share the page.
  const clipId = 'iso-floor-clip';

  // 2×2 world-unit tiles alternating between two subtle shades.
  // Tiles are clipped to the floor shape so they never extend past the edge.
  const tiles: React.ReactNode[] = [];
  for (let y = FLOOR_Y0; y < FLOOR_Y1; y += TILE) {
    for (let x = FLOOR_X0; x < FLOOR_X1; x += TILE) {
      const tc1 = iso(x, y);
      const tc2 = iso(x + TILE, y);
      const tc3 = iso(x + TILE, y + TILE);
      const tc4 = iso(x, y + TILE);
      const tileD = ptsToPath([tc1, tc2, tc3, tc4]);
      const ix = Math.round((x - FLOOR_X0) / TILE);
      const iy = Math.round((y - FLOOR_Y0) / TILE);
      const isDark = (ix + iy) % 2 === 0;
      tiles.push(
        <path
          key={`tile-${ix}-${iy}`}
          d={tileD}
          fill={isDark ? 'rgba(255,255,255,0.020)' : 'rgba(255,255,255,0.050)'}
          stroke="rgba(88,166,255,0.06)"
          strokeWidth="0.5"
        />,
      );
    }
  }

  return (
    <g className="iso-floor">
      <defs>
        <clipPath id={clipId}>
          <path d={d} />
        </clipPath>
      </defs>
      <path d={d} fill="url(#floor-grad)" opacity="0.95" />
      <g clipPath={`url(#${clipId})`}>{tiles}</g>
      {/* No hard perimeter stroke — the tile grid already defines the floor edge,
          and a bright outline cuts a distracting diagonal across the viewport. */}
    </g>
  );
}

/** Central hub — a low hexagonal platform with a glowing orb hovering above it.
 *  This is the visual "anchor" of the circular layout; every desk faces it. */
function Hub() {
  const HUB_R = 1.2;
  const HUB_PLATFORM_H = 0.18;
  // Hexagon points in world coords
  const hexPts: [number, number][] = [];
  for (let i = 0; i < 6; i++) {
    const a = (i * 60 - 30) * Math.PI / 180;
    hexPts.push([HUB_X + HUB_R * Math.cos(a), HUB_Y + HUB_R * Math.sin(a)]);
  }
  // Top face of platform
  const topPts = hexPts.map(([x, y]) => iso(x, y, HUB_PLATFORM_H));
  // Bottom face (for side strips)
  const botPts = hexPts.map(([x, y]) => iso(x, y, 0));
  // Side faces — build a path combining top and bottom edges for each visible side
  const sidePaths: string[] = [];
  for (let i = 0; i < 6; i++) {
    const j = (i + 1) % 6;
    sidePaths.push(ptsToPath([botPts[i], botPts[j], topPts[j], topPts[i]]));
  }
  // Orb positions
  const [orbCx, orbCy] = iso(HUB_X, HUB_Y, HUB_PLATFORM_H + 0.9);
  const [glowCx, glowCy] = iso(HUB_X, HUB_Y, 0);

  return (
    <g className="iso-hub" pointerEvents="none">
      {/* Soft glow on the floor beneath the hub */}
      <ellipse cx={glowCx} cy={glowCy + 8} rx={HUB_R * ISO_SX * 1.2} ry={HUB_R * ISO_SY * 1.5}
        fill="#58a6ff" opacity="0.22" filter="url(#glow-soft)" />
      {/* Platform sides (all rendered; the ones facing away will be occluded visually) */}
      {sidePaths.map((d, i) => (
        <path key={i} d={d} fill="#1a1f2a" stroke="rgba(88,166,255,0.25)" strokeWidth="0.5" />
      ))}
      {/* Platform top */}
      <path d={ptsToPath(topPts)} fill="#232a3a" stroke="rgba(88,166,255,0.5)" strokeWidth="1" />
      {/* Hub orb */}
      <circle cx={orbCx} cy={orbCy} r="14" fill="#58a6ff" opacity="0.18" className="iso-hub-glow" />
      <circle cx={orbCx} cy={orbCy} r="8"  fill="#58a6ff" opacity="0.45" className="iso-hub-core" />
      <circle cx={orbCx} cy={orbCy} r="4"  fill="#cfe4ff" opacity="0.9"  className="iso-hub-core" />
    </g>
  );
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
