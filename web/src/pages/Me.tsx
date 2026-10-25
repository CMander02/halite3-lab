import { useMemo, useState } from "react";
import { Trophy, Eye, EyeClosed, Script, ArrowRight, Upload, Archive } from "@nsmr/pixelart-react";
import type { CatalogKind, Submission, User } from "@/lib/types";
import { api, date, number, percent, useApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Empty, ErrorBox, Loading, PageHead, Panel, Stat, Tag, TierBadge } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";
import { CONFIDENCE, SOURCE, CatalogChip, correctionLabel, entry, useCatalog } from "@/components/ModelBadge";

const KINDS: [CatalogKind, string][] = [
  ["model", "模型"],
  ["effort", "推理"],
  ["harness", "平台"],
];

const minutes = (s: number | null | undefined) => (s == null ? "—" : s < 3600 ? `${Math.max(1, Math.round(s / 60))} 分钟` : `${(s / 3600).toFixed(1)} 小时`);

function SetupTable({ item }: { item: Submission }) {
  const catalog = useCatalog();
  const d = item.detection;
  return (
    <table className="ptable">
      <thead>
        <tr>
          <th />
          <th>声明</th>
          <th>轨迹检测</th>
          <th>计分采用</th>
          <th className="right">修正</th>
        </tr>
      </thead>
      <tbody>
        {KINDS.map(([kind, label]) => {
          const p = item.attribution[kind];
          const conf = d ? (d[`${kind}_confidence` as const] as string) : "none";
          return (
            <tr key={kind}>
              <td className="text-ink-2">{label}</td>
              <td>
                <CatalogChip kind={kind} id={p.declared} catalog={catalog} />
              </td>
              <td>
                {d ? (
                  <span className={cn("flex items-center gap-1.5", item.attribution.mismatch.includes(kind) && "text-warn")}>
                    <CatalogChip kind={kind} id={p.detected} catalog={catalog} />
                    <span className="text-ink-3">· {CONFIDENCE[conf] || conf}</span>
                  </span>
                ) : (
                  <span className="text-ink-3">无轨迹</span>
                )}
              </td>
              <td>
                <CatalogChip kind={kind} id={p.value} catalog={catalog} />
                <span className="block text-[12px] text-ink-3">{SOURCE[p.source]}</span>
              </td>
              <td className="right num">{correctionLabel(p.offset)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function SubmissionCard({ item, busy, act }: { item: Submission; busy: boolean; act: (path: string, method: string, body?: object) => void }) {
  const r = item.ranked;
  const e = item.elo;
  const d = item.detection;
  const progress = r ? `${r.complete}/${r.total}` : null;
  return (
    <article className={cn("border-t border-line first:border-0", item.archived && "opacity-60")}>
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1.4fr)_minmax(220px,0.9fr)]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[24px] leading-[28px] text-blue">v{item.version}</span>
            <Tag>{item.language === "cpp" ? "C++17" : "Python"}</Tag>
            {item.archived && <Tag>已归档</Tag>}
            {!item.listed && <Tag className="border-warn text-warn">不在排行榜显示</Tag>}
          </div>
          <p className="mt-1 mb-2 text-ink-2">{item.notes || "未填写版本说明"}</p>
          <div className="text-ink-3">
            {date(item.created_at)} · {item.filename} · {(item.size / 1024).toFixed(1)} KiB
          </div>
          {item.trace ? (
            <div className="mt-2 text-ink-3">
              轨迹 {item.trace.filename} · {(item.trace.size / 1024 / 1024).toFixed(2)} MiB
              {d && (
                <>
                  <br />
                  {number(d.messages)} 条消息 · 输出 {number(d.output_tokens)} tokens · 用时 {minutes(d.duration_seconds)}
                </>
              )}
            </div>
          ) : (
            <div className="mt-2 text-warn">没有上传对话轨迹，按声明计分。</div>
          )}
        </div>
        <div className="min-w-0 overflow-x-auto">
          <SetupTable item={item} />
        </div>
        <div className="flex min-w-0 flex-col gap-3">
          {e ? (
            <div className="flex items-end gap-3">
              <div>
                <div className="num text-[36px] leading-[40px]">{Math.round(e.adjusted_elo)}</div>
                <div className="text-ink-2">修正后 ELO</div>
              </div>
              <div className="pb-1 text-ink-3">
                原始 {Math.round(e.elo)} ±{Math.round(e.elo_sd)}
                <br />
                修正 {correctionLabel(e.correction)}
              </div>
              <div className="ml-auto text-right">
                <div className="num text-[24px] leading-[28px] text-blue">{e.rank ? `#${e.rank}` : "—"}</div>
                <div className="text-ink-3">总排名</div>
              </div>
            </div>
          ) : (
            <div className="text-ink-2">{r ? "评测进行中，完成后计算 ELO。" : "尚未参评，没有公开对局。"}</div>
          )}
          {r && (
            <div className="flex items-center gap-2 text-ink-2">
              {r.tier ? <TierBadge tier={r.tier} /> : <Tag>评测 {progress}</Tag>}
              {r.tier ? `基准评测 ${r.wins}/${r.total} 胜 · ${percent(r.win_rate)}` : r.counts.failed ? `${r.counts.failed} 场失败` : "排队 / 运行中"}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {!r && !item.archived && (
              <Button size="sm" disabled={busy} onClick={() => act(`/versions/${item.id}/rank`, "POST", {})}>
                <Trophy size={14} /> 参加评测
              </Button>
            )}
            <Button variant="outline" size="sm" disabled={busy} onClick={() => act(`/versions/${item.id}`, "PATCH", { listed: !item.listed })}>
              {item.listed ? <EyeClosed size={14} /> : <Eye size={14} />} {item.listed ? "榜单隐藏" : "榜单显示"}
            </Button>
            {r && (
              <Button variant="ghost" size="sm" asChild>
                <a href={`/matches?version=${item.id}`}>
                  对局 <ArrowRight size={12} />
                </a>
              </Button>
            )}
            {item.trace && (
              <Button variant="ghost" size="sm" asChild>
                <a href={`/api/versions/${item.id}/trace`}>
                  <Script size={14} /> 轨迹
                </a>
              </Button>
            )}
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => act(`/versions/${item.id}`, "PATCH", { archived: !item.archived })}>
              <Archive size={14} /> {item.archived ? "取消归档" : "归档"}
            </Button>
          </div>
        </div>
      </div>
    </article>
  );
}

export default function Me({ user }: { user: User | null }) {
  const { data, error, loading, refresh } = useApi<{ submissions: Submission[] }>(user ? "/me/submissions" : null, 20000);
  const catalog = useCatalog();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const items = data?.submissions || [];
  const bots = useMemo(() => {
    const map = new Map<string, Submission[]>();
    for (const item of items) map.set(item.bot_id, [...(map.get(item.bot_id) || []), item]);
    return [...map.values()];
  }, [items]);
  const rated = items.filter((i) => i.elo);
  const best = rated.reduce<Submission | null>((a, b) => (!a || (b.elo!.adjusted_elo > a.elo!.adjusted_elo) ? b : a), null);
  const ranks = rated.map((i) => i.elo!.rank).filter((r): r is number => r != null);

  if (!user)
    return (
      <Empty title="登录后查看自己的提交">
        <a className="text-blue" href="/login">
          登录 &gt;
        </a>
      </Empty>
    );

  async function act(path: string, method: string, body?: object) {
    setBusy(true);
    setMessage("");
    try {
      await api(path, { method, body: JSON.stringify(body || {}) });
      await refresh();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        eyebrow="我的主页"
        title={
          <span className="flex items-center gap-3">
            <UserAvatar id={user.id} name={user.display_name} version={user.avatar_version} size="lg" />
            {user.display_name}
          </span>
        }
        description="每次提交的版本、生成它的模型与推理强度、轨迹检测结果，以及修正后的 ELO 与排名。"
        action={
          <Button asChild>
            <a href="/bots">
              <Upload size={16} /> 上传新版本
            </a>
          </Button>
        }
      />
      <ErrorBox message={error || message} />
      <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="提交版本" value={number(items.length)} hint={`${bots.length} 个 Bot`} />
        <Stat label="已有 ELO" value={number(rated.length)} hint={`${items.filter((i) => i.ranked && !i.ranked.tier).length} 个评测中`} />
        <Stat label="最佳修正后 ELO" value={best ? Math.round(best.elo!.adjusted_elo) : "—"} hint={best ? `${best.bot_name} v${best.version}` : undefined} />
        <Stat label="最佳排名" value={ranks.length ? `#${Math.min(...ranks)}` : "—"} hint="修正后 ELO 总榜" />
      </div>
      {loading ? (
        <Loading />
      ) : bots.length ? (
        <div className="flex flex-col gap-6">
          {bots.map((versions) => {
            const head = versions[0];
            const rated = versions.filter((v) => v.elo);
            return (
              <Panel
                key={head.bot_id}
                title={
                  <span className="text-[16px]">
                    {head.bot_name} <span className="text-ink-3">· {versions.length} 个版本</span>
                  </span>
                }
                action={
                  rated.length > 1 ? (
                    <span className="hidden items-center gap-2 text-ink-2 sm:flex">
                      ELO 走势
                      {[...rated].reverse().map((v) => (
                        <span key={v.id} className="num text-ink">
                          v{v.version} {Math.round(v.elo!.adjusted_elo)}
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className="text-ink-3">
                      <CatalogChip kind="model" id={head.attribution.model.value} catalog={catalog} /> {entry(catalog, "effort", head.attribution.effort.value).name}
                    </span>
                  )
                }
                bodyClassName="p-0"
              >
                {versions.map((item) => (
                  <SubmissionCard key={item.id} item={item} busy={busy} act={(p, m, b) => void act(p, m, b)} />
                ))}
              </Panel>
            );
          })}
        </div>
      ) : (
        <Empty title="还没有提交">
          在 <a className="text-blue" href="/bots">Bots</a> 页创建 Bot，上传源码和对话轨迹。
        </Empty>
      )}
    </>
  );
}
