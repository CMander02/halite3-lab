import { entry } from "@/components/ModelBadge";
import type { Catalog, Submission } from "@/lib/types";
import { cn } from "@/lib/utils";

const GRID = 8;

/** 32-bit FNV-1a, then mulberry32: a small seeded generator so each bot keeps its look. */
function rng(seed: string) {
  let h = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 0x01000193);
  return () => {
    h = (h + 0x6d2b79f5) | 0;
    let t = Math.imul(h ^ (h >>> 15), 1 | h);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Left-right mirrored 8x8 pixel sprite in a random (but per-bot stable) colour. */
function sprite(seed: string) {
  const next = rng(seed);
  const hue = Math.floor(next() * 360);
  const half = GRID / 2;
  let cells: boolean[][] = [];
  // Re-roll too sparse or too dense patterns so every sprite reads as a shape.
  for (let tries = 0; tries < 8; tries++) {
    cells = Array.from({ length: GRID }, () => Array.from({ length: half }, () => next() < 0.5));
    const filled = cells.flat().filter(Boolean).length;
    if (filled >= 10 && filled <= 22 && cells.some((row) => row[half - 1])) break;
  }
  const rects: string[] = [];
  cells.forEach((row, y) =>
    row.forEach((on, x) => {
      if (on) rects.push(`<rect x="${x + 1}" y="${y + 1}" width="1" height="1"/><rect x="${GRID - x}" y="${y + 1}" width="1" height="1"/>`);
    }),
  );
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${GRID + 2} ${GRID + 2}" shape-rendering="crispEdges">` +
    `<rect width="${GRID + 2}" height="${GRID + 2}" fill="hsl(${hue} 70% 93%)"/>` +
    `<g fill="hsl(${hue} 72% 42%)">${rects.join("")}</g></svg>`;
  return "data:image/svg+xml," + encodeURIComponent(svg);
}

const sprites = new Map<string, string>();
function spriteFor(seed: string) {
  if (!sprites.has(seed)) sprites.set(seed, sprite(seed));
  return sprites.get(seed)!;
}

/**
 * Model behind a group of submissions, mirroring the backend's `bot_model`:
 * the default (else latest active) version's admin-confirmed model, then a
 * confident detection, then the declaration, then any detection.
 */
export function submissionModel(versions: Submission[]) {
  const head = versions.find((v) => v.is_default) || versions.find((v) => !v.archived) || versions[0];
  if (!head) return null;
  const known = (id?: string | null) => (id && id !== "unknown" ? id : null);
  const detected = known(head.detection?.model);
  const confident = ["medium", "high"].includes(head.detection?.model_confidence || "");
  if (head.attribution.model.source === "admin") return head.attribution.model.value;
  return (confident ? detected : null) || known(head.attribution.model.declared) || detected;
}

/** Bot mark: the producing model's icon when known, otherwise a mirrored pixel sprite. */
export function BotIcon({ id, model, catalog, className }: { id: string; model?: string | null; catalog: Catalog | null; className?: string }) {
  const known = model && model !== "unknown" ? entry(catalog, "model", model) : null;
  // Wait for the catalog rather than flashing a sprite before the model icon.
  if (known && !catalog) return <span className={cn("notch size-10 shrink-0 bg-paper", className)} aria-hidden />;
  if (known?.icon)
    return (
      <span className={cn("notch flex size-10 shrink-0 items-center justify-center bg-paper", className)} title={known.name}>
        <img src={`/model-icons/${known.icon}.svg`} alt={known.name} className="size-6 [image-rendering:auto]" />
      </span>
    );
  return <img src={spriteFor(id)} alt="" title={known?.name || "未识别模型"} className={cn("notch size-10 shrink-0 [image-rendering:pixelated]", className)} />;
}
