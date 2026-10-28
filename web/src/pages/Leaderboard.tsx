import { useMemo, useState } from "react";
import { Trophy, Zap, Briefcase, Truck, Eye, Scale, Upload } from "@nsmr/pixelart-react";
import { glyphIcon } from "@/components/glyphs";
import type { BoardEntry, CatalogKind, EloEntry } from "@/lib/types";
import { navigate, useLocation } from "@/lib/router";
import { PRACTICE } from "@/lib/sitemap";
import { KIND_LABEL, SETUP_KINDS, SetupCells, correctionLabel, entry, useCatalog } from "@/components/ModelBadge";
import { compact, number, percent, useApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Empty, ErrorBox, Loading, PageHead } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";
import { MetricBars } from "@/components/charts";

const Pickaxe = glyphIcon("pickaxe");

type Board = {
  key: string;
  label: string;
  icon: typeof Zap | typeof Pickaxe;
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
    key: "vision",
    label: "视野",
    icon: Eye,
    value: (e) => e.vision ?? 0,
    format: (v) => percent(v, 1),
    note: "按回合采样，统计己方船只、基地和落点照亮的格子（迷雾规则的视野半径，环面曼哈顿距离）占全图比例，取平均。",
    columns: [
      { label: "平均名次", value: (e) => e.avg_rank.toFixed(2) },
      { label: "场均造船", value: (e) => (e.ships_built || 0).toFixed(1) },
      { label: "胜率", value: (e) => percent(e.win_rate) },
    ],
  },
  {
    key: "mined",
    label: "采矿",
    icon: Pickaxe,
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
  if (!sorted.length) return <Empty title="暂无公开对局数据">在比赛里提交并完成评测后，公开对局会自动计入子榜。</Empty>;
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
                <td className={cn("num font-pixel", i < 3 ? "text-blue" : "text-ink-3")}>{String(i + 1).padStart(2, "0")}</td>
                <td className="max-w-[220px]">
                  <a href={`/bots/${e.bot_id}`} className="block hover:text-blue">
                    <Who e={e} />
                  </a>
                </td>
                <td className="right num font-pixel text-[24px] leading-[24px]">{board.format(board.value(e))}</td>
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

const ALL = "";

/** Filters for the three setup columns; options come from the entries actually on the board. */
function SetupFilters({ entries, value, onChange, catalog }: { entries: EloEntry[]; value: Record<CatalogKind, string>; onChange: (v: Record<CatalogKind, string>) => void; catalog: ReturnType<typeof useCatalog> }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      {SETUP_KINDS.map((kind) => {
        const ids = [...new Set(entries.map((e) => e.attribution?.[kind].value).filter((v): v is string => Boolean(v)))];
        return (
          <label key={kind} className="flex items-center gap-2">
            <span className="text-ink-2">{KIND_LABEL[kind]}</span>
            <select
              value={value[kind]}
              onChange={(e) => onChange({ ...value, [kind]: e.target.value })}
              className="h-8 min-w-28 cursor-pointer border border-line bg-paper-2 px-2 outline-none focus:border-ink"
            >
              <option value={ALL}>全部</option>
              {ids.map((id) => (
                <option key={id} value={id}>
                  {entry(catalog, kind, id).name}
                </option>
              ))}
            </select>
          </label>
        );
      })}
      {SETUP_KINDS.some((k) => value[k]) && (
        <button className="cursor-pointer text-blue hover:underline" onClick={() => onChange({ model: ALL, effort: ALL, harness: ALL })}>
          清除筛选
        </button>
      )}
    </div>
  );
}

