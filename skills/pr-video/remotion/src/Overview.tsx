import React from 'react';
import { AbsoluteFill } from 'remotion';
import { C, KIND, LAYER_COLOURS, MONO, OTHER_COLOUR, SANS } from './theme';
import type { Group, OverviewCard as Card, OverviewFile } from './types';

const BAR_W = 360;

const colourOf = (g: Group): string =>
  typeof g.colour === 'number' ? LAYER_COLOURS[g.colour % LAYER_COLOURS.length]
    : g.colour === 'other' ? OTHER_COLOUR : KIND[g.colour].colour;

const FileRow: React.FC<{ f: OverviewFile; colour: string; most: number }> = ({ f, colour, most }) => (
  <div style={{ display: 'flex', alignItems: 'center', height: 46, fontFamily: MONO, fontSize: 25, color: C.ink }}>
    <span style={{ width: 8, height: 26, background: colour, borderRadius: 3, marginRight: 22, flexShrink: 0 }} />
    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.path}</span>
    <span style={{ width: 120, textAlign: 'right', color: '#15803d' }}>+{f.added}</span>
    <span style={{ width: 120, textAlign: 'right', color: '#b91c1c', marginRight: 28 }}>−{f.removed}</span>
    <span style={{ width: BAR_W, display: 'flex' }}>
      <span style={{ width: (BAR_W * f.added) / most, height: 14, background: '#22c55e' }} />
      <span style={{ width: (BAR_W * f.removed) / most, height: 14, background: '#ef4444' }} />
    </span>
  </div>
);

const GroupBlock: React.FC<{ g: Group; most: number }> = ({ g, most }) => (
  <div style={{ marginTop: 22 }}>
    <div style={{ fontFamily: SANS, fontSize: 27, fontWeight: 700, color: colourOf(g), marginBottom: 4 }}>
      {g.name} <span style={{ fontWeight: 400, color: C.muted }}>+{g.added} −{g.removed}</span>
    </div>
    {g.files.map((f) => <FileRow key={f.path} f={f} colour={colourOf(g)} most={most} />)}
    {g.more > 0 && <div style={{ fontFamily: SANS, fontSize: 23, color: C.muted, marginLeft: 30 }}>and {g.more} more</div>}
  </div>
);

// Every changed file, in groups (layers, or code / tests / generated), biggest first.
export const Overview: React.FC<{ card: Card }> = ({ card }) => {
  const most = Math.max(1, ...card.groups.flatMap((g) => g.files.map((f) => f.added + f.removed)));
  return (
    <AbsoluteFill style={{ background: C.paper, padding: '56px 120px' }}>
      <div style={{ fontFamily: SANS, fontSize: 56, fontWeight: 700, color: C.ink }}>What changed</div>
      <div style={{ fontFamily: SANS, fontSize: 28, color: C.muted, marginTop: 8 }}>{card.totals.files} files</div>
      {card.groups.map((g) => <GroupBlock key={g.name} g={g} most={most} />)}
    </AbsoluteFill>
  );
};
