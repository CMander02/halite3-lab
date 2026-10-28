import { useMemo, useState } from "react";
import { Trophy, Zap, Briefcase, Truck, Eye, ArrowRight, Scale, List } from "@nsmr/pixelart-react";
import { glyphIcon } from "@/components/glyphs";
import type { BoardEntry, CatalogKind, EloEntry, LeaderEntry, MatchupMatrix } from "@/lib/types";
import { KIND_LABEL, SETUP_KINDS, SetupCells, correctionLabel, entry, useCatalog } from "@/components/ModelBadge";
import { compact, number, percent, useApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Empty, ErrorBox, Loading, PageHead, Panel, TierBadge } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";
import { BotIcon } from "@/components/BotIcon";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { navigate, useLocation } from "@/lib/router";
import { leaderboardHref, leaderboardState } from "@/lib/leaderboard";
import { PRACTICE } from "@/lib/sitemap";
import { TierBoard } from "@/components/TierBoard";
import { Who, fullName } from "@/components/BotWho";
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

function EloBoard({ entries, filter, setFilter }: { entries: EloEntry[]; filter: Record<CatalogKind, string>; setFilter: (v: Record<CatalogKind, string>) => void }) {
  const catalog = useCatalog();
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

function ModeFilter({ mode, onChange }: { mode: string; onChange: (mode: string) => void }) {
  return (
    <label className="flex items-center gap-2">
      <span className="text-ink-2">人数模式</span>
      <select aria-label="人数模式" value={mode} onChange={(e) => onChange(e.target.value)} className="h-8 cursor-pointer border border-line bg-paper-2 px-2">
        <option value="">全部模式</option>
        <option value="2">1v1</option>
        <option value="4">4 人</option>
        <option value="8">8 人</option>
      </select>
    </label>
  );
}

function WinMatrix({ data }: { data: MatchupMatrix }) {
  const catalog = useCatalog();
  const [selected, setSelected] = useState<{ row: string; col: string } | null>(null);
  const { entries, cells } = data;
  if (!entries.length) return <Empty title="暂无公开对战数据">完成公开评测后，这里显示所有在榜版本之间的对战胜率。</Empty>;
  const selectedRow = entries.find((e) => e.version_id === selected?.row);
  const selectedCol = entries.find((e) => e.version_id === selected?.col);
  const selectedCell = selected ? cells[selected.row]?.[selected.col] : null;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <p id="matrix-help" className="m-0 text-ink-2">行 Bot 对列 Bot 的胜率 =（胜 + 平 × 0.5）÷ 比较次数。多人局按最终名次逐对座位比较，同版本不比较；重复座位分别计数。仅统计已完成的公开对局，无 ELO 修正。点击格子查看详情。</p>
      <div className="flex flex-wrap gap-3 text-ink-3">
        <span className="bg-blue-100 px-2">&gt; 50%</span><span className="bg-paper px-2">= 50%</span><span className="bg-bad/10 px-2">&lt; 50%</span><span>未交手：无比较记录</span>
      </div>
      <div className="max-h-[70vh] overflow-auto border border-line" role="region" aria-label="胜率矩阵，可横向及纵向滚动" tabIndex={0}>
        <table className="w-max border-separate border-spacing-0 text-sm" aria-describedby="matrix-help">
          <caption className="sr-only">公开在榜 Bot 版本之间的胜率矩阵，行对列，按修正后 ELO 排序，包含平台基准。</caption>
          <thead className="sticky top-0 z-20">
            <tr>
              <th className="sticky left-0 z-30 w-44 border-r border-b border-line bg-paper px-3 py-2 text-left">行 ↓ 对列 →</th>
              {entries.map((e, i) => (
                <th key={e.version_id} scope="col" className="w-28 max-w-28 border-r border-b border-line bg-paper px-2 py-2 font-normal">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <a href={`/bots/${e.bot_id}`} className="flex flex-col items-center gap-1 hover:text-blue" aria-label={fullName(e)}>
                        <BotIcon id={e.bot_id} model={e.model} catalog={catalog} className="size-6" />
                        <span className="block w-full truncate">{i + 1}. {e.bot_name}</span>
                        <span className="block w-full truncate text-ink-3">v{e.version}</span>
                      </a>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs break-words">{fullName(e)}</TooltipContent>
                  </Tooltip>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((row, i) => (
              <tr key={row.version_id}>
                <th scope="row" className="sticky left-0 z-10 w-44 max-w-44 border-r border-b border-line bg-paper-2 px-2 py-2 text-left font-normal">
                  <a href={`/bots/${row.bot_id}`} className="flex min-w-0 items-center gap-2 hover:text-blue" aria-label={fullName(row)}>
                    <span className="num text-ink-3">{i + 1}</span><Who e={row} />
                  </a>
                </th>
                {entries.map((col) => {
                  const cell = cells[row.version_id]?.[col.version_id];
                  const self = row.version_id === col.version_id;
                  const detail = `${fullName(row)} 对 ${fullName(col)}：${self ? "同一版本" : cell ? `${percent(cell.win_rate, 1)}，${cell.wins} 胜 / ${cell.draws} 平 / ${cell.losses} 负，${cell.games} 次比较` : "未交手"}`;
                  return (
                    <td key={col.version_id} className="border-r border-b border-line p-0 text-center">
                      {self ? <span className="block bg-paper py-3 text-ink-3" aria-label="同一版本">—</span> : (
                        <button type="button" title={detail} aria-label={detail} aria-pressed={selected?.row === row.version_id && selected?.col === col.version_id}
                          onClick={() => setSelected({ row: row.version_id, col: col.version_id })}
                          className={cn("flex min-h-14 w-full cursor-pointer flex-col items-center justify-center px-2 focus-visible:outline-2 focus-visible:outline-blue aria-pressed:ring-2 aria-pressed:ring-inset aria-pressed:ring-blue", !cell ? "text-ink-3" : cell.win_rate > 0.5 ? "bg-blue-100 text-ink" : cell.win_rate < 0.5 ? "bg-bad/10 text-ink" : "bg-paper text-ink")}>
                          <span className="num">{cell ? percent(cell.win_rate, 1) : "未交手"}</span>
                          {cell && <span className="text-xs text-ink-2">{cell.games} 次</span>}
                        </button>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="m-0 min-h-6 break-words text-ink-2" aria-live="polite">
        {selectedRow && selectedCol ? `${fullName(selectedRow)} 对 ${fullName(selectedCol)}：${selectedCell ? `${percent(selectedCell.win_rate, 1)}，${selectedCell.wins} 胜 / ${selectedCell.draws} 平 / ${selectedCell.losses} 负，共 ${selectedCell.games} 次比较。` : "当前人数模式下未交手。"}` : "悬停或聚焦名称查看全名；矩阵可滚动，行列标题保持可见。"}
      </p>
    </div>
  );
}

export default function Leaderboard() {
  const { search } = useLocation();
  const { view, mode, filter } = leaderboardState(search);
  const update = (changes: Record<string, string>) => navigate(leaderboardHref(search, changes));
  const elo = useApi<{ entries: EloEntry[]; anchor: number }>("/leaderboard/elo");
  const stats = useApi<{ entries: BoardEntry[] }>(`/leaderboard/stats${mode ? `?mode=${mode}` : ""}`);
  const matrix = useApi<MatchupMatrix>(view === "matrix" ? `/leaderboard/matrix${mode ? `?mode=${mode}` : ""}` : null);

  return (
    <>
      <PageHead
        eyebrow="排行榜"
        title="ELO、Tier 与对战胜率"
        description="跨比赛的全局榜：ELO 总榜按修正后的 ELO 排名，用来平衡不同模型和推理强度；子榜和胜率矩阵统计全部公开对局；Tier 是 #0 的 12 场基准成绩。各场比赛自己的排名在比赛页里。"
        action={
          <Button asChild>
            <a href={`${PRACTICE}/mine`}>
              <Trophy size={16} /> 去 #0 提交参评
            </a>
          </Button>
        }
      />
      <p className="mt-0 mb-4 text-ink-3"><a href={leaderboardHref(search, { view })} className="text-blue hover:underline">当前视图链接</a> · 可复制链接分享当前榜单、人数模式和筛选条件。</p>
      <ErrorBox message={stats.error || elo.error || matrix.error} />
      <Tabs value={view} onValueChange={(value) => update({ view: value })} className="min-w-0 gap-6">
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <TabsList className="h-10">
            <TabsTrigger value="elo" className="px-4">
              <Scale size={14} /> ELO 总榜
            </TabsTrigger>
            <TabsTrigger value="tier" className="px-4">
              <Trophy size={14} /> Tier
            </TabsTrigger>
            <TabsTrigger value="matrix" className="px-4">胜率矩阵</TabsTrigger>
            {BOARDS.map(({ key, label, icon: Icon }) => (
              <TabsTrigger key={key} value={key} className="px-4">
                <Icon size={14} /> {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <TabsContent value="elo" className="flex flex-col gap-4">
          <div className="pixel-frame overflow-x-auto p-0">{elo.loading ? <Loading /> : <EloBoard entries={elo.data?.entries || []} filter={filter} setFilter={(next) => update(next)} />}</div>
          <p className="m-0 max-w-[880px] text-ink-3">
            原始 ELO：对全部公开对局做 Bradley–Terry 极大似然拟合（每局按名次两两比较，多人局按 1/(n−1) 加权，另加对 1500 锚点的一胜一负先验），与比赛顺序无关。
            修正后 ELO = 原始 ELO − 模型修正 − 推理强度修正 − 平台修正，三项分列在对应列下方；强模型、强推理扣分更多。用户声明与轨迹检测不一致时按修正更大的一方计算，管理员可以人工确认。平台基准不做修正、不参与排名。
          </p>
        </TabsContent>

        <TabsContent value="tier" className="flex flex-col gap-4">
          <p className="m-0 text-ink-2">
            Tier 是 #0 测试比赛的成绩，也在{" "}
            <a href={`${PRACTICE}/tier`} className="text-blue hover:underline">
              #0 比赛页的 Tier
            </a>{" "}
            里。
          </p>
          {view === "tier" && <TierBoard />}
        </TabsContent>

        <TabsContent value="matrix" className="flex min-w-0 flex-col gap-4">
          <ModeFilter mode={mode} onChange={(value) => update({ mode: value })} />
          <div className="pixel-frame min-w-0 p-3 sm:p-4">{matrix.loading ? <Loading /> : matrix.data ? <WinMatrix key={mode} data={matrix.data} /> : null}</div>
        </TabsContent>

        {BOARDS.map((board) => (
          <TabsContent key={board.key} value={board.key} className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <ModeFilter mode={mode} onChange={(value) => update({ mode: value })} />
              <span className="text-ink-2">按 Bot 版本聚合 · 仅公开对局</span>
            </div>
            <div className="pixel-frame p-4">{stats.loading ? <Loading /> : <SubBoard board={board} entries={stats.data?.entries || []} />}</div>
          </TabsContent>
        ))}
      </Tabs>
    </>
  );
}
