import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

/*
 * Multi-colour 16×16 pixel art for the spots where a one-colour line icon reads too flat.
 * Each glyph is a grid of palette letters ("." is transparent); `mono` paints every pixel
 * in currentColor so the same glyph can sit in a tab next to line icons.
 */
const PALETTE: Record<string, string> = {
  k: "#0a1a4a", // ink outline
  b: "#1f4fff", // blue
  B: "#1236c8", // deep blue
  l: "#8ea8ff", // light blue
  w: "#ffffff",
  s: "#c9d1e8", // steel
  g: "#8a93b0", // grey
  o: "#c47a35", // wood
  O: "#7a4319", // dark wood
  c: "#3fd9c7", // halite crystal
  C: "#119c8c", // crystal shade
  y: "#f2b52d", // gold
  r: "#f2542d", // signal red
  G: "#0e9f6e", // green
  P: "#f6e7bd", // parchment
  Q: "#e3cf93", // parchment fold
};

const ART = {
  pickaxe: [
    "................",
    "...kkkkkkk......",
    "..kssssssskk....",
    ".ksskkkkkkssk...",
    ".kkk....kOkssk..",
    "........kOk.ksk.",
    ".......kOk...ksk",
    "......kOk....ksk",
    ".....kOk.....kkk",
    "....kOk.........",
    "...kOk.....kk...",
    "..kOk.....kcck..",
    ".kOk.....kccCck.",
    ".kk......kcCCck.",
    "..........kCck..",
    "...........kk...",
  ],
  laptop: [
    "................",
    "................",
    "..kkkkkkkkkkkk..",
    "..kBBBBBBBBBBk..",
    "..kBwwBBBBBBBk..",
    "..kBBlwwwBBBBk..",
    "..kBBlyyBBBBBk..",
    "..kBwwBBBBBBBk..",
    "..kBBBBBBBBGBk..",
    "..kBBBBBBBBBBk..",
    "..kkkkkkkkkkkk..",
    ".kssssssssssssk.",
    "ksgsgsgsgsgsgssk",
    "kssssskkkksssssk",
    ".kkkkkkkkkkkkkk.",
    "................",
  ],
  cloud: [
    "................",
    "......kkkk......",
    "....kkwwwwk.....",
    "...kwwwwwwwkkk..",
    ".kkwwwwwwwwwwwk.",
    "kwwwwwwlwwwwwwwk",
    "kwwwwwwwwwwwwllk",
    ".kkkkkkkkkkkkkk.",
    ".......kk.......",
    "..kkkkkkkkkkkk..",
    "..kbbbbbbbbGyk..",
    "..kkkkkkkkkkkk..",
    "..kbbbbbbbbGGk..",
    "..kkkkkkkkkkkk..",
    "................",
    "................",
  ],
  map: [
    "................",
    ".kkkkkkkkkkkkkk.",
    ".kPPPPQQQQPPPPk.",
    ".kPllPQQQQrPrPk.",
    ".kllllQQQQPrPPk.",
    ".kPllPQQQQrPrPk.",
    ".kPPPPQQQOPPPPk.",
    ".kPPPPQQOQPPPPk.",
    ".kPPPOQOQQPPPPk.",
    ".kPPOPQQQQPPPPk.",
    ".kPOPPQQQQPGGPk.",
    ".kPPPPQQQQGGGGk.",
    ".kPPPPQQQQPGGPk.",
    ".kkkkkkkkkkkkkk.",
    "................",
    "................",
  ],
} satisfies Record<string, string[]>;

export type GlyphName = keyof typeof ART;

export function Glyph({ name, size = 16, mono = false, className }: { name: GlyphName; size?: number; mono?: boolean; className?: string }) {
  const rects: ReactNode[] = [];
  ART[name].forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      const ch = row[x];
      if (ch === ".") continue;
      // run-length merge horizontal pixels of one colour
      let end = x;
      while (end + 1 < row.length && row[end + 1] === ch) end++;
      rects.push(<rect key={`${x}-${y}`} x={x} y={y} width={end - x + 1} height={1} fill={mono ? "currentColor" : PALETTE[ch]} />);
      x = end;
    }
  });
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} shapeRendering="crispEdges" className={cn("shrink-0", className)} aria-hidden>
      {rects}
    </svg>
  );
}

/** A glyph usable wherever a pixelart-react icon component is expected (`size`, `className`). */
export function glyphIcon(name: GlyphName, mono = true) {
  const C = ({ size, className }: { size?: number; className?: string }) => <Glyph name={name} size={size} mono={mono} className={className} />;
  C.displayName = `Glyph(${name})`;
  return C;
}

type IconLike = ComponentType<{ size?: number; className?: string }>;

const TONES = {
  blue: "bg-blue text-white",
  soft: "bg-blue-100 text-blue-700",
  ink: "bg-ink text-paper",
  orange: "bg-[#ffe6dc] text-[#d4401d]",
  green: "bg-[#dcf3e8] text-good",
  gold: "bg-[#fdf0cc] text-[#a86b00]",
} as const;
export type Tone = keyof typeof TONES;

/** Icon on a notched colour tile with a 2px offset shadow block — the two-tone version of a bare line icon. */
export function IconTile({ icon: Icon, tone = "soft", size = 16, className }: { icon: IconLike; tone?: Tone; size?: number; className?: string }) {
  const box = size + Math.max(8, Math.round(size / 2));
  return (
    <span className="relative inline-flex shrink-0" style={{ width: box + 2, height: box + 2 }} aria-hidden>
      <span className="notch absolute top-[2px] left-[2px] bg-ink/15" style={{ width: box, height: box }} />
      <span className={cn("notch relative inline-flex items-center justify-center", TONES[tone], className)} style={{ width: box, height: box }}>
        <Icon size={size} />
      </span>
    </span>
  );
}
