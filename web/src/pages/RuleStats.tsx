import { useApi, number, percent } from "@/lib/api";
import { Empty, ErrorBox, Loading } from "@/components/pixel";
import { MetricBars } from "@/components/charts";

type Cohort = {
  mode: number; config: Record<string, number | boolean | null>; games: number; seats: number;
  initial: number; remaining: number; cells: number; reefs: number; unknown: number;
  ship_turns: number; moving_turns: number; cargo_bins: number[]; enemy_events: number;
  friendly_events: number; outcomes: Record<string, number>; counters: Record<string, number>; peak_ships_sum: number;
};
type Report = {
  covered: number; eligible: number; missing: number; latest_match_at: number | null; bins: string[]; cohorts: Cohort[];
  top: { candidates: number; cutoff: number | null; min_games: number; versions: { version_id: string; bot_id: string; bot_name: string; version: string; elo: number }[] };
};
const rate = (n: number, d: number) => d ? percent(n / d, 1) : "无样本";
const OUTCOMES: Record<string, string> = { capture: "轻船存活", tie: "最轻同重全灭", pileup: "多船阈值全灭", upstream: "原版全灭" };

function CohortStats({ data: d, bins }: { data: Cohort; bins: string[] }) {
  const c = d.counters;
  const participants = c.enemy_participants || 0;
  const metrics = [
    ["敌对碰撞事件", number(d.enemy_events)], ["己方碰撞事件", number(d.friendly_events)],
    ["回合开始空载的参撞船", rate(c.enemy_empty || 0, participants)],
    ["结算时空载的参撞船", rate(c.enemy_settlement_empty || 0, participants)],
    ["主动移动且回合开始空载", rate(c.enemy_moving_empty || 0, participants)],
    ["出生船参撞", rate(c.enemy_newborn || 0, participants)],
    ["期末地面矿 / 初始地面矿", rate(d.remaining, d.initial)],
    ["平均船数峰值（回合开始）", d.seats ? (d.peak_ships_sum / d.seats).toFixed(1) : "无样本"],
  ];
  return <section className="pixel-frame min-w-0 p-4 sm:p-6">
    <h2 className="m-0 text-xl">{d.mode === 2 ? "1v1" : `${d.mode} 人`} · {d.config.width}×{d.config.height} · {d.config.turns} 步</h2>
    <p className="mt-2 text-ink-2">{number(d.games)} 场 · {number(d.seats)} 个所选座位 · {number(participants)} 次敌对参撞船计数 · 视野半径 {String(d.config.VISION_RADIUS ?? "未记录")} · 全灭阈值 {d.config.PILEUP_WRECK_SIZE ? `${d.config.PILEUP_WRECK_SIZE} 艘` : "关闭"} · 实际礁石 {rate(d.reefs, d.cells)}{d.config.MIRROR_REEFS == null && " · 早期回放缺少部分规则常量，单独列示"}</p>
    <dl className="my-5 grid grid-cols-1 gap-4 min-[460px]:grid-cols-2 xl:grid-cols-4">
      {metrics.map(([label, value]) => <div key={label} className="border-l-2 border-blue pl-3"><dt className="text-sm text-ink-2">{label}</dt><dd className="m-0 mt-1 text-2xl num">{value}</dd></div>)}
    </dl>
    <div className="grid min-w-0 gap-6 lg:grid-cols-2">
      <div className="min-w-0"><h3>敌对碰撞结果</h3>{d.enemy_events ? <MetricBars label="事件占比" rows={Object.entries(OUTCOMES).map(([key, name]) => ({ name, value: (d.outcomes[key] || 0) / d.enemy_events }))} format={(v) => percent(v, 1)} /> : <p className="text-ink-3">暂无敌对碰撞事件。</p>}
        <p className="text-sm text-ink-2">同一格一次结算计一事件；同回合出生碰撞单独计数。含所选版本与其他版本的碰撞。</p></div>
      <div className="min-w-0"><h3>回合开始载重分布</h3>{d.ship_turns ? <MetricBars label="船回合占比" rows={bins.map((name, i) => ({ name, value: d.cargo_bins[i] / d.ship_turns }))} format={(v) => percent(v, 1)} /> : <p className="text-ink-3">暂无船回合样本。</p>}
        <p className="text-sm text-ink-2">{number(d.ship_turns)} 个船回合，包含存活船的逐回合载重。主动移动占 {rate(d.moving_turns, d.ship_turns)}。</p></div>
    </div>
    <div className="overflow-x-auto"><table className="ptable"><caption className="py-3 text-left text-ink-2">参撞船计数，含所选版本的存活船与沉没船</caption><thead><tr><th>结果</th><th className="right">敌对事件</th><th className="right">所选船参与</th><th className="right">其中回合开始空载</th></tr></thead><tbody>
      {Object.entries(OUTCOMES).map(([key, label]) => <tr key={key}><th scope="row">{label}</th><td className="right num">{number(d.outcomes[key] || 0)}</td><td className="right num">{number(c[`enemy_${key}`] || 0)}</td><td className="right num">{rate(c[`enemy_${key}_empty`] || 0, c[`enemy_${key}`] || 0)}</td></tr>)}
    </tbody></table></div>
    <p className="mb-0 text-sm text-ink-3">空载指载重为 0。主动移动按实际成功移动统计，不能据此判断攻击意图。期末地面矿含碰撞回流，初始矿枯竭率需另做资源追踪；该比值也受灵感奖励、移动耗矿与落点建造影响。{d.unknown > 0 && `另有 ${d.unknown} 个碰撞事件无法还原，已排除碰撞指标。`}</p>
  </section>;
}

