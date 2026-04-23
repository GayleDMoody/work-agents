/**
 * Pixel-art character rendered with inline SVG <rect> elements.
 * Two frames are pre-rendered; typing animation toggles visibility via CSS.
 */

const P = 3; // pixel size in SVG units
const W = 10; // grid width
const H_GRID = 12; // grid height

type CharState = 'idle' | 'typing' | 'error' | 'celebrate';

interface Props {
  color: string;
  hairColor?: string;
  state: CharState;
}

const SKIN = '#fdd';
const HAIR_DEFAULT = '#543';
const PANTS = '#446';
const SHOE = '#333';
const EYE = '#222';

type Pixel = [number, number, string];

function getPixels(shirt: string, hair: string, frame: string): Pixel[] {
  const base: Pixel[] = [
    // Hair
    [3,0,hair],[4,0,hair],[5,0,hair],[6,0,hair],
    [2,1,hair],[3,1,hair],[4,1,hair],[5,1,hair],[6,1,hair],[7,1,hair],
    // Face
    [3,2,SKIN],[4,2,SKIN],[5,2,SKIN],[6,2,SKIN],
    [3,3,SKIN],[4,3,EYE],[5,3,SKIN],[6,3,EYE],
    [3,4,SKIN],[4,4,SKIN],[5,4,SKIN],[6,4,SKIN],
    // Neck
    [4,5,SKIN],[5,5,SKIN],
    // Shirt core
    [2,6,shirt],[3,6,shirt],[4,6,shirt],[5,6,shirt],[6,6,shirt],[7,6,shirt],
    [2,7,shirt],[3,7,shirt],[4,7,shirt],[5,7,shirt],[6,7,shirt],[7,7,shirt],
    [3,8,shirt],[4,8,shirt],[5,8,shirt],[6,8,shirt],
    // Legs
    [3,9,PANTS],[4,9,PANTS],[5,9,PANTS],[6,9,PANTS],
    [3,10,PANTS],[4,10,PANTS],[5,10,PANTS],[6,10,PANTS],
    [3,11,SHOE],[4,11,SHOE],[5,11,SHOE],[6,11,SHOE],
  ];

  // Arms vary by frame
  switch (frame) {
    case 'type1':
      base.push([1,5,SKIN],[1,6,SKIN], [8,7,SKIN],[8,8,SKIN]);
      break;
    case 'type2':
      base.push([1,7,SKIN],[1,8,SKIN], [8,5,SKIN],[8,6,SKIN]);
      break;
    case 'celebrate':
      base.push([1,4,SKIN],[1,5,SKIN], [8,4,SKIN],[8,5,SKIN]);
      break;
    case 'error':
      base.push([1,7,SKIN],[1,8,SKIN], [7,2,SKIN],[8,3,SKIN]);
      break;
    default: // idle
      base.push([1,7,SKIN],[1,8,SKIN], [8,7,SKIN],[8,8,SKIN]);
  }

  return base;
}

function SpriteFrame({ pixels, className }: { pixels: Pixel[]; className?: string }) {
  return (
    <g className={className}>
      {pixels.map(([x, y, fill], i) => (
        <rect key={i} x={x * P} y={y * P} width={P} height={P} fill={fill} />
      ))}
    </g>
  );
}

export default function PixelCharacter({ color, hairColor, state }: Props) {
  const h = hairColor || HAIR_DEFAULT;

  const frame1Name = state === 'typing' ? 'type1' : state === 'error' ? 'error' : state === 'celebrate' ? 'celebrate' : 'idle';
  const frame1 = getPixels(color, h, frame1Name);
  const frame2 = state === 'typing' ? getPixels(color, h, 'type2') : null;

  return (
    <svg
      className={`pixel-char-svg ${state === 'typing' ? 'pcs-typing' : ''}`}
      viewBox={`0 0 ${W * P} ${H_GRID * P}`}
      width={W * P}
      height={H_GRID * P}
      shapeRendering="crispEdges"
    >
      <SpriteFrame pixels={frame1} className="pcs-frame1" />
      {frame2 && <SpriteFrame pixels={frame2} className="pcs-frame2" />}
    </svg>
  );
}
