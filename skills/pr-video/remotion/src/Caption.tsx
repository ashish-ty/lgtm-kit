import React from 'react';
import { interpolate, useCurrentFrame } from 'remotion';
import { C, FADE, SANS } from './theme';

// A lower third over the screen: dark, so it reads over a light or a dark UI.
export const Caption: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const shown = interpolate(frame, [0, FADE], [0, 1], { extrapolateRight: 'clamp' });
  return (
    <div
      style={{
        position: 'absolute',
        left: 72,
        bottom: 72,
        maxWidth: 1300,
        padding: '22px 34px 24px 30px',
        background: 'rgba(20,23,28,0.9)',
        borderLeft: `6px solid ${C.click}`,
        borderRadius: 6,
        color: C.paper,
        fontFamily: SANS,
        fontSize: 40,
        fontWeight: 500,
        lineHeight: 1.25,
        opacity: shown,
        transform: `translateY(${(1 - shown) * 14}px)`,
        boxShadow: '0 10px 30px rgba(20,23,28,0.25)',
      }}
    >
      {text}
    </div>
  );
};
