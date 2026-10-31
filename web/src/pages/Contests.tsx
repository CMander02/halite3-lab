import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Trophy, Calendar, Clock, Download, Upload, Lock, Plus, Play, Check, Reload, Trash, ArrowLeft, ArrowRight, Flag, Bullseye, Hidden, Copy, Archive, Article, Script, Server, Analytics, BookOpen, Command, Sliders, List, Scale } from "@nsmr/pixelart-react";
import { Glyph, glyphIcon } from "@/components/glyphs";
import type { Bot, CatalogKind, Contest, ContestConfig, ContestEntry, ContestStatus, ContestSummary, Standings, StandingRow, User } from "@/lib/types";
import { api, date, number, percent, useApi } from "@/lib/api";
import { navigate } from "@/lib/router";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import RuleExperiments from "./RuleExperiments";
import { Empty, ErrorBox, Loading, ModeLabel, PageHead, Panel, Status, Tag } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";
import { CatalogSelect, SetupCells, correctionLabel, useCatalog } from "@/components/ModelBadge";
import { Markdown } from "@/components/Markdown";
import MatchBrowser from "@/components/MatchBrowser";
import { TierBoard } from "@/components/TierBoard";

const MapGlyph = glyphIcon("map", false);

const STATUS: Record<ContestStatus, { label: string; tone: string }> = {
  draft: { label: "草稿", tone: "border-line text-ink-3" },
  upcoming: { label: "即将开始", tone: "border-ink text-ink" },
  open: { label: "提交中", tone: "border-blue bg-blue text-white" },
  closed: { label: "正式评测中", tone: "border-warn text-warn" },
  finished: { label: "已结束", tone: "border-ink bg-ink text-paper" },
};
const LANG: Record<string, string> = { cpp: "C++17", python: "Python" };

function StatusTag({ status }: { status: ContestStatus }) {
  return <Tag className={STATUS[status].tone}>{STATUS[status].label}</Tag>;
}

