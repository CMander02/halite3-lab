import { useEffect, useRef, useState } from "react";
import type { Replay } from "./types";
import type { BoardState } from "./replay";
import { wrappedDistance } from "./replay";
import { colors, number } from "./api";
export default function Board({
  replay,
  state,
  perspective = "all",
}: {
  replay: Replay;
  state: BoardState;
  perspective?: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [selected, setSelected] = useState<{ x: number; y: number } | null>(
    null,
  );
  const { width: w, height: h, grid } = replay.production_map;
  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const draw = () => {
      const rect = element.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      element.width = Math.round(rect.width * ratio);
      element.height = Math.round(rect.height * ratio);
      const ctx = element.getContext("2d");
      if (!ctx) return;
      ctx.scale(ratio, ratio);
      const width = rect.width,
        height = rect.height,
        pad = 28,
        gw = width - pad - 12,
        gh = height - pad - 12,
        cw = gw / w,
        ch = gh / h;
      ctx.fillStyle = "#06222e";
      ctx.fillRect(0, 0, width, height);
      const player = Number(perspective);
      const sources =
        perspective === "all"
          ? []
          : [
              ...Object.values(state.ships[player] || {}),
              ...replay.players
                .filter((p) => p.player_id === player)
                .map((p) => p.factory_location),
              ...state.dropoffs.filter((d) => d.owner === player),
            ];
      const visible = (x: number, y: number) =>
        perspective === "all" ||
        sources.some(
          (s) =>
            wrappedDistance(x, y, s.x, s.y, w, h) <=
            replay.GAME_CONSTANTS.VISION_RADIUS,
        );
      for (let y = 0; y < h; y++)
        for (let x = 0; x < w; x++) {
          const left = pad + x * cw,
            top = pad + y * ch,
            known = visible(x, y);
          ctx.fillStyle = known ? "#0a2b38" : "#071720";
          ctx.fillRect(left, top, cw, ch);
          if (known && state.halite[y * w + x] > 0) {
            const alpha = Math.min(
              0.84,
              0.09 + (state.halite[y * w + x] / 900) * 0.75,
            );
            ctx.fillStyle = `rgba(58,212,167,${alpha})`;
            ctx.fillRect(
              left + cw * 0.12,
              top + ch * 0.12,
              cw * 0.76,
              ch * 0.76,
            );
          }
          if (grid[y][x].reef) {
            ctx.fillStyle = known ? "#536977" : "#354652";
            ctx.fillRect(left + 1, top + 1, cw - 2, ch - 2);
            ctx.strokeStyle = "#7d8b93";
            ctx.beginPath();
            ctx.moveTo(left + cw * 0.2, top + ch * 0.2);
            ctx.lineTo(left + cw * 0.8, top + ch * 0.8);
            ctx.stroke();
          }
          ctx.strokeStyle = "rgba(105,151,167,.17)";
          ctx.lineWidth = 0.6;
          ctx.strokeRect(left, top, cw, ch);
        }
      ctx.font = "10px ui-monospace,monospace";
      ctx.fillStyle = "#b8c8d0";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (let x = 0; x < w; x += w <= 32 ? 2 : 4)
        ctx.fillText(String(x), pad + (x + 0.5) * cw, 14);
      for (let y = 0; y < h; y += h <= 32 ? 2 : 4)
        ctx.fillText(String(y), 13, pad + (y + 0.5) * ch);
      for (const base of [
        ...replay.players.map((p) => ({
          ...p.factory_location,
          owner: p.player_id,
        })),
        ...state.dropoffs,
      ]) {
        if (!visible(base.x, base.y)) continue;
        const left = pad + base.x * cw,
          top = pad + base.y * ch;
        ctx.strokeStyle = colors[base.owner % 8];
        ctx.lineWidth = 1.8;
        ctx.strokeRect(left + 1, top + 1, cw - 2, ch - 2);
        ctx.fillStyle = colors[base.owner % 8];
        ctx.globalAlpha = 0.25;
        ctx.fillRect(left + cw * 0.22, top + ch * 0.22, cw * 0.56, ch * 0.56);
        ctx.globalAlpha = 1;
      }
      for (const [pid, ships] of Object.entries(state.ships))
        for (const ship of Object.values(ships)) {
          if (!visible(ship.x, ship.y)) continue;
          const x = pad + (ship.x + 0.5) * cw,
            y = pad + (ship.y + 0.5) * ch;
          const r = Math.max(3, Math.min(cw, ch) * 0.37);
          ctx.save();
          ctx.translate(x, y);
          ctx.fillStyle = colors[Number(pid) % 8];
          ctx.strokeStyle = "#e4fff7";
          ctx.lineWidth = 0.7;
          ctx.beginPath();
          ctx.moveTo(0, -r);
          ctx.lineTo(r * 0.8, r * 0.8);
          ctx.lineTo(0, r * 0.45);
          ctx.lineTo(-r * 0.8, r * 0.8);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
          if (ship.energy > 0) {
            ctx.strokeStyle = colors[Number(pid) % 8];
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            ctx.arc(
              r * 0.8,
              -r * 0.6,
              Math.max(1.5, (ship.energy / 1000) * r * 0.6),
              0,
              2 * Math.PI,
            );
            ctx.stroke();
          }
          ctx.restore();
        }
      if (selected) {
        ctx.strokeStyle = "#f8dc87";
        ctx.lineWidth = 2;
        ctx.strokeRect(
          pad + selected.x * cw + 0.5,
          pad + selected.y * ch + 0.5,
          cw - 1,
          ch - 1,
        );
      }
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(element);
    return () => observer.disconnect();
  }, [replay, state, perspective, selected, w, h, grid]);
  const occupant = selected
    ? Object.entries(state.ships).flatMap(([pid, ships]) =>
        Object.entries(ships)
          .filter(([, s]) => s.x === selected.x && s.y === selected.y)
          .map(([id, s]) => ({ id, owner: Number(pid), ...s })),
      )
    : [];
  return (
    <div className="board-wrap">
      <canvas
        ref={canvas}
        role="img"
        aria-label={`Halite 棋盘，${w} 乘 ${h}，第 ${state.turn} 回合。点击格子查看信息。`}
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const x = Math.floor(
              (e.clientX - rect.left - 28) / ((rect.width - 40) / w),
            ),
            y = Math.floor(
              (e.clientY - rect.top - 28) / ((rect.height - 40) / h),
            );
          if (x >= 0 && y >= 0 && x < w && y < h) setSelected({ x, y });
        }}
      />
      <div className="board-legend">
        <span>
          <i style={{ background: "#42bd96" }} />
          矿量
        </span>
        <span>
          <i style={{ background: "#536977" }} />
          礁石
        </span>
        <span>△ 船只 · □ 基地</span>
      </div>
      <div className="board-inspection">
        {selected ? (
          <>
            <span className="mono">
              ({selected.x}, {selected.y})
            </span>
            <span>
              {grid[selected.y][selected.x].reef
                ? "礁石"
                : `地面矿 ${number(state.halite[selected.y * w + selected.x])}`}
            </span>
            {occupant.map((s) => (
              <span key={s.id} style={{ color: colors[s.owner] }}>
                {replay.players.find((p) => p.player_id === s.owner)?.name} ·
                载矿 {number(s.energy)}
              </span>
            ))}
          </>
        ) : (
          <span>点击棋盘格子查看矿量和船只</span>
        )}
      </div>
    </div>
  );
}
