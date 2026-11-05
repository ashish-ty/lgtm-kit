// The shape of captures/timeline.json, written by ../../scripts/timeline.py.
// The composition draws this and nothing else: every timing decision is made in Python.

export type Point = [number, number];

export type Row = { kind: '+' | '-' | ' '; old: number | null; new: number | null; text: string };

export type CodeCard = {
  file: string;
  old_path: string;
  status: string;
  context: string;
  hunk: number;
  hunks: number;
  rows: Row[];
};

export type FileKind = 'code' | 'test' | 'generated';

export type OverviewFile = { path: string; kind: FileKind; status: string; added: number; removed: number };

export type Totals = { files: number } & Partial<Record<FileKind, { added: number; removed: number }>>;

// colour: a file kind (code / test / generated), a layer's index, or 'other'
export type Group = { name: string; colour: FileKind | number | 'other'; added: number; removed: number;
                      files: OverviewFile[]; more: number };

export type OverviewCard = { groups: Group[]; totals: Totals };

export type TestFile = OverviewFile & { names: string[]; more_names: number };

export type TestsCard = { files: TestFile[]; more: number; total_names: number };

export type Shot = {
  kind: 'image' | 'code' | 'overview' | 'tests';
  image: string | null;
  card: CodeCard | OverviewCard | TestsCard | null;
  from: number;
  duration: number;
  caption: string | null;
  beat: string;
  // [x, y, width, height] of the screen that fills the frame; null shows the whole screen
  crop: [number, number, number, number] | null;
};

export type Move = { start: number; end: number; from: Point; to: Point; click: number | null };

export type Clip = { src: string; from: number; duration: number };

export type TitleCard = { from: number; duration: number; eyebrow: string; title: string; subtitle: string | null };

export type EndCard = { from: number; duration: number; points: string[] };

export type Timeline = {
  fps: number;
  width: number;
  height: number;
  total_frames: number;
  title: TitleCard;
  end: EndCard;
  shots: Shot[];
  moves: Move[];
  audio: Clip[];
};
