import { Play, ChevronRight, Trophy } from "@nsmr/pixelart-react";
import type { Match } from "@/lib/types";
import { ago, number } from "@/lib/api";
import { playerColor } from "@/lib/colors";
import { Empty, ModeLabel, Status, Tag } from "@/components/pixel";
import { AvatarStack } from "@/components/UserAvatar";

const kindLabel = (kind: string) =>
  kind === "ranked" ? "基准评测" : kind === "ranked-multi" ? "多人评测" : kind === "demo" ? "公开示例" : kind === "contest-final" ? "比赛正式评测" : "私人测试";

function winnerOf(match: Match) {
  if (!match.result) return null;
  const entry = Object.entries(match.result.stats).find(([, s]) => s.rank === 1);
  if (!entry) return null;
  const index = Number(entry[0]);
  return { index, seat: match.seats[index], score: entry[1].score };
}

function Seats({ match, limit = 8 }: { match: Match; limit?: number }) {
  const winner = winnerOf(match);
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5">
      {match.seats.slice(0, limit).map((seat, i) => (
        <span key={i} className={winner?.index === i ? "text-ink" : "text-ink-2"}>
          <span style={{ color: playerColor(i) }}>■</span> {seat.name}
          <span className="text-ink-3"> v{seat.version}</span>
          {winner?.index === i && <Trophy size={12} className="ml-0.5 inline align-[-1px] text-blue" />}
        </span>
      ))}
      {match.seats.length > limit && <span className="text-ink-3">+{match.seats.length - limit}</span>}
    </div>
  );
}

export default function MatchList({ matches, compact = false }: { matches: Match[]; compact?: boolean }) {
  if (!matches.length)
    return (
      <Empty title="还没有对战记录">提交一组测试后，运行状态和回放会出现在这里。</Empty>
    );

  if (compact)
    return (
      <div className="flex flex-col">
        {matches.map((match) => (
          <a key={match.id} href={`/matches/${match.id}`} className="group border-b border-line-2 px-3 py-2.5 hover:bg-blue-50">
            <div className="mb-1 flex items-center justify-between gap-2 text-ink-3">
              <span>
                <ModeLabel mode={match.mode} /> · {kindLabel(match.kind)}{match.kind === "contest-final" && match.execution ? ` · ${match.execution.turn_timeout_ms} ms` : ""}
              </span>
              <span>{ago(match.created_at)}</span>
            </div>
            <Seats match={match} limit={4} />
          </a>
        ))}
      </div>
    );

  return (
    <>
      {/* desktop table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="ptable">
          <thead>
            <tr>
              <th>对局</th>
              <th>参与者</th>
              <th>模式</th>
              <th>胜者</th>
              <th className="right">种子</th>
              <th>状态</th>
              <th className="right">时间</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {matches.map((match) => {
              const winner = winnerOf(match);
              return (
                <tr key={match.id}>
                  <td className="max-w-[420px]">
                    <Seats match={match} />
                    <span className="text-ink-3">{kindLabel(match.kind)}{match.kind === "contest-final" && match.execution ? ` · ${match.execution.turn_timeout_ms} ms` : ""}</span>
                  </td>
                  <td>
                    <AvatarStack seats={match.seats} />
                  </td>
                  <td className="whitespace-nowrap">
                    <ModeLabel mode={match.mode} />
                  </td>
                  <td className="whitespace-nowrap">
                    {winner ? (
                      <>
                        <span style={{ color: playerColor(winner.index) }}>■</span> {winner.seat?.name}
                        <div className="num text-ink-3">{number(winner.score)} 矿</div>
                      </>
                    ) : (
                      <span className="text-ink-3">—</span>
                    )}
                  </td>
                  <td className="right num text-ink-2">{match.seed}</td>
                  <td>
                    <Status value={match.status} />
                    {match.error && <div className="max-w-[200px] truncate text-bad" title={match.error}>{match.error}</div>}
                  </td>
                  <td className="right whitespace-nowrap text-ink-2">{ago(match.created_at)}</td>
                  <td className="right">
                    <a
                      href={`/matches/${match.id}`}
                      className={`notch inline-flex h-8 items-center gap-1.5 px-3 whitespace-nowrap ${match.has_replay ? "bg-blue text-white hover:bg-ink" : "bg-blue-50 text-blue hover:bg-blue-100"}`}
                    >
                      {match.has_replay ? <Play size={14} /> : <ChevronRight size={14} />}
                      {match.has_replay ? "回放" : "详情"}
                    </a>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {/* phone cards */}
      <div className="flex flex-col md:hidden">
        {matches.map((match) => {
          const winner = winnerOf(match);
          return (
            <a key={match.id} href={`/matches/${match.id}`} className="flex gap-3 border-b border-line-2 p-3 active:bg-blue-50">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center gap-2 text-ink-3">
                  <Tag>
                    <ModeLabel mode={match.mode} />
                  </Tag>
                  <span>{kindLabel(match.kind)}{match.kind === "contest-final" && match.execution ? ` · ${match.execution.turn_timeout_ms} ms` : ""}</span>
                  <span className="ml-auto">{ago(match.created_at)}</span>
                </div>
                <Seats match={match} limit={4} />
                <div className="mt-2 flex items-center justify-between">
                  <AvatarStack seats={match.seats} />
                  {winner ? <span className="num text-ink-2">胜 {number(winner.score)}</span> : <Status value={match.status} />}
                </div>
              </div>
              <span className="flex items-center text-blue">{match.has_replay ? <Play size={18} /> : <ChevronRight size={18} />}</span>
            </a>
          );
        })}
      </div>
    </>
  );
}
