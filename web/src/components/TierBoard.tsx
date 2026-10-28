import { ArrowRight, List } from "@nsmr/pixelart-react";
import type { LeaderEntry } from "@/lib/types";
import { number, useApi } from "@/lib/api";
import { PRACTICE } from "@/lib/sitemap";
import { cn } from "@/lib/utils";
import { Empty, ErrorBox, Loading, Panel, TierBadge } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";

const TIERS = [
  { tier: "S", rule: "胜率 ≥ 75%" },
  { tier: "A", rule: "≥ 50%" },
  { tier: "B", rule: "≥ 25%" },
  { tier: "C", rule: "< 25%" },
];

export type TierData = { entries: LeaderEntry[]; season: string; required_games: number };

/** The Tier list: contest #0's fixed 12-game benchmark, one row per evaluated version. */
export function TierBoard() {
  const { data, error, loading } = useApi<TierData>("/leaderboard");
  const entries = data?.entries || [];
  if (loading) return <Loading />;
  return (
    <div className="flex flex-col gap-6">
      <ErrorBox message={error} />
      <div className="flex flex-col border border-ink">
        {TIERS.map(({ tier, rule }) => {
          const row = entries.filter((e) => e.tier === tier);
          return (
            <div key={tier} className="flex min-h-16 border-b border-line last:border-0">
              <div className={cn("flex w-20 shrink-0 flex-col items-center justify-center gap-1 border-r border-line sm:w-28", tier === "S" && "bg-ink text-paper", tier === "A" && "bg-blue text-white", tier === "B" && "bg-blue-100", tier === "C" && "bg-paper")}>
                <span className="font-pixel text-[36px] leading-[36px]">{tier}</span>
                <span className="text-[13px] opacity-80">{rule}</span>
              </div>
              <div className="flex flex-1 flex-wrap items-center gap-2 p-2">
                {row.length ? (
                  row.map((e) => (
                    <a key={e.version_id} href={`/bots/${e.bot_id}`} className="flex items-center gap-2 border border-line bg-paper-2 py-1 pr-3 pl-1 hover:border-ink">
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
      <Panel title="完整排名" icon={List} bodyClassName="p-0 overflow-x-auto">
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
                  <td className="num font-pixel text-ink-3">{String(i + 1).padStart(2, "0")}</td>
                  <td>
                    <TierBadge tier={e.tier} />
                  </td>
                  <td>
                    <a href={`/bots/${e.bot_id}`} className="flex min-w-0 items-center gap-2 hover:text-blue">
                      <UserAvatar id={e.author_id} name={e.author} size="sm" />
                      <span className="min-w-0">
                        <span className="block truncate">
                          {e.bot_name} <span className="text-ink-3">v{e.version}</span>
                        </span>
                        <span className="block truncate text-ink-3">{e.author}</span>
                      </span>
                    </a>
                  </td>
                  <td className="right num font-pixel text-[24px] leading-[24px]">{(e.win_rate * 100).toFixed(1)}%</td>
                  <td className="right num text-ink-2">
                    {e.wins}/{e.games}
                  </td>
                  <td className="right num">{number(Math.round(e.mean_score))}</td>
                  <td className="right">
                    <a className="inline-flex items-center gap-1 text-blue" href={`${PRACTICE}/matches?version=${e.version_id}`}>
                      回放 <ArrowRight size={12} />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty title="还没有完成 12 场评测的版本">在本比赛的“我的提交”上传 bot.cpp 即可参评。</Empty>
        )}
      </Panel>
      <p className="m-0 text-ink-3">
        Tier 只来自 #0 的固定评测（{data?.season}）：对阵 baseline 与 raider，种子 11 / 29 / 47，交换座位，共 {data?.required_games ?? 12} 场。每个参评版本一行；私人对练不计入。
      </p>
    </div>
  );
}
