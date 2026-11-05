import React from 'react';
import { AbsoluteFill } from 'remotion';
import { C, MONO, SANS } from './theme';
import type { CodeCard as Card, Row } from './types';

const ROW_H = 36;
const NUM_W = 76;

const rowStyle = (kind: Row['kind']): React.CSSProperties => ({
  display: 'flex',
  height: ROW_H,
  alignItems: 'center',
  background: kind === '+' ? C.addBg : kind === '-' ? C.delBg : 'transparent',
  color: kind === '+' ? C.addFg : kind === '-' ? C.delFg : C.codeFg,
});

const Num: React.FC<{ n: number | null }> = ({ n }) => (
  <span style={{ width: NUM_W, textAlign: 'right', paddingRight: 18, color: C.codeMuted, flexShrink: 0 }}>{n ?? ''}</span>
);

const STATUS: Record<string, string> = { added: 'new file', deleted: 'deleted', renamed: 'renamed' };

// One hunk of the diff, as the reviewer would read it: both line numbers, +/− tinted.
export const CodeCard: React.FC<{ card: Card }> = ({ card }) => (
  <AbsoluteFill style={{ background: C.codeBg, padding: '48px 64px' }}>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 24, fontFamily: MONO, fontSize: 32, color: C.white }}>
      <span style={{ fontWeight: 600 }}>{card.file}</span>
      {STATUS[card.status] && (
        <span style={{ fontFamily: SANS, fontSize: 22, color: C.codeBg, background: C.codeFg, borderRadius: 6, padding: '2px 12px' }}>
          {STATUS[card.status]}
        </span>
      )}
    </div>
    <div style={{ fontFamily: MONO, fontSize: 22, color: C.codeMuted, marginTop: 10, marginBottom: 24 }}>
      {card.status === 'renamed' && card.old_path !== card.file ? `from ${card.old_path} · ` : ''}
      hunk {card.hunk + 1} of {card.hunks}
      {card.context ? ` · ${card.context}` : ''}
    </div>
    <div style={{ fontFamily: MONO, fontSize: 25, whiteSpace: 'pre' }}>
      {card.rows.map((r, i) => (
        <div key={i} style={rowStyle(r.kind)}>
          <Num n={r.old} />
          <Num n={r.new} />
          <span style={{ width: 34, flexShrink: 0 }}>{r.kind === ' ' ? '' : r.kind}</span>
          <span>{r.text}</span>
        </div>
      ))}
    </div>
  </AbsoluteFill>
);
