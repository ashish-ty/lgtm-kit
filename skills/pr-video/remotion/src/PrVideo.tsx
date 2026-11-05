import React from 'react';
import { AbsoluteFill, Audio, Img, Sequence, staticFile, useCurrentFrame } from 'remotion';
import { Caption } from './Caption';
import { EndCard, TitleCard } from './Cards';
import { CodeCard } from './CodeCard';
import { Cursor } from './Cursor';
import { Overview } from './Overview';
import { TestsCard } from './TestsCard';
import { C } from './theme';
import type { CodeCard as Code, OverviewCard, Shot, TestsCard as Tests, Timeline } from './types';

// A crop is drawn by scaling the whole still and shifting it, so the cropped part fills the frame.
const framing = (crop: Shot['crop'], width: number, height: number): React.CSSProperties => {
  if (!crop) return { width, height };
  const [x, y, w] = crop;
  const scale = width / w;
  return { position: 'absolute', left: -x * scale, top: -y * scale, width: width * scale, height: height * scale };
};

const ShotView: React.FC<{ shot: Shot; width: number; height: number }> = ({ shot, width, height }) => {
  if (shot.kind === 'code') return <CodeCard card={shot.card as Code} />;
  if (shot.kind === 'overview') return <Overview card={shot.card as OverviewCard} />;
  if (shot.kind === 'tests') return <TestsCard card={shot.card as Tests} />;
  return <Img src={staticFile(shot.image as string)} style={framing(shot.crop, width, height)} />;
};

export const PrVideo: React.FC<Timeline> = (t) => {
  const frame = useCurrentFrame();
  const current = t.shots.find((s) => frame >= s.from && frame < s.from + s.duration);
  return (
    <AbsoluteFill style={{ background: C.paper }}>
      {t.shots.map((shot) => (
        <Sequence key={`${shot.beat}-${shot.from}`} from={shot.from} durationInFrames={shot.duration}>
          <ShotView shot={shot} width={t.width} height={t.height} />
          {shot.caption && <Caption text={shot.caption} />}
        </Sequence>
      ))}
      {current?.kind === 'image' && <Cursor moves={t.moves} frame={frame} />}
      {t.audio.map((clip) => (
        <Sequence key={clip.src} from={clip.from} durationInFrames={clip.duration}>
          <Audio src={staticFile(clip.src)} />
        </Sequence>
      ))}
      <Sequence from={t.title.from} durationInFrames={t.title.duration}>
        <TitleCard {...t.title} />
      </Sequence>
      <Sequence from={t.end.from} durationInFrames={t.end.duration}>
        <EndCard {...t.end} />
      </Sequence>
    </AbsoluteFill>
  );
};
