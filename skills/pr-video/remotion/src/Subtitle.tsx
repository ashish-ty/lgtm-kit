import React from 'react';
import { C, SANS } from './theme';

// Height the bottom of the frame keeps clear for a two-line subtitle; Caption sits above it.
export const SUBTITLE_SPACE = 170;

// The narration as it is spoken: centred at the foot of the frame, white on a dark band, so it
// reads over code, cards and any app screen alike.
export const Subtitle: React.FC<{ text: string }> = ({ text }) => (
  <div style={{ position: 'absolute', left: 0, right: 0, bottom: 40, display: 'flex', justifyContent: 'center' }}>
    <div
      style={{
        maxWidth: 1500,
        padding: '12px 28px 14px',
        background: 'rgba(20,23,28,0.82)',
        borderRadius: 8,
        color: C.white,
        fontFamily: SANS,
        fontSize: 36,
        fontWeight: 500,
        lineHeight: 1.3,
        textAlign: 'center',
      }}
    >
      {text}
    </div>
  </div>
);
