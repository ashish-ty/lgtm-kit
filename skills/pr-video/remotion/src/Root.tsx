import React from 'react';
import { Composition } from 'remotion';
import { PrVideo } from './PrVideo';
import type { Timeline } from './types';

// Shown only when Studio is opened without --props; real runs pass captures/timeline.json.
const EMPTY: Timeline = {
  fps: 30,
  width: 1920,
  height: 1080,
  total_frames: 180,
  title: { from: 0, duration: 90, eyebrow: 'pr-video', title: 'Run capture.py, then render.py studio', subtitle: null },
  end: { from: 90, duration: 90, points: [] },
  shots: [],
  moves: [],
  audio: [],
  subtitles: [],
};

export const Root: React.FC = () => (
  <Composition
    id="PrVideo"
    component={PrVideo}
    defaultProps={EMPTY}
    durationInFrames={EMPTY.total_frames}
    fps={EMPTY.fps}
    width={EMPTY.width}
    height={EMPTY.height}
    calculateMetadata={({ props }) => ({
      durationInFrames: props.total_frames,
      fps: props.fps,
      width: props.width,
      height: props.height,
    })}
  />
);
