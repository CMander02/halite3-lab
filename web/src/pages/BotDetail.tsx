import { ArrowLeft, ArrowRight, Download, Trophy } from "@nsmr/pixelart-react";
import type { BotProfile, User } from "@/lib/types";
import { date, percent, useApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Empty, ErrorBox, Loading, PageHead, Panel, Stat, Tag, TierBadge } from "@/components/pixel";
import { BotIcon } from "@/components/BotIcon";
import { SetupLine, correctionLabel, useCatalog } from "@/components/ModelBadge";
import { VersionEloChart } from "@/components/charts";

const STAGE: Record<string, string> = { draft: "草稿", upcoming: "未开始", open: "提交中", closed: "评测中", finished: "已结束" };

export default function BotDetail({ id, user }: { id: string; user: User | null }) {
  const { data, error, loading } = useApi<BotProfile>(`/bots/${id}/profile`);
  const catalog = useCatalog();
  if (loading) return <Loading />;
  if (!data) return <ErrorBox message={error || "Bot 不存在。"} />;
  const { bot, versions } = data;
  const rated = versions.filter((v) => v.elo);
  const best = rated.reduce<(typeof rated)[number] | null>((a, v) => (!a || v.elo!.adjusted_elo > a.elo!.adjusted_elo ? v : a), null);
  const latest = versions[versions.length - 1];
  const contests = new Set(versions.flatMap((v) => v.contests.map((c) => c.contest_id)));
  const chart = versions.map((v) => ({
    label: `v${v.version}`,
    elo: v.elo ? Math.round(v.elo.elo) : undefined,
    adjusted: v.elo ? Math.round(v.elo.adjusted_elo) : undefined,
    contest: v.contests.find((c) => c.final)?.final?.adjusted_elo ?? v.contests.find((c) => c.bench)?.bench?.adjusted_elo,
  }));
  return (
    <>
      <a href="/bots" className="mb-4 inline-flex items-center gap-1 text-ink-2 hover:text-blue">
        <ArrowLeft size={14} /> {user ? "我的 Bots" : "Bots"}
      </a>
      <PageHead
        eyebrow={bot.builtin ? "平台基准" : `Bot · ${bot.author}`}
        title={
          <span className="flex items-center gap-3">
            {!bot.builtin && <BotIcon id={bot.id} model={latest?.attribution?.model.value} catalog={catalog} />}
            {bot.name}
          </span>
        }
        description={bot.description || "尚未添加简介"}
        action={
          <Button variant="outline" asChild>
            <a href={`/matches?version=${latest?.id || ""}`}>
              最新版本对局 <ArrowRight size={12} />
            </a>
          </Button>
        }
      />
      <div className="mb-6 grid grid-cols-2 gap-6 lg:grid-cols-4">
        <Stat label="版本" value={versions.length} hint={latest ? `最新 v${latest.version} · ${date(latest.created_at)}` : undefined} />
        <Stat label="最高修正后 ELO" value={best ? Math.round(best.elo!.adjusted_elo) : "—"} hint={best ? `v${best.version}${best.elo!.rank ? ` · 总榜 #${best.elo!.rank}` : ""}` : "还没有公开对局"} />
        <Stat label="最新版本 ELO" value={latest?.elo ? Math.round(latest.elo.adjusted_elo) : "—"} hint={latest?.elo ? `原始 ${Math.round(latest.elo.elo)} · 修正 ${correctionLabel(latest.elo.correction)}` : undefined} />
        <Stat label="参加比赛" value={contests.size} />
      </div>
      {versions.length > 1 && (
        <Panel title="版本迭代 · ELO" className="mb-6">
          <VersionEloChart data={chart} />
          <p className="mt-2 mb-0 text-ink-3">蓝线：全局修正后 ELO；虚线：原始 ELO；黑线：比赛中的修正后 ELO（有正式结果用正式结果，否则用提交期临时 ELO）。</p>
        </Panel>
      )}
      <Panel title="版本" bodyClassName="p-0 overflow-x-auto">
        {versions.length ? (
          <table className="ptable">
            <thead>
              <tr>
                <th>版本</th>
                <th>模型 · 推理 · 平台</th>
                <th className="right">原始 ELO</th>
                <th className="right text-blue">修正后</th>
                <th className="right">总榜</th>
                <th className="right">胜率 · 场次</th>
                <th>Tier</th>
                <th>比赛</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {[...versions].reverse().map((v) => (
                <tr key={v.id} className={cn(v.archived && "opacity-60")}>
                  <td className="max-w-[260px]">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-blue">v{v.version}</span>
                      <Tag>{v.language === "cpp" ? "C++17" : "Python"}</Tag>
                      {v.is_default && <Tag className="border-ink text-ink">默认</Tag>}
                      {v.archived && <Tag>已归档</Tag>}
                      {!v.listed && <Tag>未上榜</Tag>}
                    </div>
                    <div className="truncate text-ink-2">{v.notes || "未填写版本说明"}</div>
                    <div className="text-ink-3">{date(v.created_at)}</div>
                  </td>
                  <td className="max-w-[240px]">{bot.builtin ? <span className="text-ink-3">平台基准</span> : <SetupLine attribution={v.attribution} catalog={catalog} compact />}</td>
                  <td className="right num text-ink-2">
                    {v.elo ? (
                      <>
                        {Math.round(v.elo.elo)}
                        <span className="text-ink-3"> ±{Math.round(v.elo.elo_sd)}</span>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="right num text-[20px]">{v.elo ? Math.round(v.elo.adjusted_elo) : "—"}</td>
                  <td className="right num text-ink-2">{v.elo?.rank ? `#${v.elo.rank}` : "—"}</td>
                  <td className="right num text-ink-2">{v.elo ? `${percent(v.elo.win_rate)} · ${v.elo.games}` : "—"}</td>
                  <td>{v.ranked?.tier ? <TierBadge tier={v.ranked.tier} /> : v.ranked ? <span className="text-ink-3">{`${v.ranked.complete}/${v.ranked.total}`}</span> : <span className="text-ink-3">—</span>}</td>
                  <td className="max-w-[280px]">
                    <div className="flex flex-col gap-1">
                      {v.contests.length
                        ? v.contests.map((c) => (
                            <a key={c.contest_id + c.seq} href={`/contests/${c.slug}`} className="flex flex-wrap items-center gap-1.5 hover:text-blue">
                              <Trophy size={12} className="text-blue" />
                              <span className="truncate">{c.title}</span>
                              <span className="text-ink-3">
                                #{c.seq} · {STAGE[c.status]}
                              </span>
                              {c.final?.rank ? (
                                <Tag className="border-blue text-blue">正式第 {c.final.rank}</Tag>
                              ) : c.bench ? (
                                <span className="num text-ink-2">
                                  临时 {Math.round(c.bench.adjusted_elo)}
                                  {c.bench.rank ? ` · #${c.bench.rank}` : ""}
                                </span>
                              ) : null}
                            </a>
                          ))
                        : <span className="text-ink-3">—</span>}
                    </div>
                  </td>
                  <td className="right">
                    <span className="flex justify-end gap-2">
                      {(bot.owned || bot.builtin) && (
                        <Button variant="ghost" size="icon-sm" asChild>
                          <a href={`/api/versions/${v.id}/source`} aria-label="下载源码">
                            <Download size={14} />
                          </a>
                        </Button>
                      )}
                      <a className="inline-flex items-center gap-1 text-blue" href={`/matches?version=${v.id}`}>
                        对局 <ArrowRight size={12} />
                      </a>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty title="还没有版本" />
        )}
      </Panel>
      {!bot.owned && !bot.builtin && <p className="mt-3 mb-0 text-ink-3">只显示已上榜或参加过比赛的版本。源码始终私有。</p>}
    </>
  );
}
