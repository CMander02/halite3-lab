import { useMemo, useState, type FormEvent } from "react";
import { Plus, Play, Reload, Close, ArrowRight, ArrowLeft, List, Tournament } from "@nsmr/pixelart-react";
import type { Bot, Job, User } from "@/lib/types";
import { api, date, number, useApi } from "@/lib/api";
import { navigate, useLocation } from "@/lib/router";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Empty, ErrorBox, Loading, PageHead, Panel, PixelBar, Status } from "@/components/pixel";
import MatchList from "@/components/MatchList";

function combinations(n: number, k: number) {
  if (n < k) return 0;
  let result = 1;
  for (let i = 0; i < k; i++) result = (result * (n - i)) / (i + 1);
  return Math.round(result);
}

function Progress({ job }: { job: Job }) {
  const done = job.counts.complete || 0;
  return (
    <div className="flex items-center gap-3">
      <PixelBar value={done} max={job.total} className="h-2.5 flex-1" />
      <span className="num w-20 shrink-0 text-right">
        {done}/{job.total}
      </span>
    </div>
  );
}

export default function Tests({ user, jobId }: { user: User | null; jobId?: string }) {
  const { search } = useLocation();
  const list = useApi<{ jobs: Job[] }>(user && !jobId ? "/tests" : null, 4000);
  const detail = useApi<Job>(user && jobId ? `/tests/${jobId}` : null, 3000);
  const bots = useApi<{ bots: Bot[] }>(user ? "/bots" : null);
  const [create, setCreate] = useState(search.has("new"));
  const [selected, setSelected] = useState<string[]>([]);
  const [modes, setModes] = useState([2]);
  const [seeds, setSeeds] = useState("11,29,47");
  const [rotate, setRotate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const options = useMemo(() => bots.data?.bots.flatMap((b) => b.versions.filter((v) => v.eligible).map((v) => ({ ...v, bot_name: b.name, builtin: b.builtin }))) || [], [bots.data]);
  const seedList = seeds.split(/[,，\s]+/).filter(Boolean);
  // The admin has no quotas; the larger per-job cap only guards against typos.
  const maxBots = user?.is_admin ? Infinity : 10;
  const maxGames = user?.is_admin ? 20000 : 300;
  const count = modes.reduce((sum, k) => sum + combinations(selected.length, k) * (rotate ? k : 1), 0) * seedList.length;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("");
    try {
      const values = seedList.map(Number);
      if (values.some((v) => !Number.isSafeInteger(v) || v < 0 || v > 4294967295)) throw new Error("种子必须是 0 至 4294967295 的整数。");
      const r = await api<{ id: string }>("/tests", { method: "POST", body: JSON.stringify({ name: form.get("name"), version_ids: selected, modes, seeds: values, rotate_seats: rotate }) });
      navigate(`/tests/${r.id}`);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function action(name: "retry" | "cancel") {
    setBusy(true);
    setMessage("");
    try {
      await api(`/tests/${jobId}/${name}`, { method: "POST", body: "{}" });
      await detail.refresh();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!user)
    return (
      <>
        <PageHead eyebrow="测试任务" title="后端执行，离开网页也不中断" />
        <Empty title="登录后管理测试任务">
          <Button asChild>
            <a href="/login">登录 / 注册 &gt;</a>
          </Button>
        </Empty>
      </>
    );

  if (jobId) {
    const job = detail.data;
    return (
      <>
        <PageHead
          eyebrow={
            <a href="/tests" className="hover:text-blue">
              测试任务
            </a>
          }
          title={job?.name || "测试任务"}
          description="完成的比赛会保留；中断或失败的场次可以整场重试。"
          action={
            <Button variant="outline" asChild>
              <a href="/tests">
                <ArrowLeft size={14} /> 返回列表
              </a>
            </Button>
          }
        />
        <ErrorBox message={detail.error || message} />
        {detail.loading || !job ? (
          <Loading />
        ) : (
          <div className="flex flex-col gap-6">
            <section className="pixel-frame ticks flex flex-col gap-4 p-4 sm:p-6">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <Status value={job.status} />
                  <div className="num mt-1 font-pixel text-[48px] leading-[48px]">
                    {number(job.counts.complete || 0)}
                    <span className="font-pixel text-[24px] text-ink-3"> / {number(job.total)}</span>
                  </div>
                  <div className="text-ink-2">
                    等待 {job.counts.queued || 0} · 运行 {job.counts.running || 0} · 失败 {job.counts.failed || 0} · 取消 {job.counts.cancelled || 0}
                  </div>
                </div>
                <div className="flex gap-2">
                  {job.retryable && (
                    <Button variant="outline" disabled={busy} onClick={() => void action("retry")}>
                      <Reload size={14} /> 重试失败场次
                    </Button>
                  )}
                  {Boolean(job.counts.queued) && (
                    <Button variant="outline" disabled={busy} onClick={() => void action("cancel")}>
                      <Close size={14} /> 取消等待场次
                    </Button>
                  )}
                </div>
              </div>
              {Boolean(job.counts.failed) && !job.retryable && <p className="text-warn">历史任务含有不再支持的版本，无法重试。请上传 C++17 版本新建测试。</p>}
              <Progress job={job} />
            </section>
            <Panel title="比赛记录" icon={List} action={<span className="text-ink-3">每 3 秒更新</span>} bodyClassName="p-0">
              <MatchList matches={job.matches || []} />
            </Panel>
          </div>
        )}
      </>
    );
  }

  return (
    <>
      <PageHead
        eyebrow="测试任务"
        title="私人循环赛"
        description="选择版本和模式，后端生成赛程并自动收集结果。"
        action={
          <Button onClick={() => setCreate(!create)}>
            <Plus size={16} /> {create ? "收起" : "新建测试"}
          </Button>
        }
      />
      <ErrorBox message={list.error || message} />
      {create && (
        <Panel title="新建私人循环赛" icon={Tournament} tone="blue" className="mb-6" ticks>
          <form onSubmit={submit} className="flex flex-col gap-5">
            <div className="flex flex-col gap-1.5 sm:max-w-md">
              <Label htmlFor="job-name">任务名称</Label>
              <Input id="job-name" name="name" defaultValue="策略对照测试" required maxLength={80} />
            </div>
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-3">
                <span>参赛版本</span>
                <span className="text-ink-3">{user?.is_admin ? "至少 2 个（管理员不限数量）" : "2–10 个"}；仅 C++17 与平台固定基准，开始后固定版本</span>
                <Button
                  type="button"
                  variant="secondary"
                  size="xs"
                  onClick={() => {
                    const latest = (bots.data?.bots || []).map((b) => b.versions.find((v) => v.eligible && !v.archived)?.id).filter((id): id is string => Boolean(id));
                    if (latest.length > maxBots) return setMessage("超过 10 个 Bot，请手动选择。");
                    setSelected(latest);
                  }}
                >
                  选择各 Bot 最新版本
                </Button>
              </div>
              <div className="grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
                {options.map((v) => {
                  const on = selected.includes(v.id);
                  return (
                    <label key={v.id} className={cn("flex cursor-pointer items-center gap-2 px-3 py-2", on ? "bg-blue-50" : "bg-paper-2 hover:bg-blue-50")}>
                      <input type="checkbox" className="accent-[var(--blue)]" checked={on} onChange={(e) => setSelected(e.target.checked ? [...selected, v.id] : selected.filter((id) => id !== v.id))} />
                      <span className="min-w-0 flex-1 truncate">
                        {v.bot_name} <span className="text-ink-3">v{v.version}</span>
                      </span>
                      {v.builtin === 1 && <span className="text-ink-3">基准</span>}
                    </label>
                  );
                })}
              </div>
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <div className="mb-2">比赛模式</div>
                <div className="flex border border-ink w-fit">
                  {[2, 4, 8].map((k) => (
                    <button
                      type="button"
                      key={k}
                      className={cn("h-8 cursor-pointer px-3", modes.includes(k) ? "bg-ink text-paper" : "hover:bg-blue-50")}
                      onClick={() => setModes(modes.includes(k) ? modes.filter((m) => m !== k) : [...modes, k])}
                    >
                      {k === 2 ? "1v1" : `${k} 人`}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="seeds">地图种子</Label>
                <Input id="seeds" value={seeds} onChange={(e) => setSeeds(e.target.value)} required placeholder="11,29,47" />
              </div>
            </div>
            <label className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" className="accent-[var(--blue)]" checked={rotate} onChange={(e) => setRotate(e.target.checked)} />
              循环轮换座位（每个组合打 k 场，消除出生位置差异）
            </label>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
              <div>
                <span className="num font-pixel text-[24px] leading-[28px] text-blue">{number(count)}</span> 场比赛
                <div className="text-ink-3">2 / 8 人 32×32 · 200 回合；4 人 48×48 · 300 回合 · 单任务上限 {number(maxGames)} 场</div>
              </div>
              <Button size="lg" disabled={busy || count === 0 || count > maxGames || selected.length > maxBots || modes.some((k) => selected.length < k)}>
                <Play size={14} /> {busy ? "提交中…" : "提交到后端 >"}
              </Button>
            </div>
          </form>
        </Panel>
      )}
      {list.loading ? (
        <Loading />
      ) : list.data?.jobs.length ? (
        <div className="flex flex-col gap-3">
          {list.data.jobs.map((job) => (
            <a key={job.id} href={`/tests/${job.id}`} className="pixel-frame group flex items-center gap-4 p-4 hover:border-ink">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="truncate">{job.name}</span>
                  <Status value={job.status} />
                </div>
                <div className="mb-2 text-ink-3">
                  {job.kind === "ranked" ? "固定基准评测" : job.kind === "ranked-multi" ? "多人基准评测" : "私人循环赛"} · {date(job.created_at)}
                </div>
                <Progress job={job} />
              </div>
              <ArrowRight size={18} className="text-ink-3 group-hover:text-blue" />
            </a>
          ))}
        </div>
      ) : (
        <Empty title="还没有测试任务">创建一个测试，把自己的版本和平台基准对照一下。</Empty>
      )}
    </>
  );
}