function EloBoard({ entries }: { entries: EloEntry[] }) {
  const catalog = useCatalog();
  const [filter, setFilter] = useState<Record<CatalogKind, string>>({ model: ALL, effort: ALL, harness: ALL });
  const active = SETUP_KINDS.some((k) => filter[k]);
  // Baselines have no setup: keep them as reference rows unless a filter is active.
  const shown = entries.filter((e) => (e.attribution ? SETUP_KINDS.every((k) => !filter[k] || e.attribution![k].value === filter[k]) : !active));
  if (!entries.length) return <Empty title="还没有完成评测的版本">在比赛里提交 bot.cpp、对局完成后，这里按修正后 ELO 排名。</Empty>;
  return (
    <>
      <div className="border-b border-line px-4 py-3">
        <SetupFilters entries={entries} value={filter} onChange={setFilter} catalog={catalog} />
      </div>
      <table className="ptable">
        <thead>
          <tr>
            <th>#</th>
            <th>Bot</th>
            <th>模型</th>
            <th>推理</th>
            <th>平台</th>
            <th className="right">原始 ELO</th>
            <th className="right">修正合计</th>
            <th className="right text-blue">修正后 ELO</th>
            <th className="right">胜率</th>
            <th className="right">场次</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((e) => (
            <tr key={e.version_id} className={e.builtin ? "bg-paper" : ""}>
              <td className={cn("num font-pixel whitespace-nowrap", e.rank && e.rank <= 3 ? "text-blue" : "text-ink-3")}>{e.rank ? String(e.rank).padStart(2, "0") : "基准"}</td>
              <td className="max-w-[220px]">
                <a href={`/bots/${e.bot_id}`} className="block hover:text-blue">
                  <Who e={e} />
                </a>
              </td>
              <SetupCells attribution={e.attribution} catalog={catalog} />
              <td className="right num whitespace-nowrap text-ink-2">
                {Math.round(e.elo)}
                <span className="text-ink-3"> ±{Math.round(e.elo_sd)}</span>
              </td>
              <td className="right num text-ink-2">{e.builtin ? "—" : correctionLabel(e.correction)}</td>
              <td className="right num font-pixel text-[24px] leading-[24px]">{Math.round(e.adjusted_elo)}</td>
              <td className="right num">{percent(e.win_rate)}</td>
              <td className="right num text-ink-3">{e.games}</td>
            </tr>
          ))}
          {!shown.length && (
            <tr>
              <td colSpan={10} className="py-8 text-center text-ink-3">
                没有符合筛选条件的版本
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}

const TABS = ["elo", ...BOARDS.map((b) => b.key)];

export default function Leaderboard() {
  const { search } = useLocation();
  const elo = useApi<{ entries: EloEntry[]; anchor: number }>("/leaderboard/elo");
  const [mode, setMode] = useState("");
  const stats = useApi<{ entries: BoardEntry[] }>(`/leaderboard/stats${mode ? `?mode=${mode}` : ""}`);
  const tab = TABS.includes(search.get("tab") || "") ? search.get("tab")! : "elo";

  return (
    <>
      <PageHead
        eyebrow="排行榜"
        title="ELO、Tier 与子榜"
        description="跨比赛的全局榜：ELO 总榜按修正后的 ELO 排名，用来平衡不同模型和推理强度；子榜统计全部公开对局。各场比赛自己的排名（以及 #0 的 Tier）在比赛页里。"
        action={
          <>
            <Button variant="outline" asChild>
              <a href={`${PRACTICE}/tier`}>
                <Trophy size={16} /> #0 Tier
              </a>
            </Button>
            <Button asChild>
              <a href={`${PRACTICE}/mine`}>
                <Upload size={16} /> 去 #0 提交参评
              </a>
            </Button>
          </>
        }
      />
      <ErrorBox message={stats.error || elo.error} />
      <Tabs value={tab} onValueChange={(t) => navigate(t === "elo" ? "/leaderboard" : `/leaderboard?tab=${t}`, true)} className="gap-6">
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <TabsList className="h-10">
            <TabsTrigger value="elo" className="px-4">
              <Scale size={14} /> ELO 总榜
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
            修正后 ELO = 原始 ELO − 模型修正 − 推理强度修正 − 平台修正，三项分列在对应列下方；强模型、强推理扣分更多。用户声明与轨迹检测不一致时按修正更大的一方计算，管理员可以人工确认。平台基准不做修正、不参与排名。
          </p>
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
