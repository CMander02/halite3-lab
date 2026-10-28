import { useState } from "react";
import { Upload, Play, Trophy, Eye, Grid, Zap, Drop, ChevronsVertical, Download, Ship } from "@nsmr/pixelart-react";
import { IconTile, type Tone } from "@/components/glyphs";
import type { BoardEntry, LeaderEntry, Match, Summary, User } from "@/lib/types";
import { compact, number, useApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Empty, Loading, Panel, Stat, TierBadge } from "@/components/pixel";
import ShipLaunch, { SHIPS } from "@/components/ShipLaunch";
import MatchList from "@/components/MatchList";
import { DailyChart } from "@/components/charts";
import { UserAvatar } from "@/components/UserAvatar";

const RULES: { icon: typeof Eye; tone: Tone; title: string; text: string }[] = [
  { icon: Eye, tone: "ink", title: "迷雾视野", text: "每艘船、基地与落点照亮半径 4 的曼哈顿范围，其余海域不可见。" },
  { icon: Grid, tone: "green", title: "对称礁石", text: "按出生分区对称生成，保持海域连通；撞礁等于原地停留。" },
  { icon: Zap, tone: "gold", title: "轻船抢矿", text: "相撞时唯一最轻的船存活，并夺走被击沉船的全部货物。" },
  { icon: Drop, tone: "orange", title: "同重沉没", text: "最轻重量并列时同归于尽，货物原地落成地面矿；4 人场 3 艘以上同格相撞也一起沉没变矿。" },
];

const STEPS = [
  { icon: Upload, title: "上传 Bot", text: "仅支持 C++17 单文件或 C++ ZIP。每个版本不可覆盖，源码保持私有。", href: "/bots" },
  { icon: Play, title: "提交测试", text: "1v1、4 人、8 人循环赛，座位轮换。离开网页也会继续执行。", href: "/tests" },
  { icon: Trophy, title: "回放与排名", text: "逐回合拖动回放；参加固定基准评测后进入公开 Tier 与子榜。", href: "/leaderboard" },
];