/** "3 天 4 小时" / "25 分钟" until (or since) a timestamp. */
function span(seconds: number) {
  const s = Math.abs(seconds);
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} 分钟`;
  if (s < 86400) return `${Math.floor(s / 3600)} 小时 ${Math.floor((s % 3600) / 60)} 分`;
  return `${Math.floor(s / 86400)} 天 ${Math.floor((s % 86400) / 3600)} 小时`;
}

function useNow(interval = 30000) {
  const [value, setValue] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = window.setInterval(() => setValue(Date.now() / 1000), interval);
    return () => window.clearInterval(id);
  }, [interval]);
  return value;
}

function Countdown({ contest }: { contest: ContestSummary }) {
  const t = useNow();
  if (contest.practice) return <span>常驻测试赛 · 随时提交，不截止</span>;
  if (contest.status === "upcoming") return <span>{span(contest.open_at - t)}后开放提交</span>;
  if (contest.status === "open") return <span className="text-blue">距截止 {span(contest.close_at - t)}</span>;
  if (contest.status === "closed") return <span>提交已截止，正式评测进行中</span>;
  if (contest.status === "finished") return <span>结果已于 {date(contest.finalized_at!)} 公布</span>;
  return <span className="text-ink-3">未发布</span>;
}

export default function Contests({ user, slug, tab }: { user: User | null; slug?: string; tab?: string }) {
  if (slug === "new") return user?.is_admin ? <ContestEditor onDone={(id) => navigate(`/contests/${id}`)} /> : <Empty title="只有管理员可以创建比赛" />;
  if (slug) return <ContestDetail user={user} slug={slug} tab={tab || "overview"} />;
  return <ContestList user={user} />;
}

function ContestList({ user }: { user: User | null }) {
  const { data, error, loading } = useApi<{ contests: ContestSummary[] }>("/contests", 60000);
  const contests = data?.contests || [];
  const order: ContestStatus[] = ["open", "upcoming", "closed", "finished", "draft"];
  return (
    <>
      <PageHead
        eyebrow="比赛"
        title="限时提交，隐藏地图定胜负"
        description="每场比赛有自己的靶子 bot、地图和提交窗口。提交期间你的 bot 只和靶子对战，得到临时 ELO；截止后所有人的最终版本在公开和隐藏地图上互相循环，结果公布后计入全局 ELO。"
        action={
          user?.is_admin && (
            <Button asChild>
              <a href="/contests/new">
                <Plus size={16} /> 新建比赛
              </a>
            </Button>
          )
        }
      />
      <ErrorBox message={error} />
      {loading ? (
        <Loading />
      ) : contests.length ? (
        <div className="flex flex-col gap-8">
          {order.map((state) => {
            const list = contests.filter((c) => c.status === state);
            if (!list.length) return null;
            return (
              <section key={state}>
                <h2 className="eyebrow mb-3">{STATUS[state].label}</h2>
                <div className="grid gap-4 md:grid-cols-2">
                  {list.map((c) => (
                    <a key={c.id} href={`/contests/${c.slug}`} className={cn("pixel-frame flex flex-col gap-3 p-4 hover:border-ink", c.status === "open" && "ticks")}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-[24px] leading-[28px]">
                            <span className="text-blue">#{c.number}</span> {c.title}
                          </div>
                          <div className="mt-1 text-ink-2">{c.summary || "—"}</div>
                        </div>
                        <StatusTag status={c.status} />
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {c.modes.map((m) => (
                          <Tag key={m}>
                            <ModeLabel mode={m} />
                          </Tag>
                        ))}
                        {c.languages.map((l) => (
                          <Tag key={l}>{LANG[l]}</Tag>
                        ))}
                      </div>
                      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-ink-2">
                        <span className="flex items-center gap-1.5">
                          <Calendar size={14} /> {date(c.open_at)} → {date(c.close_at)}
                        </span>
                        <span className="num">
                          {c.participants} 人 · {c.submissions} 次提交
                          {c.my_submissions ? <span className="text-blue"> · 我 {c.my_submissions}</span> : null}
                        </span>
                      </div>
                      <div className="text-ink-2">
                        <Countdown contest={c} />
                      </div>
                    </a>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <Empty title="还没有比赛">{user?.is_admin ? "点击“新建比赛”创建第一场。" : "管理员发布比赛后会出现在这里。"}</Empty>
      )}
    </>
  );
}

function ContestDetail({ user, slug, tab }: { user: User | null; slug: string; tab: string }) {
  const { data, error, loading, refresh } = useApi<Contest>(`/contests/${slug}`, 30000);
  // every tab has its own URL: /contests/<slug>/<tab>
  const setTab = (next: string) => navigate(`/contests/${slug}${next === "overview" ? "" : `/${next}`}`, true);
  if (loading) return <Loading />;
  if (!data) return <ErrorBox message={error || "比赛不存在。"} />;
  const c = data;
  const tabs = ["overview", "standings", ...(c.practice ? ["tier"] : []), ...(c.experimental ? ["experiments"] : []), "matches", "rules", ...(user ? ["mine"] : []), ...(user?.is_admin ? ["admin"] : [])];
  const active = tabs.includes(tab) ? tab : "overview";
  return (
    <>
      <a href="/contests" className="mb-4 inline-flex items-center gap-1 text-ink-2 hover:text-blue">
        <ArrowLeft size={14} /> 全部比赛
      </a>
      <PageHead
        eyebrow="比赛"
        title={
          <>
            <span className="text-blue">#{c.number}</span> {c.title}
          </>
        }
        description={
          <>
            {c.summary && <span className="mb-2 block">{c.summary}</span>}
            <span className="flex flex-wrap items-center gap-2">
              <StatusTag status={c.status} /> <Countdown contest={c} />
            </span>
          </>
        }
        action={
          <>
            <Button variant="outline" asChild>
              <a href={`/api/contests/${c.slug}/kit.zip`} download>
                <Archive size={16} /> 下载题目包
              </a>
            </Button>
            {c.status === "open" && user && (
              <Button onClick={() => setTab("mine")}>
                <Upload size={16} /> 提交 bot.cpp
              </Button>
            )}
          </>
        }
      />
      <ErrorBox message={error} />
      <Tabs value={active} onValueChange={setTab} className="gap-6">
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <TabsList className="h-10">
            <TabsTrigger value="overview" className="px-4">
              <Flag size={14} /> 概览
            </TabsTrigger>
            <TabsTrigger value="standings" className="px-4">
              <Scale size={14} /> 排行
            </TabsTrigger>
            {c.practice && (
              <TabsTrigger value="tier" className="px-4">
                <Trophy size={14} /> Tier
              </TabsTrigger>
            )}
            <TabsTrigger value="matches" className="px-4">
              <List size={14} /> 对局
            </TabsTrigger>
            {c.experimental && <TabsTrigger value="experiments" className="px-4">规则实验</TabsTrigger>}
            <TabsTrigger value="rules" className="px-4">
              <BookOpen size={14} /> 规则
            </TabsTrigger>
            {user && (
              <TabsTrigger value="mine" className="px-4">
                <Upload size={14} /> 我的提交{c.my_submissions ? ` · ${c.my_submissions}` : ""}
              </TabsTrigger>
            )}
            {user?.is_admin && (
              <TabsTrigger value="admin" className="px-4">
                <Lock size={14} /> 管理
              </TabsTrigger>
            )}
          </TabsList>
        </div>
        <TabsContent value="overview">
          <Overview contest={c} />
        </TabsContent>
        {c.practice && <TabsContent value="tier">{active === "tier" && <TierBoard />}</TabsContent>}
        <TabsContent value="matches">{active === "matches" && <MatchBrowser user={user} contest={c.slug} modes={c.practice ? [2, 4, 8] : c.modes} />}</TabsContent>
        <TabsContent value="rules">
          <Panel title="比赛规则" icon={BookOpen} tone="blue" ticks>
            <Markdown text={c.rules_text} skipTitle />
          </Panel>
        </TabsContent>
        <TabsContent value="standings">{active === "standings" && <StandingsView contest={c} user={user} />}</TabsContent>
        {c.experimental && <TabsContent value="experiments">{active === "experiments" && <RuleExperiments slug={c.slug} />}</TabsContent>}
        {user && <TabsContent value="mine">{active === "mine" && <MyEntries contest={c} user={user} onChange={refresh} />}</TabsContent>}
        {user?.is_admin && (
          <TabsContent value="admin">
            <AdminPanel contest={c} onChange={refresh} />
          </TabsContent>
        )}
      </Tabs>
    </>
  );
}

function Timeline({ contest: c }: { contest: Contest }) {
  const t = useNow();
  const steps: [string, number | null, ReactNode][] = [
    ["开放浏览", c.visible_at, "题目、地图和靶子公开，可以下载靶子本地测试"],
    ["开放提交", c.open_at, `每次提交与靶子在公开地图上打 ${c.bench_games} 场，得到临时 ELO`],
    ["提交截止", c.close_at, "以每人选定（默认最后一次）的提交参加正式评测"],
    ["正式评测", c.final_started_at, "全部最终版本 + 靶子互相对战，包含隐藏地图"],
    ["公布结果", c.finalized_at, "排名冻结，全部对局和回放公开，计入全局 ELO"],
  ];
  if (c.practice) {
    steps.splice(2);
    steps[1][2] = `每次提交与靶子打 ${c.bench_games} 场，立即公开并计入全局 ELO`;
  }
  return (
    <ol className="m-0 flex list-none flex-col p-0">
      {steps.map(([label, at, note], i) => {
        const done = at !== null && at <= t;
        return (
          <li key={label} className="relative flex gap-3 pb-4 last:pb-0">
            <span className={cn("notch mt-0.5 flex size-5 shrink-0 items-center justify-center text-[11px]", done ? "bg-blue text-white" : "border border-line text-ink-3")}>{i + 1}</span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className={done ? "text-ink" : "text-ink-2"}>{label}</span>
                <span className="num text-ink-3">{at ? date(at) : i >= 3 ? "截止后自动进行" : "发布即开放"}</span>
              </div>
              <div className="text-ink-3">{note}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function BotRow({ bot, slug, role }: { bot: Contest["targets"][number]; slug: string; role: string }) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-line-2 py-2 last:border-0">
      <UserAvatar size="sm" name={bot.author} />
      <div className="min-w-0 flex-1">
        <div>
          {bot.bot_name} <span className="text-ink-3">v{bot.version}</span> <Tag>{role}</Tag> <Tag>{LANG[bot.language] || bot.language}</Tag>
        </div>
        <div className="truncate text-ink-3">{bot.notes || bot.author}</div>
      </div>
      {bot.downloadable ? (
        <Button variant="outline" size="sm" asChild>
          <a href={`/api/contests/${slug}/downloads/${bot.version_id}`} download>
            <Download size={14} /> 下载
          </a>
        </Button>
      ) : (
        <span className="flex items-center gap-1 text-ink-3">
          <Lock size={14} /> 仅云端
        </span>
      )}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      size="sm"
      variant="outline"
      onClick={() =>
        void navigator.clipboard.writeText(text).then(() => {
          setDone(true);
          window.setTimeout(() => setDone(false), 1500);
        })
      }
    >
      {done ? <Check size={14} /> : <Copy size={14} />} {done ? "已复制" : "复制"}
    </Button>
  );
}

function Overview({ contest: c }: { contest: Contest }) {
  const extra = c.downloads.filter((d) => !c.targets.some((t) => t.version_id === d.version_id) && d.version_id !== c.base?.version_id);
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-6">
          {c.description && (
            <Panel title="比赛说明" icon={Article}>
              <div className="leading-[22px] whitespace-pre-wrap">{c.description}</div>
            </Panel>
          )}
          <Panel
            title="题目 Prompt"
            icon={Script}
            tone="ink"
            action={
              <span className="flex gap-2">
                <CopyButton text={c.prompt_text} />
                <Button size="sm" asChild>
                  <a href={`/api/contests/${c.slug}/kit.zip`} download>
                    <Archive size={14} /> 题目包
                  </a>
                </Button>
              </span>
            }
          >
            <div className="max-h-[420px] overflow-y-auto pr-2">
              <Markdown text={c.prompt_text} skipTitle />
            </div>
            <p className="mt-3 mb-0 border-t border-line pt-3 text-ink-3">
              题目包（ZIP）：PROMPT.md、RULES.md、协议、公开地图（种子、规则文件和渲染好的地形 / 矿量）、参考 bot 源码、C++ 起点 <code>starter/bot.cpp</code> 和提交用的 <code>tools/client.py</code>。可以整包交给 Agent；也可以让 Agent 读{" "}
              <a className="text-blue" href={`/api/contests/${c.slug}/prompt.md`} target="_blank" rel="noreferrer">
                prompt.md
              </a>
              。
            </p>
          </Panel>
          <Panel title="地图" icon={MapGlyph} tone="gold" bodyClassName="p-0 overflow-x-auto">
            <table className="ptable">
              <thead>
                <tr>
                  <th>模式</th>
                  <th>地图</th>
                  <th className="right">回合</th>
                  <th className="right">单场时限</th>
                  <th>公开地图（种子）</th>
                  <th>隐藏地图</th>
                </tr>
              </thead>
              <tbody>
                {c.modes.map((m) => {
                  const map = c.maps[String(m)];
                  return (
                    <tr key={m}>
                      <td>
                        <ModeLabel mode={m} />
                      </td>
                      <td className="num">
                        {map.width}×{map.height}
                      </td>
                      <td className="right num">{map.turns}</td>
                      <td className="right num">{map.seconds} 秒</td>
                      <td className="num">{map.public.join(" / ")}</td>
                      <td className="num text-ink-2">{c.practice ? "—" : map.hidden ? map.hidden.join(" / ") || "—" : map.hidden_count ? `${map.hidden_count} 张，结果公布时揭晓` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Panel>
          <Panel title="本地测试 vs 云端评测" icon={Server} tone="blue">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex gap-3">
                <Glyph name="laptop" size={40} />
                <div>
                  <div className="font-bold">本地：随便测</div>
                  <p className="mt-1 mb-0 text-ink-2">下载题目包，在公开地图上和参考 bot 对战，次数不限。{c.practice ? "" : "提交期的云端评测做的也只是这件事，先在本地调好再提交。"}</p>
                </div>
              </div>
              <div className="flex gap-3">
                <Glyph name="cloud" size={40} />
                <div>
                  <div className="font-bold">云端：{c.practice ? "公开成绩" : "只有这里能做的事"}</div>
                  <p className="mt-1 mb-0 text-ink-2">
                    {c.practice
                      ? "提交后对阵靶子的 12 场立即公开，计入全局 ELO 和 Tier；另自动加跑 4 人 / 8 人多人评测，计入全局 ELO 和多人榜。"
                      : "截止后的正式评测：对手是其他选手的最终版本（你拿不到），地图包含隐藏地图，所有人同一个沙箱和时限，并按模型 / 推理强度修正 ELO。"}
                  </p>
                </div>
              </div>
            </div>
          </Panel>
        </div>
        <div className="flex flex-col gap-6">
          <Panel title="时间线" icon={Calendar} tone="orange">
            <Timeline contest={c} />
          </Panel>
          <Panel title="靶子与参考 bot" icon={Bullseye} tone="orange">
            {c.base && !c.targets.some((t) => t.version_id === c.base!.version_id) && <BotRow bot={c.base} slug={c.slug} role="基础 bot" />}
            {c.targets.map((t) => (
              <BotRow key={t.version_id} bot={t} slug={c.slug} role={t.version_id === c.base?.version_id ? "靶子 · 基础 bot" : "靶子"} />
            ))}
            {extra.map((t) => (
              <BotRow key={t.version_id} bot={t} slug={c.slug} role="参考" />
            ))}
            <p className="mt-3 mb-0 text-ink-3">靶子参加每次提交的评测{c.practice ? "" : "，也参加正式评测作为基准"}，但不参与排名。</p>
          </Panel>
          <Panel title="评测进度" icon={Analytics} tone="green">
            <div className="grid grid-cols-2 gap-4">
              {(c.practice ? (["bench"] as const) : (["bench", "final"] as const)).map((stage) => {
                const p = c.progress[stage];
                return (
                  <div key={stage}>
                    <div className="text-ink-2">{stage === "bench" ? "提交评测" : "正式评测"}</div>
                    <div className="num font-pixel text-[24px] leading-[28px]">
                      {number(p.counts.complete || 0)}
                      <span className="text-ink-3">/{number(p.total)}</span>
                    </div>
                    {p.counts.queued || p.counts.running ? <div className="text-ink-3">排队 {(p.counts.queued || 0) + (p.counts.running || 0)}</div> : null}
                  </div>
                );
              })}
            </div>
          </Panel>
        </div>
      </div>
      <a href={`/contests/${c.slug}/rules`} className="pixel-frame flex items-center gap-3 p-4 hover:border-ink">
        <BookOpen size={20} className="text-blue" />
        <span className="flex-1">
          <span className="font-bold">完整比赛规则</span>
          <span className="block text-ink-2">迷雾、礁石、碰撞与抢矿、地图生成、计分与时限：所有模式的规则全文。</span>
        </span>
        <ArrowRight size={16} className="text-blue" />
      </a>
    </div>
  );
}

function StandingsView({ contest: c, user }: { contest: Contest; user: User | null }) {
  const canFinal = c.experimental || c.status === "finished" || Boolean(user?.is_admin && c.final_started_at);
  const [stage, setStage] = useState<"bench" | "final">(c.experimental || c.status === "finished" ? "final" : "bench");
  const [mode, setMode] = useState("overall");
  const [history, setHistory] = useState(false);
  const { data, error, loading } = useApi<{ standings: Standings; final: boolean; computed_at: number }>(`/contests/${c.slug}/standings?stage=${stage}`, c.status === "finished" ? 0 : 60000);
  const catalog = useCatalog();
  const rows = (data?.standings[mode] || []).filter((r) => history || r.current || r.target);
  // #0: "overall" is the 12-game 1v1 benchmark; its 4 / 8-player runs come as extra boards
  const modes = Object.keys(data?.standings || {})
    .filter((k) => k !== "overall" && !(c.practice && k === "2"))
    .map(Number)
    .sort((a, b) => a - b);
  const targets = c.targets;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Toggle
          value={stage}
          onChange={(v) => setStage(v as "bench" | "final")}
          options={[
            ["bench", c.practice ? "排名" : c.status === "finished" ? "提交期（临时）" : "临时排名"],
            ...(canFinal ? ([["final", c.status === "finished" ? "正式排名" : "正式评测（仅管理员）"]] as [string, string][]) : []),
          ]}
        />
        <Toggle value={mode} onChange={setMode} options={[["overall", c.practice ? "1v1 · 12 场基准" : "总榜"], ...modes.map((m) => [String(m), m === 2 ? "1v1" : c.practice ? `${m} 人评测` : `${m} 人`] as [string, string])]} />
        <label className="flex cursor-pointer items-center gap-2 text-ink-2">
          <input type="checkbox" checked={history} onChange={(e) => setHistory(e.target.checked)} className="size-4 accent-[var(--blue)]" /> 显示历史提交
        </label>
      </div>
      <ErrorBox message={error} />
      <div className="pixel-frame overflow-x-auto p-0">
        {loading ? (
          <Loading />
        ) : rows.length ? (
          <table className="ptable">
            <thead>
              <tr>
                <th>#</th>
                <th>Bot</th>
                <th>模型</th>
                <th>推理</th>
                <th>平台</th>
                <th className="right">原始 ELO</th>
                <th className="right">修正</th>
                <th className="right text-blue">修正后</th>
                <th className="right">胜率</th>
                <th className="right">平均名次</th>
                <th className="right">平均得分</th>
                <th className="right">场次</th>
                {stage === "final" ? (
                  <th className="right">隐藏图胜率</th>
                ) : (
                  targets.map((t) => (
                    <th key={t.version_id} className="right" title="与该靶子的名次对比得分率">
                      胜 {t.bot_name}
                    </th>
                  ))
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <StandingTr key={r.version_id} row={r} stage={stage} targets={targets.map((t) => t.version_id)} catalog={catalog} />
              ))}
            </tbody>
          </table>
        ) : (
          <Empty title={stage === "final" ? "正式评测还没有完成的对局" : "还没有完成评测的提交"}>{c.status === "open" ? "提交 bot 后，与靶子的对局完成即出现在这里。" : null}</Empty>
        )}
      </div>
      <p className="m-0 max-w-[880px] text-ink-3">
        {c.practice && mode !== "overall"
          ? `${mode} 人评测：每次提交另与 baseline、raider 和 #0 当前修正后 ELO 最高的 7 个 Bot 打多人局（48 场 4 人 + 24 场 8 人，座位轮换），单独拟合 ELO；不影响 12 场基准和 Tier。`
          : c.practice
          ? "排名来自每次提交与 baseline、raider 的 12 场对局，用 Bradley–Terry 拟合 ELO。每个 Bot 以最新一次提交排名；靶子和历史提交不占名次。这些对局同时计入全局 ELO。"
          : stage === "bench"
          ? "临时排名只来自与靶子的对局：所有提交面对同一组靶子和公开地图，用 Bradley–Terry 拟合出可比的 ELO。每人以当前选定（默认最后一次）的提交排名；靶子和历史提交不占名次。"
          : "正式排名来自截止后的循环赛：每人的最终版本与其他选手和靶子在公开 + 隐藏地图上对战（1v1 双循环换座，多人局多轮随机分组）。"}
        修正后 ELO = 原始 ELO − 模型 / 推理强度 / 平台修正，和全局 ELO 总榜相同。{data?.final ? `结果已冻结于 ${date(data.computed_at)}。` : ""}
      </p>
    </div>
  );
}

