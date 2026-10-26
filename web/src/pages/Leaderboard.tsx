import { useMemo, useState } from "react";
import { Trophy, Zap, Briefcase, Truck, Map as MapIcon, Coin, ArrowRight, Scale } from "@nsmr/pixelart-react";
import type { BoardEntry, EloEntry, LeaderEntry } from "@/lib/types";
import { SetupLine, correctionLabel, useCatalog } from "@/components/ModelBadge";
import { compact, number, percent, useApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Empty, ErrorBox, Loading, PageHead, Panel, TierBadge } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";
import { MetricBars } from "@/components/charts";

type Board = {
  key: string;
  label: string;
  icon: typeof Zap;
  value: (e: BoardEntry) => number;
  format: (v: number) => string;
  note: string;
  columns: { label: string; value: (e: BoardEntry) => string }[];
};

const BOARDS: Board[] = [
  {
    key: "kda",
    label: "KDA",
    icon: Zap,
    value: (e) => e.kda,
    format: (v) => v.toFixed(2),
    note: "(击沉 + 同归) ÷ 被击沉。击沉：自己的船在碰撞中存活并撞沉敌船；同归：最轻重量并列、双方一起沉没。",
    columns: [
      { label: "击沉", value: (e) => number(e.kills) },
      { label: "被击沉", value: (e) => number(e.deaths) },
      { label: "同归", value: (e) => number(e.assists) },
    ],
  },
  {
    key: "robbed",
    label: "抢劫",
    icon: Briefcase,
    value: (e) => e.robbed,
    format: (v) => compact(v),
    note: "轻船撞沉敌船后夺走的货物总量（受 1000 载重上限约束）。",
    columns: [
      { label: "场均", value: (e) => number(Math.round(e.robbed_per_game)) },
      { label: "被抢/损失", value: (e) => number(e.lost) },
      { label: "击沉", value: (e) => number(e.kills) },
    ],
  },
  {
    key: "delivered",
    label: "搬运",
    icon: Truck,
    value: (e) => e.delivered,
    format: (v) => compact(v),
    note: "场均卸入基地与落点的矿量（含抢来的货物）。",
    columns: [
      { label: "场均采矿", value: (e) => number(Math.round(e.mined)) },
      { label: "场均造船", value: (e) => (e.ships_built || 0).toFixed(1) },
      { label: "场均得分", value: (e) => number(Math.round(e.score)) },
    ],
  },
  {
    key: "territory",
    label: "圈地",
    icon: MapIcon,
    value: (e) => e.territory,
    format: (v) => percent(v, 1),
    note: "按回合采样，统计离己方船只或建筑最近（环面曼哈顿距离，平局不计）的格子占全图比例，取平均。",
    columns: [
      { label: "平均名次", value: (e) => e.avg_rank.toFixed(2) },
      { label: "场均造船", value: (e) => (e.ships_built || 0).toFixed(1) },
      { label: "胜率", value: (e) => percent(e.win_rate) },
    ],
  },
  {
    key: "mined",
    label: "采矿",
    icon: Coin,
    value: (e) => e.mined,
    format: (v) => compact(v),
    note: "场均从地面采集的矿量。",
    columns: [
      { label: "场均搬运", value: (e) => number(Math.round(e.delivered)) },
      { label: "场均得分", value: (e) => number(Math.round(e.score)) },
      { label: "胜率", value: (e) => percent(e.win_rate) },
    ],
  },
];

const TIERS = [
  { tier: "S", rule: "胜率 ≥ 75%" },
  { tier: "A", rule: "≥ 50%" },
  { tier: "B", rule: "≥ 25%" },
  { tier: "C", rule: "< 25%" },
];

function Who({ e }: { e: { author_id: string | null; author: string | null; bot_name: string; version: string; builtin?: number } }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <UserAvatar id={e.author_id} name={e.author || "平台基准"} size="sm" />
      <span className="min-w-0">
        <span className="block truncate">
          {e.bot_name} <span className="text-ink-3">v{e.version}</span>
        </span>
        <span className="block truncate text-ink-3">{e.builtin ? "平台基准" : e.author}</span>
      </span>
    </span>
  );
}

