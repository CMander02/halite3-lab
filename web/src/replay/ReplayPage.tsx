import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Download, Next, Pause, Play, Prev, Forward, Backburger, Script } from "@nsmr/pixelart-react";
import type { Match, Replay } from "@/lib/types";
import { api, number, percent, useApi } from "@/lib/api";
import { playerColor } from "@/lib/colors";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Empty, ErrorBox, Loading, ModeLabel, PixelBar, Status, Tag } from "@/components/pixel";
import { AvatarStack, UserAvatar } from "@/components/UserAvatar";
import MatchList from "@/components/MatchList";
import { BankChart } from "@/components/charts";
import Board from "./Board";
import { normalizeReplay, series, type BoardState } from "./replay";

function Track({ states, players, last }: { states: BoardState[]; players: number; last: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !states.length) return;
    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(rect.width * ratio);
      canvas.height = Math.round(rect.height * ratio);
      const ctx = canvas.getContext("2d")!;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const W = rect.width,
        H = rect.height;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = "#edf1ff";
      ctx.fillRect(0, H / 2 - 1, W, 2);
      let max = 1;
      for (const s of states) for (let p = 0; p < players; p++) max = Math.max(max, s.banks[p] || 0);
      for (let p = 0; p < players; p++) {
        ctx.fillStyle = playerColor(p);
        for (let x = 0; x < W; x += 2) {
          const s = states[Math.min(last, Math.round((x / W) * last))];
          const y = H - 2 - Math.round(((s.banks[p] || 0) / max) * (H - 6));
          ctx.fillRect(x, y, 2, 2);
        }
      }
      ctx.fillStyle = "#d4321f";
      states.forEach((s, t) => {
        if (s.wrecks.length) ctx.fillRect(Math.round((t / Math.max(1, last)) * (W - 2)), 0, 2, Math.min(6, 1 + s.wrecks.length * 2));
      });
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [states, players, last]);
  return <canvas ref={ref} aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" />;
}

