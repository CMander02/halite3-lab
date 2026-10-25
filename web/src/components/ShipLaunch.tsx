import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/*
 * Rotating pixel launch scene: a different hull lifts off the pad every cycle,
 * while the moon behind it advances one phase. All shading is ordered (Bayer)
 * dithering in blue on cream — no gradients, no anti-aliasing.
 */

// Left half of each sprite including the centre column; mirrored at load time.
const HALVES: Record<string, string[]> = {
  miner: ["......k", ".....kb", "....kbw", "....kbw", "...kbbb", "...kbll", "..kbbbb", "..kbkkk", ".kbbkpp", ".kbbkpp", "kbbbkkk", "kbbbbbb", "kbkkbbb", "kk..kkk", "....k.k"],
  raider: [".......k", ".......k", "......kb", "......kw", "......kb", ".....kbl", ".....kbb", ".....kbb", "....kbbl", "...kbkbb", "..kbbkbb", ".kbbbkbb", "kbbkkkbb", "kbk..kkk", "kk...k.k"],
  hauler: ["....kkkk", "...kbbbb", "..kbwwbb", "..kbbbbb", "..kkkkkk", "..kplplp", "..kpkpkp", "..kkkkkk", "..klplpl", "..kkpkpk", "..kkkkkk", ".kbbbbbb", "kbbkbbkb", "kkkkkkkk", "..k.k..k"],
  scout: ["..kkkkk", ".kp...k", "kp..kk.", "k..k...", "...k..k", "....kkb", ".....kb", "....kbw", "....kbb", "...kbll", "...kbbb", "..kbkbb", "..kk.kk", "....k.k"],
  builder: [".......k", "......kb", ".....kbw", "..kkkkkk", "..k.k.k.", "..kkkkkk", "..k.k.k.", "..kkkkkk", "....kbbb", "...kbbll", "...kbbbb", "..kbbkkk", ".kbbk...", ".kbk....", ".kk....."],
  flagship: ["........k", ".......kb", ".......kw", "......kbw", "......kbb", ".....kbll", ".....kbbb", "....kbbbb", "...kbbkbb", "..kbbkpkb", "..kbbkpkb", ".kbbbkkkb", "kbbbbbbbb", "kbkbbkbbb", "kbkbbkbbb", "kkkkkkkkk", ".k.k..k.k"],
};

export const SHIPS = [
  { key: "miner", name: "采矿船", code: "MINER", spec: "载重 1000 · 采矿 25%", engines: [-4, 0, 4] },
  { key: "raider", name: "突击艇", code: "RAIDER", spec: "空载最轻 · 撞沉即抢矿", engines: [-6, 0, 6] },
  { key: "hauler", name: "运输舰", code: "HAULER", spec: "满仓返航 · 卸货入库", engines: [-5, -2, 2, 5] },
  { key: "scout", name: "侦察艇", code: "SCOUT", spec: "视野半径 4 · 驱散迷雾", engines: [-2, 2] },
  { key: "builder", name: "建造舰", code: "BUILDER", spec: "就地展开 · 新建落点", engines: [-5, 5] },
  { key: "flagship", name: "旗舰", code: "FLAGSHIP", spec: "八方混战 · 坐镇中军", engines: [-6, -3, 3, 6] },
];

const COLORS: Record<string, string> = { k: "#0a1a4a", b: "#1f4fff", l: "#8ea8ff", w: "#fbfaf5", p: "#dce4ff" };
const SPRITES: Record<string, string[]> = Object.fromEntries(
  Object.entries(HALVES).map(([key, half]) => [key, half.map((row) => row + [...row.slice(0, -1)].reverse().join(""))]),
);
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => (v + 0.5) / 16);
const bayer = (x: number, y: number) => BAYER[(y & 3) * 4 + (x & 3)];
const CYCLE = 5600;

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  max: number;
  smoke: boolean;
}

