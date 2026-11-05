import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { C, FADE, SANS } from './theme';
import type { EndCard as End, TitleCard as Title } from './types';

const useFade = (duration: number, fadeIn: boolean, fadeOut: boolean) => {
  const frame = useCurrentFrame();
  const inn = fadeIn ? interpolate(frame, [0, FADE], [0, 1], { extrapolateRight: 'clamp' }) : 1;
  const out = fadeOut ? interpolate(frame, [duration - FADE, duration], [1, 0], { extrapolateLeft: 'clamp' }) : 1;
  return Math.min(inn, out);
};

export const TitleCard: React.FC<Title> = (t) => {
  const opacity = useFade(t.duration, false, true);
  return (
    <AbsoluteFill style={{ background: C.paper, padding: '120px 140px', justifyContent: 'center', opacity }}>
      <div style={{ fontFamily: SANS, fontSize: 28, fontWeight: 600, letterSpacing: 3, color: C.accent, textTransform: 'uppercase' }}>
        {t.eyebrow}
      </div>
      <div style={{ fontFamily: SANS, fontSize: 92, fontWeight: 700, lineHeight: 1.08, color: C.ink, marginTop: 24, maxWidth: 1600 }}>
        {t.title}
      </div>
      {t.subtitle && <div style={{ fontFamily: SANS, fontSize: 36, color: C.muted, marginTop: 32 }}>{t.subtitle}</div>}
    </AbsoluteFill>
  );
};

// What the reviewer should check by hand: the video shows the change, it doesn't approve it.
export const EndCard: React.FC<End> = (e) => {
  const opacity = useFade(e.duration, true, false);
  return (
    <AbsoluteFill style={{ background: C.paper, padding: '120px 140px', justifyContent: 'center', opacity }}>
      <div style={{ fontFamily: SANS, fontSize: 64, fontWeight: 700, color: C.ink }}>
        {e.points.length ? 'Check before you approve' : 'End of walkthrough'}
      </div>
      {e.points.map((p, i) => (
        <div key={i} style={{ display: 'flex', gap: 28, marginTop: i ? 28 : 56, fontFamily: SANS, fontSize: 40, color: C.ink, maxWidth: 1600 }}>
          <span style={{ color: C.accent, fontWeight: 700 }}>{i + 1}</span>
          <span>{p}</span>
        </div>
      ))}
    </AbsoluteFill>
  );
};
