import React from 'react';
import { AbsoluteFill } from 'remotion';
import { C, KIND, MONO, SANS } from './theme';
import type { TestsCard as Card } from './types';

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

// The tests the PR adds, file by file, named as in the code. Listed, not run: no pass marks.
export const TestsCard: React.FC<{ card: Card }> = ({ card }) => (
  <AbsoluteFill style={{ background: C.paper, padding: '56px 120px' }}>
    <div style={{ fontFamily: SANS, fontSize: 56, fontWeight: 700, color: C.ink }}>Tests</div>
    <div style={{ fontFamily: SANS, fontSize: 28, color: C.muted, marginTop: 8 }}>
      {plural(card.total_names, 'new test')} in {plural(card.files.length + card.more, 'file')}
    </div>
    {card.files.map((f) => (
      <div key={f.path} style={{ marginTop: 22 }}>
        <div style={{ fontFamily: MONO, fontSize: 25, color: KIND.test.colour, fontWeight: 600 }}>
          {f.path} <span style={{ color: C.muted, fontWeight: 400 }}>+{f.added} −{f.removed}</span>
        </div>
        {f.names.map((n) => (
          <div key={n} style={{ fontFamily: MONO, fontSize: 23, color: C.ink, marginLeft: 30, lineHeight: 1.5 }}>• {n}</div>
        ))}
        {f.more_names > 0 && <div style={{ fontFamily: SANS, fontSize: 22, color: C.muted, marginLeft: 30 }}>and {f.more_names} more</div>}
        {f.names.length === 0 && <div style={{ fontFamily: SANS, fontSize: 22, color: C.muted, marginLeft: 30 }}>no new test names found</div>}
      </div>
    ))}
    {card.more > 0 && <div style={{ fontFamily: SANS, fontSize: 24, color: C.muted, marginTop: 18 }}>and {card.more} more test files</div>}
  </AbsoluteFill>
);
