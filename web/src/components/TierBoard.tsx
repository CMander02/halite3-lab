import { ArrowRight, List } from "@nsmr/pixelart-react";
import type { EloEntry, LeaderEntry } from "@/lib/types";
import { number, percent, useApi } from "@/lib/api";
import { PRACTICE } from "@/lib/sitemap";
import { cn } from "@/lib/utils";
import { Empty, ErrorBox, Loading, Panel, TierBadge } from "@/components/pixel";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Who, fullName } from "@/components/BotWho";

const TIERS = [
  { tier: "S", rule: "胜率 ≥ 75%" },
  { tier: "A", rule: "≥ 50%" },
  { tier: "B", rule: "≥ 25%" },
  { tier: "C", rule: "< 25%" },
];

/** The Tier list: contest #0's fixed 12-game benchmark, one row per evaluated version.
 * Shown in #0's Tier tab and in the global leaderboard's Tier view. */
export function TierBoard() {
  const tiers = useApi<{ entries: LeaderEntry[]; season: string; required_games: number }>("/leaderboard");
  const elo = useApi<{ entries: EloEntry[] }>("/leaderboard/elo");
  const rated = new Map((elo.data?.entries || []).map((e) => [e.version_id, e]));
  const entries = (tiers.data?.entries || []).map((e) => ({ ...e, model: rated.get(e.version_id)?.attribution?.model.value }));
  if (tiers.loading) return <Loading />;
  return (
    <div className="flex flex-col gap-6">
      <ErrorBox message={tiers.error} />
      <div className="flex flex-col border border-ink">
        {TIERS.map(({ tier, rule }) => {
          const row = entries.filter((e) => e.tier === tier);
          return (
            <div key={tier} className="flex min-h-16 border-b border-line last:border-0">
              <div className={cn("flex w-20 shrink-0 flex-col items-center justify-center gap-1 border-r border-line sm:w-28", tier === "S" && "bg-ink text-paper", tier === "A" && "bg-blue text-white", tier === "B" && "bg-blue-100", tier === "C" && "bg-paper")}>
                <span className="font-pixel text-[36px] leading-[36px]">{tier}</span>
                <span className="text-[13px] opacity-80">{rule}</span>
              </div>
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 p-2">
                {row.length ? (
                  row.map((e) => (
                    <Tooltip key={e.version_id}>
                      <TooltipTrigger asChild>
                        <a href={`/bots/${e.bot_id}`} className="flex w-64 max-w-full min-w-0 items-center gap-2 border border-line bg-paper-2 py-2 pr-2 pl-2 hover:border-ink" aria-label={`${fullName(e)}，胜率 ${percent(e.win_rate)}`}>
                          <Who e={e} />
                          <span className="num ml-auto shrink-0 text-blue">{percent(e.win_rate)}</span>
                        </a>
                      </TooltipTrigger>
                      <TooltipContent className="max-w-xs break-words">
                        {fullName(e)} · 胜率 {percent(e.win_rate)}
                      </TooltipContent>
                    </Tooltip>
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
                  <td className="max-w-[280px]">
                    <a href={`/bots/${e.bot_id}`} className="block hover:text-blue">
                      <Who e={e} />
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
          <Empty title="还没有完成 12 场评测的版本">在 #0 的“我的提交”上传 bot.cpp 即可参评。</Empty>
        )}
      </Panel>
      <p className="m-0 text-ink-3">
        Tier 是 #0 测试比赛的成绩（{tiers.data?.season}）：对阵 baseline 与 raider，种子 11 / 29 / 47，交换座位，共 {tiers.data?.required_games ?? 12} 场。每个参评版本一行；私人对练不计入。
      </p>
    </div>
  );
}
