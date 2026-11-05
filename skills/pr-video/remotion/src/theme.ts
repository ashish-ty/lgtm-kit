// A neutral look for every repo: no product branding, system faces only (nothing fetched at render).
export const SANS = "-apple-system, 'SF Pro Text', 'Segoe UI', Helvetica, Arial, sans-serif";
export const MONO = "'SF Mono', Menlo, 'JetBrains Mono', Consolas, monospace";

export const C = {
  ink: '#14171c',
  paper: '#f6f7f9',
  muted: '#6b7280',
  accent: '#2563eb',
  click: '#d97706',
  white: '#ffffff',
  codeBg: '#16191f',
  codeFg: '#d6dae0',
  codeMuted: '#6b7280',
  addBg: 'rgba(46,160,67,0.18)',
  addFg: '#7ee2a0',
  delBg: 'rgba(248,81,73,0.18)',
  delFg: '#ffa198',
};

// Bars and labels for the three kinds of file the overview groups.
export const KIND = {
  code: { label: 'code', colour: '#2563eb' },
  test: { label: 'tests', colour: '#059669' },
  generated: { label: 'generated', colour: '#9ca3af' },
} as const;

// Layers the storyboard names take these in order; files outside every layer are 'other'.
export const LAYER_COLOURS = ['#2563eb', '#7c3aed', '#0891b2', '#c2410c', '#be185d', '#4d7c0f'];
export const OTHER_COLOUR = '#9ca3af';

export const FADE = 10;
