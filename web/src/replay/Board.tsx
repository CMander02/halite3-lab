import { useEffect, useRef, useState } from "react";
import type { Replay } from "@/lib/types";
import { number } from "@/lib/api";
import { playerColor } from "@/lib/colors";
import { cn } from "@/lib/utils";
import type { BoardState } from "./replay";
import { wrappedDistance } from "./replay";

const BAYER4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => (v + 0.5) / 16);
const BAYER2 = [0, 2, 3, 1].map((v) => (v + 0.5) / 4);
const PAPER = "#fbfaf5";
const INK = "#0a1a4a";

// 5x5 hull, bow pointing up; rotated by the last move direction.
const HULL = ["..#..", ".###.", ".###.", "#####", "#.#.#"];
const SCOUT_HULL = ["#.#.#", "..#..", ".###.", "..#..", ".#.#."];
const rotate = (x: number, y: number, dir: string): [number, number] =>
  dir === "e" ? [4 - y, x] : dir === "s" ? [4 - x, 4 - y] : dir === "w" ? [y, 4 - x] : [x, y];

export default function Board({
  replay,
  state,
  prev,
  perspective = "all",
  className,
  interactive = true,
}: {
  replay: Replay;
  state: BoardState;
  prev?: BoardState;
  perspective?: string;
  className?: string;
  interactive?: boolean;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [selected, setSelected] = useState<{ x: number; y: number } | null>(null);
  const [geometry, setGeometry] = useState({ cell: 0, offsetX: 0, offsetY: 0 });
  const { width: w, height: h, grid } = replay.production_map;

  useEffect(() => {
    const element = canvas.current,
      box = wrap.current;
    if (!element || !box) return;
    const draw = () => {
      const rect = box.getBoundingClientRect();
      const cell = Math.max(2, Math.floor(Math.min(rect.width / w, rect.height / h)));
      const bw = cell * w,
        bh = cell * h;
      const ratio = Math.min(window.devicePixelRatio || 1, 3);
      element.width = Math.round(bw * ratio);
      element.height = Math.round(bh * ratio);
      element.style.width = `${bw}px`;
      element.style.height = `${bh}px`;
      const offsetX = Math.floor((rect.width - bw) / 2),
        offsetY = Math.floor((rect.height - bh) / 2);
      element.style.left = `${offsetX}px`;
      element.style.top = `${offsetY}px`;
      setGeometry((g) => (g.cell === cell && g.offsetX === offsetX && g.offsetY === offsetY ? g : { cell, offsetX, offsetY }));
      const ctx = element.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.imageSmoothingEnabled = false;
      ctx.fillStyle = PAPER;
      ctx.fillRect(0, 0, bw, bh);

      const player = Number(perspective);
      const sources =
        perspective === "all"
          ? []
          : [
              ...Object.values(state.ships[player] || {}),
              ...replay.players.filter((p) => p.player_id === player).map((p) => p.factory_location),
              ...state.dropoffs.filter((d) => d.owner === player),
            ];
      const radius = replay.GAME_CONSTANTS.VISION_RADIUS;
      const visible = (x: number, y: number) => perspective === "all" || !replay.GAME_CONSTANTS.FOG_ENABLED || sources.some((s) => wrappedDistance(x, y, s.x, s.y, w, h, replay.GAME_CONSTANTS.BOUNDED_MAP) <= ('scout' in s && s.scout ? replay.GAME_CONSTANTS.SCOUT_VISION_RADIUS ?? radius : radius));

      const coarse = (replay.GAME_CONSTANTS.MAX_CELL_PRODUCTION || 1000) <= 15;
      const sub = cell >= (coarse ? 4 : 12) ? 4 : cell >= (coarse ? 2 : 6) ? 2 : 1;
      const step = cell / sub;
      for (let y = 0; y < h; y++)
        for (let x = 0; x < w; x++) {
          const left = x * cell,
            top = y * cell;
          if (grid[y][x].reef) {
            ctx.fillStyle = INK;
            ctx.fillRect(left, top, cell, cell);
            if (cell >= 6) {
              ctx.fillStyle = "#4b5880";
              for (let j = 0; j < sub; j++) for (let i = 0; i < sub; i++) if ((i + j) % 2 === 0 && (i * 3 + j) % 4 === 0) ctx.fillRect(left + i * step, top + j * step, Math.ceil(step), Math.ceil(step));
            }
            continue;
          }
          if (!visible(x, y)) {
            ctx.fillStyle = "#e9e5d8";
            ctx.fillRect(left, top, cell, cell);
            continue;
          }
          const amount = Math.min(1, state.halite[y * w + x] / (replay.GAME_CONSTANTS.MAX_CELL_PRODUCTION || 1000));
          if (amount <= 0) continue;
          ctx.fillStyle = amount > 0.45 ? "#1f4fff" : "#8ea8ff";
          const threshold = amount > 0.45 ? (amount - 0.3) / 0.7 : amount / 0.45;
          for (let j = 0; j < sub; j++)
            for (let i = 0; i < sub; i++) {
              const b = sub === 4 ? BAYER4[j * 4 + i] : sub === 2 ? BAYER2[j * 2 + i] : 0.5;
              if (b < threshold) ctx.fillRect(Math.floor(left + i * step), Math.floor(top + j * step), Math.ceil(step), Math.ceil(step));
            }
        }
      // faint grid dots on cell corners
      if (cell >= 10) {
        ctx.fillStyle = "rgba(10,26,74,.18)";
        for (let y = 0; y <= h; y++) for (let x = 0; x <= w; x++) ctx.fillRect(x * cell, y * cell, 1, 1);
      }

      const structures = [
        ...replay.players.map((p) => ({ ...p.factory_location, owner: p.player_id, yard: true })),
        ...state.dropoffs.map((d) => ({ ...d, yard: false })),
      ];
      for (const s of structures) {
        if (!visible(s.x, s.y)) continue;
        const left = s.x * cell,
          top = s.y * cell,
          u = Math.max(1, Math.floor(cell / 8));
        ctx.fillStyle = playerColor(s.owner);
        if (s.yard) {
          ctx.fillRect(left, top, cell, cell);
          ctx.fillStyle = PAPER;
          ctx.fillRect(left + 2 * u, top + 2 * u, cell - 4 * u, cell - 4 * u);
          ctx.fillStyle = playerColor(s.owner);
          ctx.fillRect(left + 3 * u, top + 3 * u, cell - 6 * u, cell - 6 * u);
        } else {
          for (let i = 0; i < cell; i++) {
            const d = Math.abs(i - (cell - 1) / 2);
            const span = Math.max(0, Math.round((cell / 2 - d) * 1));
            ctx.fillRect(left + Math.round(cell / 2 - span), top + i, Math.max(1, span * 2), 1);
          }
          ctx.fillStyle = PAPER;
          ctx.fillRect(left + Math.floor(cell / 2) - u, top + Math.floor(cell / 2) - u, 2 * u, 2 * u);
        }
      }

      for (const [pid, ships] of Object.entries(state.ships))
        for (const [id, ship] of Object.entries(ships)) {
          if (!visible(ship.x, ship.y)) continue;
          const before = prev?.ships[pid]?.[id];
          let dir = "n";
          if (before) {
            let dx = ship.x - before.x,
              dy = ship.y - before.y;
            if (Math.abs(dx) > 1) dx = -Math.sign(dx);
            if (Math.abs(dy) > 1) dy = -Math.sign(dy);
            dir = dx > 0 ? "e" : dx < 0 ? "w" : dy > 0 ? "s" : dy < 0 ? "n" : "n";
          }
          const left = ship.x * cell,
            top = ship.y * cell;
          const color = playerColor(Number(pid));
          if (cell < 7) {
            ctx.fillStyle = color;
            ctx.fillRect(left, top, cell, cell);
            if (ship.scout) { ctx.fillStyle = PAPER; ctx.fillRect(left+Math.floor(cell/2),top+Math.floor(cell/2),1,1); }
            continue;
          }
          const unit = Math.floor((cell - 2) / 5);
          const pad = Math.floor((cell - unit * 5) / 2);
          // ink silhouette one unit larger for contrast, then the hull
          ctx.fillStyle = color;
          (ship.scout ? SCOUT_HULL : HULL).forEach((row, y) =>
            [...row].forEach((c, x) => {
              if (c !== "#") return;
              const [rx, ry] = rotate(x, y, dir);
              ctx.fillRect(left + pad + rx * unit, top + pad + ry * unit, unit, unit);
            }),
          );
          // cargo gauge: ink pixels filling from the stern
          const capacity = ship.scout ? replay.GAME_CONSTANTS.SCOUT_CAPACITY ?? replay.GAME_CONSTANTS.MAX_ENERGY : replay.GAME_CONSTANTS.MAX_ENERGY;
          const cargo = Math.round((ship.energy / capacity) * 3);
          if (cargo > 0) {
            ctx.fillStyle = INK;
            for (let i = 0; i < cargo; i++) {
              const [rx, ry] = rotate(2, 3 - i, dir);
              ctx.fillRect(left + pad + rx * unit, top + pad + ry * unit, unit, unit);
            }
          }
        }

      for (const wreck of state.wrecks || []) {
        const left = wreck.x * cell,
          top = wreck.y * cell;
        ctx.fillStyle = "#d4321f";
        const u = Math.max(1, Math.floor(cell / 6));
        for (let i = 0; i < cell; i += u) {
          ctx.fillRect(left + i, top + i, u, u);
          ctx.fillRect(left + cell - i - u, top + i, u, u);
        }
      }

      if (selected) {
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2;
        ctx.strokeRect(selected.x * cell + 1, selected.y * cell + 1, cell - 2, cell - 2);
      }
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(box);
    return () => observer.disconnect();
  }, [replay, state, prev, perspective, selected, w, h, grid]);

  const occupants = selected
    ? Object.entries(state.ships).flatMap(([pid, ships]) =>
        Object.entries(ships)
          .filter(([, s]) => s.x === selected.x && s.y === selected.y)
          .map(([id, s]) => ({ id, owner: Number(pid), ...s })),
      )
    : [];

  return (
    <div className={cn("relative flex min-h-0 flex-col", className)}>
      <div ref={wrap} className="relative min-h-0 flex-1">
        <canvas
          ref={canvas}
          role="img"
          aria-label={`Halite 棋盘 ${w}×${h}，第 ${state.turn} 回合`}
          className={cn("absolute", interactive && "cursor-crosshair")}
          onClick={(e) => {
            if (!interactive || !geometry.cell) return;
            const rect = e.currentTarget.getBoundingClientRect();
            const x = Math.floor((e.clientX - rect.left) / geometry.cell),
              y = Math.floor((e.clientY - rect.top) / geometry.cell);
            if (x >= 0 && y >= 0 && x < w && y < h) setSelected(selected && selected.x === x && selected.y === y ? null : { x, y });
          }}
        />
      </div>
      {interactive && selected && (
        <div className="pointer-events-none absolute bottom-2 left-2 flex max-w-[calc(100%-16px)] flex-wrap items-center gap-x-3 border border-ink bg-paper px-2 py-1">
          <span className="text-ink-2">
            ({selected.x},{selected.y})
          </span>
          <span>{grid[selected.y][selected.x].reef ? "礁石" : `矿 ${number(state.halite[selected.y * w + selected.x])}`}</span>
          {occupants.map((s) => (
            <span key={s.id} style={{ color: playerColor(s.owner) }}>
              ■ #{s.id} 载 {number(s.energy)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