function SubBoard({ board, entries }: { board: Board; entries: BoardEntry[] }) {
  const sorted = useMemo(() => [...entries].sort((a, b) => board.value(b) - board.value(a)), [entries, board]);
  if (!sorted.length) return <Empty title="暂无公开对局数据">参加固定基准评测后，公开对局会自动计入子榜。</Empty>;
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <div>
        <MetricBars rows={sorted.slice(0, 10).map((e) => ({ name: `${e.bot_name} v${e.version}`, value: board.value(e) }))} format={board.format} label={board.label} />
        <p className="mt-3 mb-0 text-ink-2">{board.note}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="ptable">
          <thead>
            <tr>
              <th>#</th>
              <th>Bot</th>
              <th className="right text-blue">{board.label}</th>
              {board.columns.map((c) => (
                <th key={c.label} className="right">
                  {c.label}
                </th>
              ))}
              <th className="right">场次</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((e, i) => (
              <tr key={e.version_id}>
                <td className={cn("num", i < 3 ? "text-blue" : "text-ink-3")}>{String(i + 1).padStart(2, "0")}</td>
                <td className="max-w-[220px]">
                  <Who e={e} />
                </td>
                <td className="right num text-[24px] leading-[24px]">{board.format(board.value(e))}</td>
                {board.columns.map((c) => (
                  <td key={c.label} className="right num text-ink-2">
                    {c.value(e)}
                  </td>
                ))}
                <td className="right num text-ink-3">{e.games}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EloBoard({ entries }: { entries: EloEntry[] }) {
  const catalog = useCatalog();
  if (!entries.length) return <Empty title="还没有完成评测的版本">在“Bots”上传版本并参加评测后，这里按修正后 ELO 排名。</Empty>;
  return (
    <table className="ptable">
      <thead>
        <tr>
          <th>#</th>
          <th>Bot</th>
          <th>模型 · 推理 · 平台</th>
          <th className="right">原始 ELO</th>
          <th className="right">修正</th>
          <th className="right text-blue">修正后 ELO</th>
          <th className="right">胜率</th>
          <th className="right">场次</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr key={e.version_id} className={e.builtin ? "bg-paper" : ""}>
            <td className={cn("num", e.rank && e.rank <= 3 ? "text-blue" : "text-ink-3")}>{e.rank ? String(e.rank).padStart(2, "0") : "基准"}</td>
            <td className="max-w-[220px]">
              <a href={`/bots/${e.bot_id}`} className="block hover:text-blue">
                <Who e={e} />
              </a>
            </td>
            <td className="max-w-[300px]">
              <SetupLine attribution={e.attribution} catalog={catalog} />
            </td>
            <td className="right num text-ink-2">
              {Math.round(e.elo)}
              <span className="text-ink-3"> ±{Math.round(e.elo_sd)}</span>
            </td>
            <td className="right num text-ink-2">{e.builtin ? "—" : correctionLabel(e.correction)}</td>
            <td className="right num text-[24px] leading-[24px]">{Math.round(e.adjusted_elo)}</td>
            <td className="right num">{percent(e.win_rate)}</td>
            <td className="right num text-ink-3">{e.games}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Leaderboard() {
  const elo = useApi<{ entries: EloEntry[]; anchor: number }>("/leaderboard/elo");
  const tiers = useApi<{ entries: LeaderEntry[]; season: string; required_games: number }>("/leaderboard");
  const [mode, setMode] = useState("");
  const stats = useApi<{ entries: BoardEntry[] }>(`/leaderboard/stats${mode ? `?mode=${mode}` : ""}`);
  const entries = tiers.data?.entries || [];

  return (
    <>
      <PageHead
        eyebrow="排行榜"
        title="ELO、Tier 与子榜"
        description="ELO 总榜按修正后的 ELO 排名，用来平衡不同模型和推理强度；Tier 来自 12 场固定基准评测；子榜统计全部公开对局。"
        action={
          <Button asChild>
            <a href="/bots">
              <Trophy size={16} /> 提交版本参评
            </a>
          </Button>
        }
      />
      <ErrorBox message={tiers.error || stats.error || elo.error} />
      <Tabs defaultValue="elo" className="gap-6">
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <TabsList className="h-10">
            <TabsTrigger value="elo" className="px-4">
              <Scale size={14} /> ELO 总榜
            </TabsTrigger>
            <TabsTrigger value="tier" className="px-4">
              <Trophy size={14} /> Tier
            </TabsTrigger>
            {BOARDS.map(({ key, label, icon: Icon }) => (
              <TabsTrigger key={key} value={key} className="px-4">
                <Icon size={14} /> {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <TabsContent value="elo" className="flex flex-col gap-4">
          <div className="pixel-frame overflow-x-auto p-0">{elo.loading ? <Loading /> : <EloBoard entries={elo.data?.entries || []} />}</div>
          <p className="m-0 max-w-[880px] text-ink-3">
            原始 ELO：对全部公开对局做 Bradley–Terry 极大似然拟合（每局按名次两两比较，多人局按 1/(n−1) 加权，另加对 1500 锚点的一胜一负先验），与比赛顺序无关。
            修正后 ELO = 原始 ELO − 模型修正 − 推理强度修正 − 平台修正；强模型、强推理扣分更多。用户声明与轨迹检测不一致时按修正更大的一方计算，管理员可以人工确认。平台基准不做修正、不参与排名。
          </p>
        </TabsContent>

        <TabsContent value="tier" className="flex flex-col gap-6">
          {tiers.loading ? (
            <Loading />
          ) : (
            <>
              <div className="flex flex-col border border-ink">
                {TIERS.map(({ tier, rule }) => {
                  const row = entries.filter((e) => e.tier === tier);
                  return (
                    <div key={tier} className="flex min-h-16 border-b border-line last:border-0">
                      <div className={cn("flex w-20 shrink-0 flex-col items-center justify-center gap-1 border-r border-line sm:w-28", tier === "S" && "bg-ink text-paper", tier === "A" && "bg-blue text-white", tier === "B" && "bg-blue-100", tier === "C" && "bg-paper")}>
                        <span className="text-[36px] leading-[36px]">{tier}</span>
                        <span className="text-[12px] opacity-80">{rule}</span>
                      </div>
                      <div className="flex flex-1 flex-wrap items-center gap-2 p-2">
                        {row.length ? (
                          row.map((e) => (
                            <a key={e.version_id} href={`/matches?version=${e.version_id}`} className="flex items-center gap-2 border border-line bg-paper-2 py-1 pr-3 pl-1 hover:border-ink">
                              <UserAvatar id={e.author_id} name={e.author} size="sm" />
                              <span>
                                {e.bot_name} <span className="text-ink-3">v{e.version}</span>
                              </span>
                              <span className="num text-blue">{(e.win_rate * 100).toFixed(0)}%</span>
                            </a>
                          ))
                        ) : (
                          <span className="px-2 text-ink-3">—</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              <Panel title="完整排名" bodyClassName="p-0 overflow-x-auto">
                {entries.length ? (
                  <table className="ptable">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Tier</th>
                        <th>Bot</th>
                        <th className="right">胜率</th>
                        <th className="right">胜/场</th>
                        <th className="right">平均矿量</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {entries.map((e, i) => (
                        <tr key={e.version_id}>
                          <td className="num text-ink-3">{String(i + 1).padStart(2, "0")}</td>
                          <td>
                            <TierBadge tier={e.tier} />
                          </td>
                          <td>
                            <Who e={e} />
                          </td>
                          <td className="right num text-[24px] leading-[24px]">{(e.win_rate * 100).toFixed(1)}%</td>
                          <td className="right num text-ink-2">
                            {e.wins}/{e.games}
                          </td>
                          <td className="right num">{number(Math.round(e.mean_score))}</td>
                          <td className="right">
                            <a className="inline-flex items-center gap-1 text-blue" href={`/matches?version=${e.version_id}`}>
                              回放 <ArrowRight size={12} />
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty title="排行榜等待第一个完成评测的版本">在“Bots”上传版本后选择“提交排名”。</Empty>
                )}
              </Panel>
              <p className="m-0 text-ink-3">
                评测集 {tiers.data?.season}：对阵 baseline 与 raider，种子 11 / 29 / 47，交换座位，共 {tiers.data?.required_games ?? 12} 场。私人自选对手的测试不计入。
              </p>
            </>
          )}
        </TabsContent>

        {BOARDS.map((board) => (
          <TabsContent key={board.key} value={board.key} className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex border border-ink">
                {[
                  ["", "全部模式"],
                  ["2", "1v1"],
                  ["4", "4 人"],
                  ["8", "8 人"],
                ].map(([key, label]) => (
                  <button key={key} className={cn("h-8 cursor-pointer px-3", mode === key ? "bg-ink text-paper" : "hover:bg-blue-50")} onClick={() => setMode(key)}>
                    {label}
                  </button>
                ))}
              </div>
              <span className="text-ink-2">按 Bot 版本聚合 · 仅公开对局</span>
            </div>
            <div className="pixel-frame p-4">{stats.loading ? <Loading /> : <SubBoard board={board} entries={stats.data?.entries || []} />}</div>
          </TabsContent>
        ))}
      </Tabs>
    </>
  );
}