export default function ShipLaunch({ className, pixel = 4, onShip }: { className?: string; pixel?: number; onShip?: (index: number) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [index, setIndex] = useState(0);
  const notify = useRef(onShip);
  notify.current = onShip;

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const ctx = element.getContext("2d");
    if (!ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let width = 0,
      height = 0,
      frame = 0,
      visible = true,
      last = 0,
      shipIndex = -1;
    const start = performance.now();
    const particles: Particle[] = [];
    const stars: { x: number; y: number; phase: number; speed: number; bright: boolean }[] = [];

    const resize = () => {
      const rect = element.parentElement!.getBoundingClientRect();
      const size = rect.width < 640 ? Math.max(2, pixel - 1) : pixel;
      width = Math.max(40, Math.ceil(rect.width / size));
      height = Math.max(40, Math.ceil(rect.height / size));
      element.width = width;
      element.height = height;
      element.style.width = `${width * size}px`;
      element.style.height = `${height * size}px`;
      stars.length = 0;
      let seed = 7;
      const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
      for (let i = 0; i < (width * height) / 90; i++)
        stars.push({ x: Math.floor(rand() * width), y: Math.floor(rand() * height * 0.7), phase: rand() * 6.28, speed: 0.6 + rand() * 1.8, bright: rand() > 0.8 });
    };

    const px = (x: number, y: number, color: string) => {
      ctx.fillStyle = color;
      ctx.fillRect(Math.round(x), Math.round(y), 1, 1);
    };

    const draw = (now: number) => {
      const t = reduced ? 1900 : Math.max(0, now - start);
      const cycle = Math.floor(t / CYCLE);
      const local = t % CYCLE;
      const current = cycle % SHIPS.length;
      if (current !== shipIndex) {
        shipIndex = current;
        setIndex(current);
        notify.current?.(current);
      }
      ctx.clearRect(0, 0, width, height);
      const wide = width > 160;
      const ground = Math.floor(height * (wide ? 0.8 : 0.7));
      const padX = Math.floor(width * (wide ? 0.4 : 0.5));
      const scale = wide ? 2 : 1;

      // stars
      for (const star of stars) {
        if (star.y >= ground - 2) continue;
        const on = Math.sin(t / 1000 * star.speed + star.phase);
        if (on > 0.15) px(star.x, star.y, star.bright && on > 0.8 ? "#1f4fff" : "#8ea8ff");
      }

      // moon: phase advances one step per launch
      const mr = Math.max(8, Math.floor(Math.min(width, height) * (wide ? 0.24 : 0.17)));
      const mx = Math.floor(width * (wide ? 0.78 : 0.76));
      const my = Math.floor(height * (wide ? 0.34 : 0.5));
      const phase = ((cycle % 8) / 8 + local / CYCLE / 8) * Math.PI * 2;
      const lx = Math.sin(phase),
        lz = -Math.cos(phase);
      for (let y = -mr; y <= mr; y++)
        for (let x = -mr; x <= mr; x++) {
          const d = x * x + y * y;
          if (d > mr * mr) continue;
          const nx = x / mr,
            ny = y / mr,
            nz = Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny));
          const light = nx * lx + nz * lz * -1 + ny * 0.15;
          const gx = mx + x,
            gy = my + y;
          const crater = ((gx * 7 + gy * 13) % 23 === 0 || (gx * 5 + gy * 3) % 29 === 0) && d < mr * mr * 0.8;
          if (light > bayer(gx, gy) - 0.15) px(gx, gy, crater ? "#8ea8ff" : "#1f4fff");
          else if (bayer(gx, gy) < 0.1 || d > (mr - 1) * (mr - 1)) px(gx, gy, "#dce4ff");
        }

      // dithered planet surface
      for (let y = ground; y < height; y++) {
        const depth = (y - ground) / Math.max(1, height - ground);
        for (let x = 0; x < width; x++) {
          const b = bayer(x, y);
          if (b < 0.18 + depth * 0.62) px(x, y, depth > 0.55 && b < depth * 0.5 ? "#1f4fff" : "#8ea8ff");
        }
      }
      for (let x = 0; x < width; x++) px(x, ground, "#0a1a4a");

      // launch pad + gantry
      const padW = 15 + 10 * scale;
      for (let x = padX - padW / 2; x <= padX + padW / 2; x++) {
        px(x, ground - 1, "#0a1a4a");
        px(x, ground - 2, x % 2 ? "#0a1a4a" : "#1f4fff");
      }
      const towerX = padX - 10 - 7 * scale;
      for (let y = ground - 18 - 10 * scale; y < ground - 2; y++) {
        px(towerX, y, "#0a1a4a");
        px(towerX + 3, y, "#0a1a4a");
        if (y % 3 === 0) for (let x = towerX; x <= towerX + 3; x++) px(x, y, "#0a1a4a");
        else px(towerX + 1 + (y % 2), y, "#8ea8ff");
      }
      const top = ground - 18 - 10 * scale;
      if (Math.floor(t / 500) % 2) px(towerX + 1, top - 2, "#f2542d");
      px(towerX + 1, top - 1, "#0a1a4a");
      px(towerX + 2, top - 1, "#0a1a4a");

      // ship timeline: 0-700 materialise, 700-1900 ignition, 1900-4300 lift-off
      const ship = SHIPS[current];
      const sprite = SPRITES[ship.key];
      const sw = sprite[0].length * scale,
        sh = sprite.length * scale;
      const reveal = Math.min(1, local / 700);
      const lift = Math.max(0, local - 1900) / 1000;
      const sy = ground - 3 - sh - Math.floor((lift * lift * 18 + lift * 4) * scale);
      const shake = local > 1500 && local < 2200 ? Math.floor(local / 60) % 2 : 0;
      const sx = padX - Math.floor(sw / 2) + shake;
      if (sy + sh > -4) {
        sprite.forEach((row, y) =>
          [...row].forEach((c, x) => {
            if (c === ".") return;
            if (bayer(x, y) > reveal) return;
            ctx.fillStyle = COLORS[c];
            ctx.fillRect(sx + x * scale, sy + y * scale, scale, scale);
          }),
        );
        // tower arm retracts before lift-off
        if (local < 1700) for (let x = towerX + 4; x < sx; x++) px(x, ground - 6 - 4 * scale, "#0a1a4a");
      }

      // exhaust + smoke particles
      if (!reduced && local > 900 && local < 4600) {
        const power = local < 1900 ? 0.35 : 1;
        for (const e of ship.engines) {
          const n = power > 0.5 ? 3 : 1;
          for (let i = 0; i < n; i++)
            particles.push({ x: padX + e * scale + (Math.random() - 0.5) * scale, y: sy + sh, vx: (Math.random() - 0.5) * 0.3, vy: 0.6 + Math.random() * 1.2 * power, life: 0, max: 8 + Math.random() * 10 * power, smoke: false });
        }
        if (local > 1700 && local < 3400)
          for (let i = 0; i < 2; i++)
            particles.push({ x: padX + (Math.random() - 0.5) * 6, y: ground - 3, vx: (Math.random() < 0.5 ? -1 : 1) * (0.4 + Math.random() * 1.1), vy: -Math.random() * 0.15, life: 0, max: 30 + Math.random() * 40, smoke: true });
      }
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        p.life++;
        p.x += p.vx;
        p.y += p.vy;
        if (p.smoke) p.vx *= 0.96;
        if (!p.smoke && p.y >= ground - 3) {
          p.y = ground - 3;
          p.vy = 0;
          p.vx = (Math.random() - 0.5) * 2;
        }
        const age = p.life / p.max;
        if (age >= 1) {
          particles.splice(i, 1);
          continue;
        }
        const ix = Math.round(p.x),
          iy = Math.round(p.y);
        if (p.smoke) {
          const r = 1 + Math.floor(age * 3);
          for (let dy = -r; dy <= 0; dy++)
            for (let dx = -r; dx <= r; dx++) if (dx * dx + dy * dy <= r * r && bayer(ix + dx, iy + dy) > age * 0.9 + 0.1) px(ix + dx, iy + dy, "#dce4ff");
        } else if (bayer(ix, iy) > age * 0.85) px(ix, iy, age < 0.25 ? "#fbfaf5" : age < 0.5 ? "#8ea8ff" : "#1f4fff");
      }
      if (particles.length > 1600) particles.splice(0, particles.length - 1600);
    };

    const loop = (now: number) => {
      frame = requestAnimationFrame(loop);
      if (!visible || document.hidden || now - last < 1000 / 24) return;
      last = now;
      draw(now);
    };
    resize();
    draw(performance.now());
    const observer = new ResizeObserver(() => {
      resize();
      draw(performance.now());
    });
    observer.observe(element.parentElement!);
    const io = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting));
    io.observe(element);
    if (!reduced) frame = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      io.disconnect();
    };
  }, [pixel]);

  const ship = SHIPS[index];
  return (
    <div className={cn("relative overflow-hidden", className)}>
      <canvas ref={canvas} aria-hidden className="absolute bottom-0 left-0 [image-rendering:pixelated]" />
      <div className="sr-only" aria-live="polite">
        正在发射：{ship.name}
      </div>
    </div>
  );
}