export default function ReplayPage({ id }: { id: string }) {
  const match = useApi<Match>(`/matches/${id}`, 0);
  const replay = useApi<Replay>(match.data?.has_replay ? `/matches/${id}/replay` : null);
  const recent = useApi<{ matches: Match[] }>("/matches");
  const [turn, setTurn] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const [perspective, setPerspective] = useState("all");
  const [logs, setLogs] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const frames = useMemo(() => (replay.data ? normalizeReplay(replay.data) : []), [replay.data]);
  const players = match.data?.seats.length || 0;
  const chart = useMemo(() => series(frames, players), [frames, players]);
  const last = frames.length - 1;
  const state = frames[Math.min(turn, Math.max(last, 0))];
  const prev = turn > 0 ? frames[turn - 1] : undefined;

  useEffect(() => {
    setTurn(0);
    setPlaying(false);
  }, [id]);
  useEffect(() => {
    if (frames.length) {
      setTurn(0);
      setPlaying(true);
    }
  }, [frames]);
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setTurn((t) => Math.min(last, t + 1)), 240 / speed);
    return () => window.clearInterval(timer);
  }, [playing, speed, last]);
  useEffect(() => {
    if (last >= 0 && turn >= last) setPlaying(false);
  }, [turn, last]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input:not([type=range]),textarea,select")) return;
      if (e.code === "Space") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setPlaying(false);
        setTurn((t) => Math.min(last, t + (e.shiftKey ? 10 : 1)));
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setPlaying(false);
        setTurn((t) => Math.max(0, t - (e.shiftKey ? 10 : 1)));
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [last]);

  async function loadLogs() {
    try {
      setLogs(JSON.stringify(await api<unknown>(`/matches/${id}/logs`), null, 2));
    } catch (e) {
      setMessage((e as Error).message);
    }
  }

  const m = match.data;
  const stats = m?.players || [];
  const live = m
    ? m.seats.map((seat, i) => {
        const ships = Object.values(state?.ships[i] || {});
        return { seat, i, bank: state?.banks[i] || 0, ships: ships.length, cargo: ships.reduce((s, x) => s + x.energy, 0) };
      })
    : [];
  const maxBank = Math.max(1, ...live.map((p) => p.bank));
  const order = [...live].sort((a, b) => b.bank - a.bank);
  const liveRank = new Map(order.map((p, r) => [p.i, r + 1]));
  const others = (recent.data?.matches || []).filter((x) => x.id !== id);

  const perspectiveSelect = (className: string) => (
    <select aria-label="棋盘视角" className={cn("h-7 shrink-0 cursor-pointer border border-line bg-paper px-1", className)} value={perspective} onChange={(e) => setPerspective(e.target.value)}>
      <option value="all">全图视角</option>
      {m?.seats.map((s, i) => (
        <option key={i} value={i}>
          {s.name} 的视野
        </option>
      ))}
    </select>
  );

  const header = (
    <div className="flex min-h-11 items-center gap-3 border-b border-line px-3 py-1.5 sm:px-4">
      <a href="/matches" className="flex shrink-0 items-center gap-1 text-ink-2 hover:text-blue" aria-label="返回对战记录">
        <ArrowLeft size={16} />
        <span className="hidden sm:inline">对战</span>
      </a>
      <div className="hidden min-w-0 flex-1 truncate md:block">
        {m?.seats.map((s, i) => (
          <span key={i} className="mr-2 whitespace-nowrap">
            <span style={{ color: playerColor(i) }}>■</span> {s.name}
          </span>
        ))}
      </div>
      {m && (
        <div className="mr-auto flex items-center gap-2 text-ink-2 md:hidden">
          <ModeLabel mode={m.mode} /> · 种子 {m.seed}
        </div>
      )}
      {m && (
        <div className="hidden shrink-0 items-center gap-2 lg:flex">
          <AvatarStack seats={m.seats} />
          <Tag>
            <ModeLabel mode={m.mode} />
          </Tag>
          <Tag>种子 {m.seed}</Tag>
          {replay.data && (
            <Tag>
              {replay.data.production_map.width}×{replay.data.production_map.height}
            </Tag>
          )}
        </div>
      )}
      {m?.has_replay && perspectiveSelect("max-w-[40vw] md:hidden")}
      {m?.has_replay && (
        <Button variant="ghost" size="icon-sm" asChild>
          <a href={`/api/matches/${id}/replay?download=true`} aria-label="下载回放" title="下载回放">
            <Download size={16} />
          </a>
        </Button>
      )}
    </div>
  );

  const controls = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-ink bg-paper px-3 py-2 sm:flex-nowrap sm:px-4">
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon-sm" className="max-sm:hidden" aria-label="跳到开局" onClick={() => (setTurn(0), setPlaying(false))}>
          <Backburger size={16} />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="上一回合" onClick={() => (setTurn((t) => Math.max(0, t - 1)), setPlaying(false))}>
          <Prev size={16} />
        </Button>
        <Button
          size="icon"
          aria-label={playing ? "暂停" : "播放"}
          onClick={() => {
            if (turn >= last) setTurn(0);
            setPlaying(!playing);
          }}
        >
          {playing ? <Pause size={18} /> : <Play size={18} />}
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="下一回合" onClick={() => (setTurn((t) => Math.min(last, t + 1)), setPlaying(false))}>
          <Next size={16} />
        </Button>
        <Button variant="ghost" size="icon-sm" className="max-sm:hidden" aria-label="跳到结束" onClick={() => (setTurn(last), setPlaying(false))}>
          <Forward size={16} />
        </Button>
      </div>
      <div className="flex border border-line">
        {[1, 2, 4, 8].map((v) => (
          <button key={v} aria-label={`${v} 倍速`} className={cn("h-7 w-7 cursor-pointer sm:w-8", speed === v ? "bg-ink text-paper" : "hover:bg-blue-50")} onClick={() => setSpeed(v)}>
            {v}×
          </button>
        ))}
      </div>
      <div className="order-last relative h-7 min-w-0 basis-full sm:order-none sm:basis-auto sm:flex-1">
        <Track states={frames} players={players} last={Math.max(1, last)} />
        <input
          className="scrubber relative"
          aria-label="回合进度"
          type="range"
          min={0}
          max={Math.max(0, last)}
          value={turn}
          onChange={(e) => {
            setTurn(Number(e.target.value));
            setPlaying(false);
          }}
        />
      </div>
      <span className="num ml-auto shrink-0 whitespace-nowrap sm:ml-0">
        T <span className="inline-block w-[3ch] text-right text-blue">{turn}</span>/{last}
      </span>
      {perspectiveSelect("hidden md:block")}

    </div>
  );

  const roster = (
    <div className="flex flex-col">
      {live.map(({ seat, i, bank, ships, cargo }) => {
        const final = m?.result?.stats[i];
        const s = stats.find((x) => x.seat === i);
        return (
          <div key={i} className="border-b border-line-2 px-3 py-2.5 last:border-0">
            <div className="flex items-center gap-2">
              <span className="num w-4 text-ink-3">{liveRank.get(i)}</span>
              <span className="size-3 shrink-0" style={{ background: playerColor(i) }} />
              <UserAvatar id={seat.author_id} name={seat.author || seat.name} size="sm" />
              <div className="min-w-0 flex-1">
                <div className="truncate">
                  {seat.name} <span className="text-ink-3">v{seat.version}</span>
                </div>
              </div>
              <span className="num text-right">{number(bank)}</span>
            </div>
            <PixelBar value={bank} max={maxBank} color={playerColor(i)} className="mt-1.5" />
            <div className="mt-1 flex justify-between text-ink-2">
              <span>船 {ships}</span>
              <span>载 {number(cargo)}</span>
              {s ? (
                <span title="击沉 / 被击沉 / 同归">
                  KDA {s.kills}/{s.deaths}/{s.assists}
                </span>
              ) : (
                <span>{seat.author || "平台"}</span>
              )}
              {final && turn >= last && <span className="text-blue">#{final.rank}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );

  const dataPanel = (
    <div className="flex flex-col gap-4 p-3">
      <div>
        <div className="eyebrow mb-1">银行矿量曲线</div>
        <BankChart data={chart} players={players} names={m?.seats.map((s) => s.name) || []} turn={turn} />
      </div>
      {stats.length > 0 && (
        <div className="overflow-x-auto">
          <div className="eyebrow mb-1">终局战报</div>
          <table className="ptable">
            <thead>
              <tr>
                <th>Bot</th>
                <th className="right">K/D/A</th>
                <th className="right">抢劫</th>
                <th className="right">搬运</th>
                <th className="right">圈地</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((s) => (
                <tr key={s.seat}>
                  <td>
                    <span style={{ color: playerColor(s.seat) }}>■</span> {m?.seats[s.seat]?.name}
                  </td>
                  <td className="right num">
                    {s.kills}/{s.deaths}/{s.assists}
                  </td>
                  <td className="right num">{number(s.robbed)}</td>
                  <td className="right num">{number(s.delivered)}</td>
                  <td className="right num">{percent(s.territory, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {replay.data && m && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-ink-2">
          <dt>地图</dt>
          <dd className="m-0 text-ink">
            {replay.data.production_map.width}×{replay.data.production_map.height} · 种子 {m.seed}
          </dd>
          <dt>视野半径</dt>
          <dd className="m-0 text-ink">{replay.data.GAME_CONSTANTS.VISION_RADIUS}</dd>
          <dt>碰撞</dt>
          <dd className="m-0 text-ink">轻船抢矿 · 同重沉没</dd>
          <dt>来源</dt>
          <dd className="m-0 text-ink">{m.kind === "ranked" ? "固定基准评测" : m.kind === "demo" ? "公开示例" : "私人测试"}</dd>
        </dl>
      )}
      {m?.can_view_logs && (
        <Button variant="outline" size="sm" onClick={() => void loadLogs()}>
          <Script size={14} /> 运行日志
        </Button>
      )}
    </div>
  );

  if (match.loading) return <Loading />;
  if (match.error || !m)
    return (
      <div className="mx-auto max-w-[960px] p-6">
        <ErrorBox message={match.error || "对局不存在。"} />
      </div>
    );

  return (
    <>
      <div className="flex h-[calc(100svh-52px)] min-h-[520px] flex-col sm:h-[calc(100svh-60px)] md:min-h-[480px]">
        {header}
        <div className="flex min-h-0 flex-1">
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-paper p-2 sm:p-3">
            {!m.has_replay ? (
              <Empty title={m.status === "complete" ? "回放已过保留期或不可用" : "回放尚未生成"}>
                <Status value={m.status} />
                <p>{m.error || "比赛结束后，完整轨迹会出现在这里。"}</p>
              </Empty>
            ) : replay.loading || !state ? (
              <Loading label="正在下载整局回放" />
            ) : (
              <Board replay={replay.data!} state={state} prev={prev} perspective={perspective} className="h-full" />
            )}
          </div>
          <aside className="hidden w-[340px] shrink-0 flex-col border-l border-line md:flex lg:w-[380px]">
            <Tabs defaultValue="live" className="flex min-h-0 flex-1 flex-col gap-0">
              <TabsList className="m-2 w-[calc(100%-16px)]">
                <TabsTrigger value="live">战况</TabsTrigger>
                <TabsTrigger value="data">数据</TabsTrigger>
                <TabsTrigger value="recent">近期</TabsTrigger>
              </TabsList>
              <TabsContent value="live" className="thin-scroll min-h-0 overflow-y-auto">
                {roster}
              </TabsContent>
              <TabsContent value="data" className="thin-scroll min-h-0 overflow-y-auto">
                {dataPanel}
              </TabsContent>
              <TabsContent value="recent" className="thin-scroll min-h-0 overflow-y-auto">
                <MatchList matches={others.slice(0, 12)} compact />
              </TabsContent>
            </Tabs>
          </aside>
        </div>
        {/* phone: compact live strip so the whole battle fits on one screen */}
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 border-t border-line px-3 py-1.5 md:hidden">
          {order.map(({ seat, i, bank, ships }) => (
            <div key={i} className="flex min-w-0 items-center gap-1.5">
              <span className="size-2.5 shrink-0" style={{ background: playerColor(i) }} />
              <span className="min-w-0 flex-1 truncate">{seat.name}</span>
              <span className="num">{number(bank)}</span>
              <span className="num w-6 text-right text-ink-3">{ships}</span>
            </div>
          ))}
        </div>
        {m.has_replay && state && controls}
      </div>
      <ErrorBox message={replay.error || message} />
      <div className="mx-auto grid max-w-[1440px] gap-6 px-3 py-6 sm:px-6 md:grid-cols-[1fr_1fr]">
        <section className="md:hidden">
          <div className="eyebrow mb-2">战况与数据</div>
          <div className="pixel-frame">{roster}</div>
          <div className="pixel-frame mt-3">{dataPanel}</div>
        </section>
        <section className="md:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <div className="eyebrow">近期对战</div>
            <a href="/matches" className="text-blue">
              全部记录 &gt;
            </a>
          </div>
          <div className="pixel-frame">
            <MatchList matches={others.slice(0, 8)} />
          </div>
        </section>
      </div>
      <Dialog open={logs !== null} onOpenChange={(open) => !open && setLogs(null)}>
        <DialogContent className="max-w-3xl border border-ink bg-paper">
          <DialogTitle className="font-normal">运行日志</DialogTitle>
          <pre className="thin-scroll max-h-[60vh] overflow-auto bg-paper-2 p-3 text-[12px] whitespace-pre-wrap">{logs}</pre>
        </DialogContent>
      </Dialog>
    </>
  );
}
