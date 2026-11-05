import React from 'react';
import { Easing, interpolate } from 'remotion';
import { C } from './theme';
import type { Move, Point } from './types';

const PULSE = 14;
const PRESS = 5;
const ease = Easing.inOut(Easing.cubic);

export const position = (moves: Move[], frame: number): Point => {
  let current: Point = moves.length ? moves[0].from : [960, 640];
  for (const m of moves) {
    if (frame < m.start) break;
    if (frame >= m.end) {
      current = m.to;
      continue;
    }
    const p = ease((frame - m.start) / (m.end - m.start));
    return [m.from[0] + (m.to[0] - m.from[0]) * p, m.from[1] + (m.to[1] - m.from[1]) * p];
  }
  return current;
};

const lastClick = (moves: Move[], frame: number): number | null => {
  const hits = moves.filter((m) => m.click !== null && frame >= m.click && frame - m.click < PULSE);
  return hits.length ? (hits[hits.length - 1].click as number) : null;
};

export const Cursor: React.FC<{ moves: Move[]; frame: number }> = ({ moves, frame }) => {
  const [x, y] = position(moves, frame);
  const click = lastClick(moves, frame);
  const since = click === null ? PULSE : frame - click;
  const press = since < PRESS ? interpolate(since, [0, 2, PRESS], [1, 0.82, 1]) : 1;
  return (
    <>
      {click !== null && (
        <div
          style={{
            position: 'absolute',
            left: x,
            top: y,
            width: 2,
            height: 2,
            borderRadius: '50%',
            border: `3px solid ${C.click}`,
            transform: `translate(-50%, -50%) scale(${interpolate(since, [0, PULSE], [4, 26])})`,
            opacity: interpolate(since, [0, PULSE], [0.9, 0]),
          }}
        />
      )}
      <svg
        width={34}
        height={34}
        viewBox="0 0 24 24"
        style={{
          position: 'absolute',
          left: x - 6,
          top: y - 3,
          transform: `scale(${press})`,
          transformOrigin: '6px 3px',
          filter: 'drop-shadow(0 3px 6px rgba(20,23,28,0.35))',
        }}
      >
        <path d="M5 2 L5 19 L9.5 15 L12.5 22 L15.5 20.7 L12.6 14 L18.5 14 Z" fill={C.ink} stroke={C.white}
              strokeWidth={1.4} strokeLinejoin="round" />
      </svg>
    </>
  );
};