export default function Overview({ user }: { user: User | null }) {
  const summary = useApi<Summary>("/summary", 30000);
  const matches = useApi<{ matches: Match[]; total: number }>("/matches", 15000);
  const board = useApi<{ entries: LeaderEntry[] }>("/leaderboard");
  const stats = useApi<{ entries: BoardEntry[] }>("/leaderboard/stats");
  const [shipIndex, setShipIndex] = useState(0);
  const ship = SHIPS[shipIndex];
  const s = summary.data;
  const topKda = [...(stats.data?.entries || [])].sort((a, b) => b.kda - a.kda)[0];
  const topRob = [...(stats.data?.entries || [])].sort((a, b) => b.robbed - a.robbed)[0];

  return (
    // the home page is set entirely in Source Han Sans; shared components drop their pixel accents here
    <div className="all-sans">
      {/* hero: four-corner composition around the launch pad */}
      <section className="relative h-[min(86svh,720px)] min-h-[520px] overflow-hidden border-b border-line">
        <ShipLaunch className="absolute inset-0" onShip={setShipIndex} />
        <div className="pointer-events-none relative mx-auto flex h-full max-w-[1440px] flex-col px-4 pt-6 pb-6 sm:px-6 sm:pt-10">
          <div className="rise max-w-[640px]">
            <div className="eyebrow mb-3">Bot 对战实验室 · 群赛</div>
            <h1 className="m-0 text-[48px] leading-[52px] font-bold tracking-tight sm:text-[72px] sm:leading-[76px]">
              HALITE <span className="text-blue">III</span>
              <br />
              ARENA
            </h1>
            <p className="mt-4 mb-0 text-[24px] leading-[30px] text-ink">在迷雾与礁石之间，让策略启航。</p>
          </div>
          <div className="mt-auto flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="rise rise-2 pointer-events-auto w-fit bg-ink px-3 py-2 text-paper">
              <div className="text-blue-300">
                &lt;&lt;&lt; LAUNCH {String(shipIndex + 1).padStart(2, "0")} · {ship.code}
              </div>
              <div className="text-[24px] leading-[28px]">{ship.name}</div>
              <div className="text-ink-3">{ship.spec}</div>
            </div>
            <div className="rise rise-3 pointer-events-auto flex flex-col items-start gap-3 lg:items-end">
              <div className="hidden bg-paper/85 px-2 text-right text-[36px] leading-[40px] lg:block">
                Build your bot.
                <br />
                <span className="text-blue">Watch it sail.</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="lg" asChild>
                  <a href={user ? "/bots" : "/register"}>
                    <Upload size={16} /> {user ? "上传新版本" : "创建账号"} &gt;
                  </a>
                </Button>
                <Button size="lg" variant="outline" className="bg-paper/80" asChild>
                  <a href="/matches">&lt;&lt;&lt; 观看回放</a>
                </Button>
              </div>
            </div>
          </div>
          <div className="float-hint absolute bottom-3 left-1/2 hidden -translate-x-1/2 flex-col items-center bg-paper px-2 text-ink-2 lg:flex">
            <ChevronsVertical size={16} />
            滑动开启探索
          </div>
        </div>
      </section>

      <div className="mx-auto flex max-w-[1440px] flex-col gap-10 px-4 py-10 sm:px-6">
        {/* stats: five columns with the daily chart breaking the rhythm */}
        <section>
          <div className="eyebrow mb-4">航行日志</div>
          <div className="grid grid-cols-2 gap-x-5 gap-y-6 md:grid-cols-3 xl:grid-cols-5">
            <Stat label="完成对局" value={s ? compact(s.matches) : "—"} hint={s ? `${s.pending} 场排队中` : undefined} />
            <Stat label="参赛 Bot" value={s ? number(s.bots) : "—"} hint={s ? `${s.versions} 个不可变版本` : undefined} />
            <div className="hairline-top col-span-2 pt-3 md:col-span-1 md:row-span-1">
              {s ? <DailyChart data={s.daily} /> : <Loading />}
              <div className="text-ink">近 14 天完成对局</div>
            </div>
            <Stat label="船长" value={s ? number(s.users) : "—"} hint="注册用户" />
            <Stat label="击沉" value={s ? compact(s.wrecks) : "—"} hint={s ? `搬运 ${compact(s.delivered)} 矿` : undefined} />
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
          <Panel
            title="近期对战"
            icon={Ship}
            tone="blue"
            action={
              <a href="/matches" className="text-blue">
                全部 &gt;
              </a>
            }
            bodyClassName="p-0"
          >
            {matches.loading ? <Loading /> : <MatchList matches={(matches.data?.matches || []).slice(0, 6)} />}
          </Panel>
          <div className="flex flex-col gap-6">
            <Panel
              title="Tier 榜"
              icon={Trophy}
              tone="gold"
              action={
                <a href="/leaderboard?view=tier" className="text-blue">
                  排行 &gt;
                </a>
              }
              bodyClassName="p-0"
            >
              {board.data?.entries.length ? (
                board.data.entries.slice(0, 5).map((e, i) => (
                  <div key={e.version_id} className="flex items-center gap-3 border-b border-line-2 px-4 py-2.5 last:border-0">
                    <span className="num w-5 text-ink-3">{String(i + 1).padStart(2, "0")}</span>
                    <TierBadge tier={e.tier} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate">
                        {e.bot_name} <span className="text-ink-3">v{e.version}</span>
                      </div>
                      <div className="truncate text-ink-3">{e.author}</div>
                    </div>
                    <span className="num">{(e.win_rate * 100).toFixed(0)}%</span>
                  </div>
                ))
              ) : (
                <Empty title="等待第一个参评版本" />
              )}
            </Panel>
            <div className="grid grid-cols-2 gap-3">
              {[
                { title: "KDA 王", view: "kda", entry: topKda, value: topKda ? topKda.kda.toFixed(2) : "—" },
                { title: "抢劫王", view: "robbed", entry: topRob, value: topRob ? compact(topRob.robbed) : "—" },
              ].map(({ title, view, entry, value }) => (
                <a key={title} href={`/leaderboard?view=${view}`} className="pixel-frame ticks block p-3 hover:bg-blue-50">
                  <div className="text-ink-2">{title}</div>
                  <div className="num text-[24px] leading-[30px] text-blue">{value}</div>
                  {entry && (
                    <div className="mt-1 flex items-center gap-1.5">
                      <UserAvatar id={entry.author_id} name={entry.author} size="sm" />
                      <span className="truncate">{entry.bot_name}</span>
                    </div>
                  )}
                </a>
              ))}
            </div>
          </div>
        </div>

        <section>
          <div className="eyebrow mb-4">本赛季规则</div>
          <div className="grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
            {RULES.map(({ icon, tone, title, text }) => (
              <div key={title} className="bg-paper-2 p-4">
                <IconTile icon={icon} tone={tone} size={24} />
                <div className="mt-3 text-[18px] font-bold">{title}</div>
                <p className="mt-1 mb-0 text-ink-2">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section>
          <div className="eyebrow mb-4">起航流程</div>
          <ol className="m-0 grid list-none gap-6 p-0 md:grid-cols-3">
            {STEPS.map(({ icon: Icon, title, text, href }, i) => (
              <li key={title} className="relative">
                {i < STEPS.length - 1 && <div className="absolute top-6 left-14 hidden h-0 w-[calc(100%-32px)] border-t-2 border-dashed border-blue-300 md:block" />}
                <a href={href} className="group relative flex flex-col gap-2">
                  <span className="relative flex size-12 items-center justify-center border-2 border-ink bg-blue-50 text-blue group-hover:bg-blue group-hover:text-white">
                    <Icon size={24} />
                    <span className="absolute -top-2 -right-2 bg-ink px-1 text-[13px] leading-[18px] text-paper">{i + 1}</span>
                  </span>
                  <span className="mt-1 text-[18px] font-bold">{title}</span>
                  <span className="text-ink-2">{text}</span>
                </a>
              </li>
            ))}
          </ol>
          <div className="mt-6 flex flex-wrap gap-2">
            <Button variant="outline" size="sm" asChild>
              <a href="/sample-cpp.zip">
                <Download size={14} /> C++ 示例
              </a>
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}
