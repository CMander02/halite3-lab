import { useApi, number, percent } from "@/lib/api";
import { useLocation, navigate } from "@/lib/router";
import { Empty, ErrorBox, Loading } from "@/components/pixel";
import type { Standings } from "@/lib/types";

type Case = { key: string; label: string; counts: Record<string, number>; total: number; map_seeds: number[];
  setups: Record<string, { width: number; height: number; turns: number; rules: Record<string, unknown> }> };
type Batch = { key: string; label: string; job_id: string; turn_timeout_ms: number; bot_cpu_percent: number; worker_cpus?: number[] | null };
type Results = { execution_batches: Batch[]; selected_batch: Batch; execution_host: string; selected: string; scenarios: Case[]; standings: Standings;
  progress: { counts: Record<string, number>; total: number };
  roster: { version_id: string; bot_id: string; bot_name: string; version: string; elo: number; sha256: string }[];
  diagnostics: { mode: number; seats: number; no_spawn_seats: number; ships_built: number; mined: number; delivered: number; deaths: number }[] };

export default function RuleExperiments({ slug }: { slug: string }) {
  const { search } = useLocation();
  const scenario = search.get("scenario") || "combined";
  const batch = search.get("batch") || "";
  const mode = ["2", "4", "8"].includes(search.get("mode") || "") ? search.get("mode")! : "2";
  const update = (key: string, value: string) => { const next = new URLSearchParams(search); next.set(key, value); navigate(`/contests/${slug}/experiments?${next}`); };
  const report = useApi<Results>(`/contests/${slug}/experiments?scenario=${encodeURIComponent(scenario)}&batch=${encodeURIComponent(batch)}`, 30000);
  if (report.loading) return <Loading />;
  if (!report.data) return <ErrorBox message={report.error || "尚无实验数据"} />;
  const d = report.data, selected = d.scenarios.find((c) => c.key === d.selected)!;
  const rows = d.standings[mode] || [];
  const diag = d.diagnostics.find((item) => item.mode === Number(mode));
  return <div className="flex min-w-0 flex-col gap-5">
    <ErrorBox message={report.error} />
    <div className="pixel-frame p-4">
      <p className="mt-0">{d.selected_batch.label} · 每步 {d.selected_batch.turn_timeout_ms} ms · 单 Bot CPU {d.selected_batch.bot_cpu_percent}%{d.selected_batch.worker_cpus?.length ? " · 每场独立 1 核" : ""}</p>
      <p>执行主机：{d.execution_host} · 已完成 {number(d.progress.counts.complete || 0)} / {number(d.progress.total)} 场 · 运行 {number(d.progress.counts.running || 0)} · 等待 {number(d.progress.counts.queued || 0)} · 失败 {number(d.progress.counts.failed || 0)}{d.progress.counts.cancelled ? ` · 停止派发 ${number(d.progress.counts.cancelled)}` : ""}</p>
      <p className="mb-0 text-ink-2">固定现有 Bot 源码和版本，按规则变体分别统计。综合新规则为主排行，实验结果不计入 #0 或全局 ELO。旧 Bot 可能硬编码容量、费用或地图环绕；零造船和零搬运也属于迁移结果。每组仅使用一个地形种子和座位轮换，不能据此确定普遍的规则优劣。</p>
    </div>
    <div className="flex flex-wrap gap-4"><label className="flex items-center gap-2">执行批次<select aria-label="执行批次" value={d.selected_batch.key} onChange={(e) => update("batch",e.target.value)} className="h-9 max-w-full border border-line bg-paper-2 px-2">{d.execution_batches.map((b)=><option key={b.key} value={b.key}>{b.label}</option>)}</select></label><label className="flex min-w-0 flex-wrap items-center gap-2">规则实验<select aria-label="规则实验" value={scenario} onChange={(e) => update("scenario", e.target.value)} className="h-9 max-w-full border border-line bg-paper-2 px-2">{d.scenarios.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select></label>
      <label className="flex items-center gap-2">人数<select aria-label="实验人数" value={mode} onChange={(e) => update("mode", e.target.value)} className="h-9 border border-line bg-paper-2 px-2"><option value="2">1v1</option><option value="4">4 人</option><option value="8">8 人</option></select></label></div>
    <div className="pixel-frame min-w-0 p-4">
      <h2 className="mt-0 text-xl">{selected.label}</h2><p>{selected.setups[mode].width}×{selected.setups[mode].height} · {selected.setups[mode].turns} 步 · 地形种子 {selected.map_seeds.join(", ")} · 本组已完成 {selected.counts.complete || 0} / {selected.total}</p>
      {rows.length ? <div className="overflow-x-auto"><table className="ptable"><thead><tr><th>Bot</th><th className="right">场次</th><th className="right">原始 ELO</th><th className="right">第一名比例</th><th className="right">场均得分</th></tr></thead><tbody>{rows.map((row) => <tr key={row.version_id}><td className="max-w-64"><a className="block truncate text-blue hover:underline" title={`${row.bot_name} v${row.version}`} href={`/bots/${row.bot_id}`}>{row.target ? "基准 · " : ""}{row.bot_name} v{row.version}</a></td><td className="right num">{row.games}</td><td className="right num">{Math.round(row.elo)}</td><td className="right num">{percent(row.win_rate, 1)}</td><td className="right num">{number(Math.round(row.mean_score))}</td></tr>)}</tbody></table></div> : <Empty title="这一人数模式尚未完成对局">远端完成后自动回传，页面每 30 秒刷新。</Empty>}
      {diag && <p className="mb-0 text-ink-2">{diag.seats} 个座位场次 · 零造船 {diag.no_spawn_seats} · 造船 {number(diag.ships_built)} · 采矿 {number(diag.mined)} · 搬运 {number(diag.delivered)}</p>}
      <details className="mt-4"><summary className="cursor-pointer text-blue">本模式完整规则</summary><pre className="max-h-96 overflow-auto bg-paper p-3 text-sm">{JSON.stringify(selected.setups[mode].rules, null, 2)}</pre></details>
    </div>
    <details className="pixel-frame p-4"><summary className="cursor-pointer text-blue">固定的 8 个强 Bot 与源码摘要</summary><ul className="break-words pl-5">{d.roster.map((bot) => <li key={bot.version_id}><a className="text-blue" href={`/bots/${bot.bot_id}`}>{bot.bot_name} v{bot.version}</a> · 选取时原始 ELO {bot.elo}<code className="block text-xs text-ink-3">SHA-256 {bot.sha256}</code></li>)}</ul></details>
    <div className="pixel-frame overflow-x-auto p-4"><table className="ptable"><caption className="mb-3 text-left">所有规则变体的完成进度</caption><thead><tr><th>实验</th><th className="right">完成 / 总场次</th><th className="right">失败</th></tr></thead><tbody>{d.scenarios.map((c) => <tr key={c.key}><td><button className="cursor-pointer text-left text-blue hover:underline" onClick={() => update("scenario", c.key)}>{c.label}</button></td><td className="right num">{c.counts.complete || 0} / {c.total}</td><td className="right num">{c.counts.failed || 0}</td></tr>)}</tbody></table></div>
  </div>;
}