export default function RuleStats({ mode, group, onGroup }: { mode: string; group: string; onGroup: (value: string) => void }) {
  const params = new URLSearchParams({ group });
  if (mode) params.set("mode", mode);
  const report = useApi<Report>(`/leaderboard/rules?${params}`);
  const data = report.data;
  return <div className="flex min-w-0 flex-col gap-4">
    <label className="flex flex-wrap items-center gap-2"><span>版本分组</span><select aria-label="版本分组" value={group} onChange={(e) => onGroup(e.target.value)} className="h-9 max-w-full border border-line bg-paper-2 px-2"><option value="all">全部公开在榜版本</option><option value="top">原始 ELO 前 25% 版本参与</option></select></label>
    <ErrorBox message={report.error} />
    {report.loading ? <Loading /> : data && <>
      <div className="border border-line bg-paper-2 p-4">
        <p className="mt-0">已覆盖 {number(data.covered)} / {number(data.eligible)} 场符合条件的公开对局。{data.missing > 0 && `待统计 ${number(data.missing)} 场。`}{data.latest_match_at && `最近对局：${new Date(data.latest_match_at * 1000).toLocaleString("zh-CN")}。`}</p>
        <details><summary className="cursor-pointer text-blue">统计口径 · {group === "top" ? "原始 ELO 前 25% 版本参与" : "全部公开在榜版本"}</summary>
          <p className="mb-0 text-ink-2">前 25% 按全模式原始 ELO 选取，至少完成 {data.top.min_games} 个公开座位场次，排除平台基准，共 {data.top.candidates} 个候选版本；分界 {data.top.cutoff ?? "暂无"}，同分全选。选择此组时，船指标仅计所选版本，碰撞事件包含其对手，地面矿统计其参与的整张地图。地图大小、回合数和规则不同的对局分别展示。</p>
        </details>
        {group === "top" && <details className="mt-3"><summary className="cursor-pointer text-blue">所选版本（{data.top.versions.length}）</summary><ul className="break-words pl-5">{data.top.versions.map((e) => <li key={e.version_id}><a href={`/bots/${e.bot_id}`} className="text-blue hover:underline">{e.bot_name} v{e.version}</a> · {e.elo}</li>)}</ul></details>}
      </div>
      {data.cohorts.length ? data.cohorts.map((d, i) => <CohortStats key={i} data={d} bins={data.bins} />) : <Empty title="暂无符合条件的统计">完成公开评测并生成规则统计后，这里显示数据。</Empty>}
    </>}
  </div>;
}