function StandingTr({ row: r, stage, targets, catalog }: { row: StandingRow; stage: string; targets: string[]; catalog: ReturnType<typeof useCatalog> }) {
  return (
    <tr className={cn(r.target && "bg-paper", !r.current && !r.target && "opacity-60")}>
      <td className={cn("num font-pixel whitespace-nowrap", r.rank && r.rank <= 3 ? "text-blue" : "text-ink-3")}>{r.rank ? String(r.rank).padStart(2, "0") : r.target ? "靶子" : "—"}</td>
      <td className="max-w-[240px]">
        <a href={`/bots/${r.bot_id}`} className="flex min-w-0 items-center gap-2 hover:text-blue">
          <UserAvatar id={r.target ? null : r.user_id} name={r.author || "平台基准"} size="sm" />
          <span className="min-w-0">
            <span className="block truncate">
              {r.bot_name} <span className="text-ink-3">v{r.version}</span>
            </span>
            <span className="block truncate text-ink-3">
              {r.target ? "靶子" : r.author}
              {r.seq ? ` · 第 ${r.seq} 次提交` : ""}
            </span>
          </span>
        </a>
      </td>
      <SetupCells attribution={r.target ? null : r.attribution} catalog={catalog} empty="不修正" />
      <td className="right num whitespace-nowrap text-ink-2">
        {Math.round(r.elo)}
        <span className="text-ink-3"> ±{Math.round(r.elo_sd)}</span>
      </td>
      <td className="right num text-ink-2">{r.target ? "—" : correctionLabel(r.correction)}</td>
      <td className="right num font-pixel text-[24px] leading-[24px]">{Math.round(r.adjusted_elo)}</td>
      <td className="right num">{percent(r.win_rate)}</td>
      <td className="right num text-ink-2">{r.avg_rank.toFixed(2)}</td>
      <td className="right num text-ink-2">{number(Math.round(r.mean_score))}</td>
      <td className="right num text-ink-3">{r.games}</td>
      {stage === "final" ? (
        <td className="right num">{r.hidden ? `${percent(r.hidden.wins / r.hidden.games)} · ${r.hidden.games}` : "—"}</td>
      ) : (
        targets.map((t) => {
          const v = r.versus[t];
          return (
            <td key={t} className="right num text-ink-2">
              {v ? percent(v.score / v.games) : "—"}
            </td>
          );
        })
      )}
    </tr>
  );
}

function Toggle({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="flex border border-ink">
      {options.map(([key, label]) => (
        <button key={key} className={cn("h-8 cursor-pointer px-3 whitespace-nowrap", value === key ? "bg-ink text-paper" : "hover:bg-blue-50")} onClick={() => onChange(key)}>
          {label}
        </button>
      ))}
    </div>
  );
}

const SETUP_KEY = "halite3-last-setup";
const lastSetup = (): Record<CatalogKind, string> => {
  try {
    return { model: "unknown", effort: "unknown", harness: "unknown", ...JSON.parse(localStorage.getItem(SETUP_KEY) || "{}") };
  } catch {
    return { model: "unknown", effort: "unknown", harness: "unknown" };
  }
};

function MyEntries({ contest: c, user, onChange }: { contest: Contest; user: User; onChange: () => Promise<void> }) {
  const entries = useApi<{ entries: ContestEntry[] }>(`/contests/${c.slug}/entries`, c.status === "open" ? 15000 : 0);
  const bots = useApi<{ bots: Bot[] }>(c.status === "open" ? "/bots" : null);
  const catalog = useCatalog();
  const [setup, setSetup] = useState(lastSetup);
  const [version, setVersion] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const list = entries.data?.entries || [];
  const used = new Set(list.map((e) => e.version_id));
  const owned = (bots.data?.bots || []).filter((b) => b.owned);
  const canonical: string[] = c.languages.map((l) => (l === "cpp" ? "bot.cpp" : "bot.py"));
  const options = owned
    .flatMap((b) => b.versions.filter((v) => !v.archived && c.languages.includes(v.language) && canonical.includes(v.filename) && !used.has(v.id)).map((v) => ({ id: v.id, label: `${b.name} v${v.version}`, at: v.created_at })))
    .sort((a, b) => b.at - a.at);
  const lastBot = list[0]?.bot_name || c.slug;
  // The admin has no submission quota.
  const left = user.is_admin ? Infinity : c.max_submissions - list.length;

  async function run(task: () => Promise<unknown>) {
    setBusy(true);
    setMessage("");
    try {
      await task();
      await entries.refresh();
      await bots.refresh();
      await onChange();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const upload = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    void run(async () => {
      const file = form.get("file") as File;
      if (!canonical.includes(file.name)) throw new Error(`请上传规范命名的 ${canonical.join(" 或 ")}（当前是 ${file.name}）。`);
      const trace = form.get("trace") as File | null;
      if (!trace || !trace.size) form.delete("trace");
      else if (trace.size > 16 * 1024 * 1024) throw new Error("对话轨迹不能超过 16 MiB，可以先用 gzip 压缩。");
      localStorage.setItem(SETUP_KEY, JSON.stringify(setup));
      await api(`/contests/${c.slug}/submit`, { method: "POST", body: form });
      target.reset();
    });
  };

  return (
    <div className="flex flex-col gap-6">
      {c.status === "open" && (
        <Panel icon={Upload} tone="blue" title={user.is_admin ? `提交 bot.cpp · 已提交 ${list.length} 次（管理员不限）` : `提交 bot.cpp · 剩余 ${left} / ${c.max_submissions} 次`}>
          <form onSubmit={upload} className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor="c-bot">Bot 名称</Label>
                <Input id="c-bot" name="bot" list="c-bot-names" defaultValue={lastBot} key={lastBot} maxLength={60} required />
                <datalist id="c-bot-names">
                  {owned.map((b) => (
                    <option key={b.id} value={b.name} />
                  ))}
                </datalist>
                <span className="text-ink-3">同名就是在同一个 Bot 上迭代新版本</span>
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor="c-file">{canonical.join(" / ")}</Label>
                <Input id="c-file" name="file" type="file" accept={c.languages.includes("python") ? ".cpp,.py" : ".cpp"} required className="pt-1.5" />
                <span className="text-ink-3">单文件，文件名必须是 {canonical.join(" 或 ")}</span>
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor="c-trace">Agent 轨迹（可选）</Label>
                <Input id="c-trace" name="trace" type="file" accept=".jsonl,.json,.md,.txt,.gz,.zip" className="pt-1.5" />
                <span className="text-ink-3">用来确定模型和推理强度，仅自己和管理员可见</span>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {(
                [
                  ["model", "模型"],
                  ["effort", "推理强度"],
                  ["harness", "平台 / Agent"],
                ] as [CatalogKind, string][]
              ).map(([kind, label]) => (
                <div key={kind} className="flex min-w-0 flex-col gap-1.5">
                  <Label htmlFor={`c-${kind}`}>{label}</Label>
                  <CatalogSelect id={`c-${kind}`} kind={kind} name={kind} catalog={catalog} value={setup[kind]} onChange={(v) => setSetup({ ...setup, [kind]: v })} />
                </div>
              ))}
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <Label htmlFor="c-note">备注（可选）</Label>
                <Input id="c-note" name="note" maxLength={500} placeholder="这次改了什么" />
              </div>
              <Button disabled={busy || left <= 0}>
                <Upload size={14} /> {busy ? "提交中…" : `上传并提交（${c.bench_games} 场）`}
              </Button>
            </div>
          </form>
          {options.length > 0 && (
            <details className="mt-4 border-t border-line pt-3">
              <summary className="cursor-pointer text-ink-2">或者提交一个已经上传过的 {canonical.join(" / ")} 版本</summary>
              <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end">
                <select aria-label="已上传的版本" value={version || options[0].id} onChange={(e) => setVersion(e.target.value)} className="h-9 min-w-0 flex-1 border border-line bg-paper-2 px-2 outline-none focus:border-ink">
                  {options.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <Button variant="outline" disabled={busy || left <= 0} onClick={() => void run(() => api(`/contests/${c.slug}/entries`, { method: "POST", body: JSON.stringify({ version_id: version || options[0].id }) }))}>
                  提交这个版本
                </Button>
              </div>
            </details>
          )}
          <p className="mt-3 mb-0 text-ink-3">
            {c.practice ? "每次提交与 baseline、raider 各打 6 场，成绩立即公开。" : "新提交会取消上一次提交还在排队的对局，并自动成为参加正式评测的版本；也可以把任意一次历史提交设为正式版本。"}
          </p>
        </Panel>
      )}
      {c.status === "open" && (
        <Panel title="让 Agent 自己提交" icon={Command} tone="ink">
          <p className="mt-0 text-ink-2">
            手动上传不需要 API Token。想让 Agent 在会话里自己提交、或者拿着同一个 Bot 反复迭代，就在
            <a className="text-blue" href="/settings">
              {" "}
              账号与头像{" "}
            </a>
            创建一个 Token 交给它（30 天有效，随时可撤销）。题目包里有 <code>tools/client.py</code>：
          </p>
          <pre className="m-0 overflow-x-auto border border-line bg-paper-2 p-3 font-mono text-[13px] leading-[20px]">
            {`export HALITE_TOKEN=h3_...
python3 tools/client.py --origin ${location.origin} contest-submit ${c.slug} bot.cpp --bot ${lastBot} \\
    --model <模型> --effort <推理强度> --harness <平台> [--trace 会话.jsonl]
python3 tools/client.py --origin ${location.origin} contest-status ${c.slug}`}
          </pre>
        </Panel>
      )}
      <ErrorBox message={message || entries.error} />
      {entries.loading ? (
        <Loading />
      ) : list.length ? (
        <div className="flex flex-col gap-3">
          {list.map((e) => (
            <EntryCard key={e.id} entry={e} contest={c} busy={busy} onPick={() => void run(() => api(`/contests/${c.slug}/pick`, { method: "PUT", body: JSON.stringify({ entry_id: e.id }) }))} />
          ))}
        </div>
      ) : (
        <Empty title="还没有提交">{c.status === "open" ? "上传 bot.cpp，开始和靶子对战。" : "这场比赛你没有提交。"}</Empty>
      )}
    </div>
  );
}

function EntryCard({ entry: e, contest: c, busy, onPick }: { entry: ContestEntry; contest: Contest; busy: boolean; onPick: () => void }) {
  const done = e.counts.complete || 0;
  const pending = (e.counts.queued || 0) + (e.counts.running || 0);
  const overall = e.stats.overall;
  const final = e.final?.overall;
  return (
    <section className={cn("pixel-frame", e.current && "border-ink")}>
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <span className="num font-pixel text-[24px] leading-[28px] text-blue">#{e.seq}</span>
        <a href={`/bots/${e.bot_id}`} className="hover:text-blue">
          {e.bot_name} <span className="text-ink-3">v{e.version}</span>
        </a>
        <Tag>{LANG[e.language]}</Tag>
        {e.current && <Tag className="border-ink bg-ink text-paper">{c.status === "open" ? "正式评测版本" : "参加正式评测"}</Tag>}
        <span className="text-ink-3">{date(e.created_at)}</span>
        <span className="ml-auto flex items-center gap-2">
          {pending ? <Status value="running" /> : e.counts.failed ? <Status value="failed" /> : done ? <Status value="complete" /> : <Status value="cancelled" />}
          <span className="num text-ink-2">
            {done}/{e.total}
          </span>
        </span>
      </header>
      <div className="grid gap-4 p-4 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex flex-col gap-2">
          {e.note && <div className="text-ink-2">{e.note}</div>}
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {[["overall", "总"], ...c.modes.map((m) => [String(m), m === 2 ? "1v1" : `${m} 人`])].map(([key, label]) => {
              const s = e.stats[key];
              return (
                <div key={key} className="min-w-[96px]">
                  <div className="text-ink-3">{label} · 临时</div>
                  <div className="num">
                    {s ? (
                      <>
                        <span className="text-[20px]">{Math.round(s.adjusted_elo)}</span> <span className="text-ink-3">{percent(s.win_rate)}</span>
                      </>
                    ) : (
                      "—"
                    )}
                  </div>
                </div>
              );
            })}
            {final !== undefined && (
              <div className="min-w-[96px]">
                <div className="text-ink-3">正式排名</div>
                <div className="num text-[20px] text-blue">{final?.rank ? `#${final.rank}` : "—"}</div>
              </div>
            )}
          </div>
          {overall && Object.keys(overall.versus).length > 0 && (
            <div className="flex flex-wrap gap-2 text-ink-2">
              {c.targets.map((t) => {
                const v = overall.versus[t.version_id];
                return v ? (
                  <Tag key={t.version_id}>
                    <Bullseye size={12} className="mr-1" /> {t.bot_name} {percent(v.score / v.games)}
                  </Tag>
                ) : null;
              })}
            </div>
          )}
        </div>
        <div className="flex items-start gap-2">
          {c.status === "open" && !e.current && (
            <Button size="sm" variant="secondary" disabled={busy} onClick={onPick}>
              <Check size={14} /> 设为正式版本
            </Button>
          )}
          {e.job_id && (
            <Button size="sm" variant="outline" asChild>
              <a href={`/contests/${c.slug}/matches?version=${e.version_id}`}>
                对局 <ArrowRight size={12} />
              </a>
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

function AdminPanel({ contest: c, onChange }: { contest: Contest; onChange: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function run(path: string, method = "POST", confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setMessage("");
    try {
      const r = await api<Record<string, unknown>>(path, { method, body: method === "DELETE" ? undefined : "{}" });
      if (method === "DELETE") return navigate("/contests");
      setMessage(r.games !== undefined ? `已排入 ${r.games} 场正式评测。` : r.retried !== undefined ? `已重排 ${r.retried} 场失败对局。` : "完成。");
      await onChange();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const final = c.progress.final;
  const closed = c.status === "closed" || c.status === "finished";
  if (c.practice) return <ContestEditor contest={c} onDone={() => void onChange()} />;
  return (
    <div className="flex flex-col gap-6">
      <Panel title="正式评测" icon={Trophy} tone="gold">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-ink-2">
            {c.final_started_at ? `开始于 ${date(c.final_started_at)}，完成 ${final.counts.complete || 0}/${final.total}${final.counts.failed ? `，失败 ${final.counts.failed}` : ""}` : `按当前提交预计 ${c.final_games_estimate ?? "—"} 场`}
            {c.auto_final ? " · 截止后自动开始、完成后自动公布" : " · 手动开始与公布"}
          </span>
          <span className="ml-auto flex flex-wrap gap-2">
            <Button size="sm" disabled={busy || !closed || c.status === "finished"} onClick={() => void run(`/admin/contests/${c.id}/final`, "POST", c.final_started_at ? "重新开始会取消当前正式评测还在排队的对局，按最新的最终版本重新排赛程。继续？" : undefined)}>
              <Play size={14} /> {c.final_started_at ? "重新开始正式评测" : "开始正式评测"}
            </Button>
            <Button size="sm" variant="outline" disabled={busy || !final.counts.failed} onClick={() => void run(`/admin/contests/${c.id}/retry`)}>
              <Reload size={14} /> 重试失败对局
            </Button>
            <Button size="sm" variant="outline" disabled={busy || !c.final_started_at || c.status === "finished"} onClick={() => void run(`/admin/contests/${c.id}/finalize`, "POST", "公布后排名冻结，全部比赛对局公开并计入全局 ELO。继续？")}>
              <Trophy size={14} /> 公布结果
            </Button>
            {c.submissions === 0 && (
              <Button size="sm" variant="destructive" disabled={busy} onClick={() => void run(`/admin/contests/${c.id}`, "DELETE", "删除这场比赛？")}>
                <Trash size={14} /> 删除
              </Button>
            )}
          </span>
        </div>
        {message && <p className="mt-3 mb-0 text-ink-2">{message}</p>}
      </Panel>
      {c.status !== "finished" && <ContestEditor contest={c} onDone={() => void onChange()} />}
    </div>
  );
}

type Options = { versions: { id: string; version: string; language: string; name: string; builtin: boolean }[]; setups: Record<string, { width: number; height: number; turns: number; seconds: number }> };

const toLocal = (t: number | null | undefined) => {
  if (!t) return "";
  const d = new Date(t * 1000);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const fromLocal = (s: string) => (s ? Math.floor(new Date(s).getTime() / 1000) : null);
const seedText = (seeds?: number[]) => (seeds || []).join(", ");
const parseSeeds = (s: string) =>
  s
    .split(/[\s,，]+/)
    .filter(Boolean)
    .map(Number);

function ContestEditor({ contest, onDone }: { contest?: Contest; onDone: (id: string) => void }) {
  const options = useApi<Options>("/admin/contest-options");
  const cfg: Partial<ContestConfig> = contest?.config || {};
  const hour = Math.ceil(Date.now() / 3600000) * 3600;
  const [form, setForm] = useState(() => ({
    slug: contest?.slug || "",
    title: contest?.title || "",
    summary: contest?.summary || "",
    description: contest?.description || "",
    prompt: contest?.prompt || "",
    rules: contest?.rules || "",
    visible_at: toLocal(contest ? contest.visible_at : hour),
    open_at: toLocal(contest?.open_at || hour + 86400),
    close_at: toLocal(contest?.close_at || hour + 8 * 86400),
    published: contest?.published ?? false,
    modes: cfg.modes || [2, 4],
    public_maps: Object.fromEntries([2, 4, 8].map((m) => [m, seedText(cfg.public_maps?.[m] || [11, 29, 47])])) as Record<number, string>,
    hidden_maps: Object.fromEntries([2, 4, 8].map((m) => [m, seedText(cfg.hidden_maps?.[m] || [])])) as Record<number, string>,
    targets: cfg.targets || ["builtin-baseline-v1", "builtin-raider-v1"],
    base_version_id: cfg.base_version_id ?? "builtin-baseline-v1",
    downloads: cfg.downloads || ["builtin-baseline-v1", "builtin-raider-v1"],
    languages: cfg.languages || ["cpp"],
    max_submissions: cfg.max_submissions ?? 20,
    bench_rotate: cfg.bench_rotate ?? true,
    final_rounds: cfg.final_rounds ?? 4,
    auto_final: cfg.auto_final ?? true,
  }));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: value }));
  const toggle = <T,>(list: T[], value: T) => (list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);
  const locked = Boolean(contest && (contest.submissions > 0 || (contest.published && contest.open_at <= Date.now() / 1000)));
  const versions = options.data?.versions || [];
  const label = (id: string) => {
    const v = versions.find((x) => x.id === id);
    return v ? `${v.name} v${v.version}${v.builtin ? " · 平台" : ""}` : id;
  };
  const randomSeeds = (n: number) => Array.from({ length: n }, () => Math.floor(Math.random() * 1e9)).join(", ");

  async function save() {
    setBusy(true);
    setMessage("");
    try {
      const body = {
        ...form,
        visible_at: fromLocal(form.visible_at),
        open_at: fromLocal(form.open_at),
        close_at: fromLocal(form.close_at),
        public_maps: Object.fromEntries(form.modes.map((m) => [m, parseSeeds(form.public_maps[m])])),
        hidden_maps: Object.fromEntries(form.modes.map((m) => [m, parseSeeds(form.hidden_maps[m])])),
        base_version_id: form.base_version_id || null,
      };
      if (contest) {
        await api(`/admin/contests/${contest.id}`, { method: "PUT", body: JSON.stringify(body) });
        setMessage("已保存。");
        onDone(contest.id);
      } else {
        await api<{ id: string }>("/admin/contests", { method: "POST", body: JSON.stringify(body) });
        onDone(form.slug);
      }
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const benchGames = useMemo(() => {
    const t = Math.max(1, form.targets.length);
    return form.modes.reduce((sum, m) => {
      const seeds = parseSeeds(form.public_maps[m]).length;
      const groups = m === 2 ? t : Math.ceil(t / (m - 1));
      return sum + groups * seeds * (form.bench_rotate ? { 2: 2, 4: 4, 8: 2 }[m as 2 | 4 | 8] : 1);
    }, 0);
  }, [form]);

  const field = (id: string, text: ReactNode, input: ReactNode, hint?: ReactNode) => (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{text}</Label>
      {input}
      {hint && <span className="text-ink-3">{hint}</span>}
    </div>
  );
  const check = (checked: boolean, onChange: () => void, text: ReactNode, disabled = false) => (
    <label className={cn("flex cursor-pointer items-center gap-2", disabled && "cursor-not-allowed opacity-50")}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={onChange} className="size-4 accent-[var(--blue)]" /> {text}
    </label>
  );

  return (
    <>
      {!contest && <PageHead eyebrow="管理员" title="新建比赛" description="比赛保存为草稿后，勾选“发布”才对选手可见。提交开始后，人数、公开地图、靶子和语言会被冻结。" />}
      <Panel title={contest ? "编辑比赛" : "比赛设置"} icon={Sliders}>
        <div className="flex flex-col gap-6">
          <div className="grid gap-4 sm:grid-cols-2">
            {field("c-title", "标题", <Input id="c-title" value={form.title} maxLength={80} onChange={(e) => set("title", e.target.value)} placeholder="第一届群赛" />)}
            {field("c-slug", "短名（网址）", <Input id="c-slug" value={form.slug} maxLength={40} onChange={(e) => set("slug", e.target.value.toLowerCase())} placeholder="cup-2026-11" />, "小写字母、数字和短横线")}
          </div>
          {field("c-summary", "一句话简介", <Input id="c-summary" value={form.summary} maxLength={200} onChange={(e) => set("summary", e.target.value)} />)}
          {field(
            "c-desc",
            "比赛说明",
            <textarea id="c-desc" rows={8} maxLength={20000} value={form.description} onChange={(e) => set("description", e.target.value)} className="border border-line bg-paper-2 p-2 outline-none focus:border-ink" />,
          )}
          {field(
            "c-prompt",
            "题目 Prompt（给 Agent 的任务描述）",
            <textarea id="c-prompt" rows={6} maxLength={20000} value={form.prompt} onChange={(e) => set("prompt", e.target.value)} placeholder="留空使用默认题目；提交方式、规则会自动附在后面" className="border border-line bg-paper-2 p-2 outline-none focus:border-ink" />,
          )}
          {field(
            "c-rules",
            "补充规则",
            <textarea id="c-rules" rows={4} maxLength={20000} value={form.rules} onChange={(e) => set("rules", e.target.value)} placeholder="地图、评测、提交规则由配置自动生成；这里只写额外约定，显示在规则末尾" className="border border-line bg-paper-2 p-2 outline-none focus:border-ink" />,
          )}
          <div className="grid gap-4 sm:grid-cols-3">
            {field("c-visible", "开放浏览", <Input id="c-visible" type="datetime-local" value={form.visible_at} onChange={(e) => set("visible_at", e.target.value)} />, "留空：发布即可见")}
            {field("c-open", "开放提交", <Input id="c-open" type="datetime-local" value={form.open_at} onChange={(e) => set("open_at", e.target.value)} />)}
            {field("c-close", "提交截止", <Input id="c-close" type="datetime-local" value={form.close_at} onChange={(e) => set("close_at", e.target.value)} />)}
          </div>

          <div className="flex flex-col gap-3">
            <Label>人数模式与地图（种子，逗号分隔）</Label>
            {[2, 4, 8].map((m) => {
              const on = form.modes.includes(m);
              const setup = options.data?.setups[String(m)];
              return (
                <div key={m} className={cn("grid gap-3 border border-line p-3 sm:grid-cols-[140px_minmax(0,1fr)_minmax(0,1fr)]", !on && "opacity-60")}>
                  <div>
                    {check(on, () => set("modes", toggle(form.modes, m).sort()), m === 2 ? "1v1" : `${m} 人混战`, locked)}
                    {setup && (
                      <div className="mt-1 text-ink-3">
                        {setup.width}×{setup.height} · {setup.turns} 回合
                      </div>
                    )}
                  </div>
                  {field(`pub-${m}`, "公开地图", <Input id={`pub-${m}`} value={form.public_maps[m]} disabled={!on || locked} onChange={(e) => set("public_maps", { ...form.public_maps, [m]: e.target.value })} />)}
                  {field(
                    `hid-${m}`,
                    <span className="flex items-center gap-1">
                      <Hidden size={14} /> 隐藏地图（仅正式评测）
                    </span>,
                    <span className="flex gap-2">
                      <Input id={`hid-${m}`} value={form.hidden_maps[m]} disabled={!on || Boolean(contest?.final_started_at)} onChange={(e) => set("hidden_maps", { ...form.hidden_maps, [m]: e.target.value })} />
                      <Button type="button" size="sm" variant="outline" disabled={!on || Boolean(contest?.final_started_at)} onClick={() => set("hidden_maps", { ...form.hidden_maps, [m]: randomSeeds(3) })}>
                        随机
                      </Button>
                    </span>,
                  )}
                </div>
              );
            })}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="flex flex-col gap-2">
              <Label>靶子（参加每次提交评测）</Label>
              {options.loading ? <Loading /> : versions.map((v) => <div key={v.id}>{check(form.targets.includes(v.id), () => set("targets", toggle(form.targets, v.id)), label(v.id), locked)}</div>)}
            </div>
            <div className="flex flex-col gap-2">
              <Label>开放下载（本地测试）</Label>
              {versions.map((v) => (
                <div key={v.id}>{check(form.downloads.includes(v.id), () => set("downloads", toggle(form.downloads, v.id)), label(v.id))}</div>
              ))}
            </div>
            <div className="flex flex-col gap-3">
              {field(
                "c-base",
                "基础 bot（选手起点，可下载）",
                <select id="c-base" value={form.base_version_id || ""} onChange={(e) => set("base_version_id", e.target.value)} className="h-9 border border-line bg-paper-2 px-2 outline-none focus:border-ink">
                  <option value="">不提供</option>
                  {versions.map((v) => (
                    <option key={v.id} value={v.id}>
                      {label(v.id)}
                    </option>
                  ))}
                </select>,
              )}
              <div className="flex flex-col gap-2">
                <Label>语言</Label>
                <p className="m-0 text-ink-2">C++17（全站只收 C++）</p>
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-4">
            {field("c-max", "每人提交次数", <Input id="c-max" type="number" min={1} max={200} value={form.max_submissions} onChange={(e) => set("max_submissions", Number(e.target.value))} />)}
            {field("c-rounds", "多人局正式评测轮数", <Input id="c-rounds" type="number" min={1} max={20} value={form.final_rounds} disabled={Boolean(contest?.final_started_at)} onChange={(e) => set("final_rounds", Number(e.target.value))} />, "每张地图随机分组的次数")}
            <div className="flex flex-col justify-end gap-2 sm:col-span-2">
              {check(form.bench_rotate, () => set("bench_rotate", !form.bench_rotate), "提交评测轮换座位", locked)}
              {check(form.auto_final, () => set("auto_final", !form.auto_final), "截止后自动开始正式评测，完成后自动公布")}
              {check(form.published, () => set("published", !form.published), "发布（选手可见）")}
            </div>
          </div>
          <p className="m-0 text-ink-3">每次提交约 {benchGames} 场。{locked ? "已有提交或已开放提交：人数模式、公开地图、靶子、语言和座位轮换已冻结。" : ""}</p>
          <ErrorBox message={message !== "已保存。" ? message : ""} />
          <div className="flex items-center gap-3">
            <Button disabled={busy} onClick={() => void save()}>
              <Check size={14} /> {contest ? "保存修改" : "创建比赛"}
            </Button>
            {message === "已保存。" && <span className="text-good">已保存。</span>}
            <Clock size={14} className="ml-auto text-ink-3" />
            <span className="text-ink-3">时间按本机时区填写</span>
          </div>
        </div>
      </Panel>
    </>
  );
}
