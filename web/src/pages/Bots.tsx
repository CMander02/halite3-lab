import { useState, type FormEvent } from "react";
import { Plus, Upload, Download, Trophy, ChevronDown, Shield, Command, MoreVertical, Flag, Archive, Edit, Script } from "@nsmr/pixelart-react";
import type { Bot, CatalogKind, User, Version } from "@/lib/types";
import { api, date, useApi } from "@/lib/api";
import { navigate } from "@/lib/router";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Empty, ErrorBox, Loading, PageHead, Tag } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";
import { BotIcon } from "@/components/BotIcon";
import { CatalogChip, CatalogSelect, entry, useCatalog } from "@/components/ModelBadge";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

const SETUP_KEY = "halite3-last-setup";
const lastSetup = (): Record<CatalogKind, string> => {
  try {
    return { model: "unknown", effort: "unknown", harness: "unknown", ...JSON.parse(localStorage.getItem(SETUP_KEY) || "{}") };
  } catch {
    return { model: "unknown", effort: "unknown", harness: "unknown" };
  }
};

/** 1.2 -> 1.3, v4 -> v5, otherwise append .1 */
function nextVersion(versions: Version[]) {
  const last = versions[0]?.version;
  if (!last) return "1.0";
  const match = last.match(/^(.*?)(\d+)$/);
  return match ? match[1] + (Number(match[2]) + 1) : `${last}.1`;
}

export default function Bots({ user }: { user: User | null }) {
  const { data, error, loading, refresh } = useApi<{ bots: Bot[] }>("/bots");
  const [create, setCreate] = useState(false);
  const [upload, setUpload] = useState<Bot | null>(null);
  const [rankTarget, setRankTarget] = useState<{ bot: Bot; id: string; version: string } | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [setup, setSetup] = useState(lastSetup);
  const [showArchived, setShowArchived] = useState<Record<string, boolean>>({});
  const [editing, setEditing] = useState<Version | null>(null);
  const catalog = useCatalog();

  async function guard(task: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await task();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const createBot = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void guard(async () => {
      const result = await api<{ id: string }>("/bots", { method: "POST", body: JSON.stringify({ name: form.get("name"), description: form.get("description") }) });
      setCreate(false);
      await refresh();
      setUpload({ id: result.id, name: String(form.get("name")), description: "", builtin: 0, owned: true, author: null, versions: [], created_at: 0 });
    });
  };

  const uploadVersion = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void guard(async () => {
      const file = form.get("file") as File;
      if (file.size > 5 * 1024 * 1024) throw new Error("文件不能超过 5 MiB。");
      const trace = form.get("trace") as File;
      if (trace.size > 16 * 1024 * 1024) throw new Error("对话轨迹不能超过 16 MiB，可以先用 gzip 压缩。");
      form.set("rank", form.get("rank") ? "true" : "false");
      localStorage.setItem(SETUP_KEY, JSON.stringify(setup));
      const result = await api<{ id: string; ranked_job_id?: string; ranked_error?: string }>(`/bots/${upload!.id}/versions`, { method: "POST", body: form });
      setExpanded(upload!.id);
      setUpload(null);
      await refresh();
      if (result.ranked_error) setMessage(`版本已上传，但参评未提交：${result.ranked_error}`);
      else navigate("/me");
    });
  };

  const submitRank = () =>
    void guard(async () => {
      const r = await api<{ id: string }>(`/versions/${rankTarget!.id}/rank`, { method: "POST", body: "{}" });
      setRankTarget(null);
      navigate(`/tests/${r.id}`);
    });

  const patchVersion = (v: Version, body: Record<string, unknown>) =>
    void guard(async () => {
      await api(`/versions/${v.id}`, { method: "PATCH", body: JSON.stringify(body) });
      await refresh();
    });
  const setDefault = (bot: Bot, id: string | null) =>
    void guard(async () => {
      await api(`/bots/${bot.id}`, { method: "PATCH", body: JSON.stringify(id ? { default_version_id: id } : { clear_default: true }) });
      await refresh();
    });
  const saveNotes = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const notes = String(new FormData(event.currentTarget).get("notes") || "");
    void guard(async () => {
      await api(`/versions/${editing!.id}`, { method: "PATCH", body: JSON.stringify({ notes }) });
      setEditing(null);
      await refresh();
    });
  };

  const bots = data?.bots || [];
  return (
    <>
      <PageHead
        eyebrow="我的 Bots"
        title="每次改进，一个不可覆盖的版本"
        description="支持 Python、C++ 单文件或 ZIP 项目；源码始终私有。"
        action={
          user ? (
            <Button onClick={() => setCreate(true)}>
              <Plus size={16} /> 创建 Bot
            </Button>
          ) : (
            <Button asChild>
              <a href="/login">登录后上传 &gt;</a>
            </Button>
          )
        }
      />
      <ErrorBox message={error || message} />
      {!user && (
        <div className="mb-4 flex items-center gap-2 border border-line bg-paper-2 px-3 py-2 text-ink-2">
          <Shield size={16} className="text-blue" /> 登录后可管理自己的源码与版本。下方平台基准可公开下载。
        </div>
      )}
      {loading ? (
        <Loading />
      ) : bots.length ? (
        <div className="grid gap-4 md:grid-cols-2">
          {bots.map((bot) => {
            const open = expanded === bot.id || bot.versions.length <= 1;
            const archived = bot.versions.filter((v) => v.archived).length;
            const visible = bot.versions.filter((v) => !v.archived || showArchived[bot.id]);
            const active = bot.versions.find((v) => !v.archived);
            const defaultId = bot.default_version_id || active?.id;
            return (
              <section key={bot.id} className={cn("pixel-frame flex min-w-0 flex-col", bot.builtin ? "border-dashed" : "")}>
                <header className="flex items-start gap-3 p-4">
                  {bot.builtin ? (
                    <UserAvatar size="lg" />
                  ) : (
                    <BotIcon id={bot.id} model={bot.model} catalog={catalog} />
                  )}
                  <div className="min-w-0 flex-1">
                    <h2 className="m-0 flex flex-wrap items-center gap-2 text-[24px] leading-[28px] font-normal">
                      {bot.name}
                      {bot.builtin === 1 && <Tag>平台基准</Tag>}
                    </h2>
                    <p className="mt-1 mb-0 text-ink-2">{bot.description || "尚未添加简介"}</p>
                  </div>
                  <span className="num shrink-0 text-ink-2">{bot.versions.length} 版本</span>
                </header>
                {open && (
                  <div className="border-t border-line">
                    {bot.versions.length ? (
                      visible.map((v, i) => (
                        <div key={v.id} className={cn("flex flex-col gap-2 border-b border-line-2 px-4 py-3 last:border-0 sm:flex-row sm:items-center", v.archived ? "opacity-60" : "")}>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-blue">v{v.version}</span>
                              <Tag>{v.language === "cpp" ? "C++17" : "Python"}</Tag>
                              {i === 0 && !v.archived && <Tag className="border-blue text-blue">最新</Tag>}
                              {bot.owned && v.id === defaultId && <Tag className="border-ink text-ink">{bot.default_version_id ? "默认" : "默认 · 最新"}</Tag>}
                              {v.archived ? <Tag>已归档</Tag> : null}
                              {!bot.builtin && v.declared_model && (
                                <span className="flex items-center gap-1.5 text-ink-2">
                                  <CatalogChip kind="model" id={v.declared_model} catalog={catalog} />
                                  <span className="text-ink-3">{entry(catalog, "effort", v.declared_effort).name}</span>
                                </span>
                              )}
                            </div>
                            <div className="truncate text-ink-2">{v.notes || "未填写版本说明"}</div>
                            <div className="text-ink-3">
                              {v.sha256.slice(0, 12)} · {(v.size / 1024).toFixed(1)} KiB · {date(v.created_at)}
                            </div>
                          </div>
                          <div className="flex shrink-0 gap-2">
                            <Button variant="outline" size="sm" asChild>
                              <a href={`/api/versions/${v.id}/source`}>
                                <Download size={14} /> 源码
                              </a>
                            </Button>
                            {bot.owned && (
                              <Button variant="secondary" size="sm" disabled={busy} onClick={() => setRankTarget({ bot, id: v.id, version: v.version })}>
                                <Trophy size={14} /> 参评
                              </Button>
                            )}
                            {bot.owned && (
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button variant="ghost" size="icon-sm" aria-label="版本操作">
                                    <MoreVertical size={16} />
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="min-w-44">
                                  {!v.archived && v.id !== bot.default_version_id && (
                                    <DropdownMenuItem onSelect={() => setDefault(bot, v.id)}>
                                      <Flag size={14} /> 设为默认版本
                                    </DropdownMenuItem>
                                  )}
                                  {v.id === bot.default_version_id && (
                                    <DropdownMenuItem onSelect={() => setDefault(bot, null)}>
                                      <Flag size={14} /> 改回“始终用最新”
                                    </DropdownMenuItem>
                                  )}
                                  <DropdownMenuItem onSelect={() => setEditing(v)}>
                                    <Edit size={14} /> 编辑版本说明
                                  </DropdownMenuItem>
                                  {v.has_trace ? (
                                    <DropdownMenuItem asChild>
                                      <a href={`/api/versions/${v.id}/trace`}>
                                        <Script size={14} /> 下载对话轨迹
                                      </a>
                                    </DropdownMenuItem>
                                  ) : null}
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem onSelect={() => patchVersion(v, { archived: !v.archived })}>
                                    <Archive size={14} /> {v.archived ? "取消归档" : "归档（不再作为默认）"}
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            )}
                          </div>
                        </div>
                      ))
                    ) : (
                      <Empty title="还没有版本">上传第一个版本，开始测试。</Empty>
                    )}
                  </div>
                )}
                <footer className="mt-auto flex items-center justify-between gap-2 border-t border-line px-4 py-2">
                  <span className="flex items-center gap-4">
                    {bot.versions.length > 1 ? (
                      <button className="flex cursor-pointer items-center gap-1 text-ink-2 hover:text-blue" onClick={() => setExpanded(expanded === bot.id ? null : bot.id)}>
                        <ChevronDown size={14} className={cn("transition-transform", expanded === bot.id && "rotate-180")} />
                        {expanded === bot.id ? "收起版本" : "展开版本"}
                      </button>
                    ) : null}
                    {open && archived > 0 && (
                      <button className="cursor-pointer text-ink-3 hover:text-blue" onClick={() => setShowArchived({ ...showArchived, [bot.id]: !showArchived[bot.id] })}>
                        {showArchived[bot.id] ? "隐藏" : "显示"} {archived} 个已归档
                      </button>
                    )}
                  </span>
                  {bot.owned && (
                    <Button size="sm" onClick={() => setUpload(bot)}>
                      <Upload size={14} /> 上传版本
                    </Button>
                  )}
                </footer>
              </section>
            );
          })}
        </div>
      ) : (
        <Empty title="还没有 Bot" />
      )}

      <section className="mt-8 flex items-start gap-4 border border-ink p-4">
        <Command size={24} className="shrink-0 text-blue" />
        <div>
          <div>也可以直接调用后端上传</div>
          <p className="mt-1 mb-2 text-ink-2">在“账号与头像”创建 API Token，用 CLI 上传版本、提交测试；网页只负责展示后端保存的版本和结果。</p>
          <div className="flex flex-wrap gap-4">
            <a className="text-blue" href="/settings">
              管理 Token &gt;
            </a>
            <a className="text-blue" href="/api/docs">
              接口文档 &gt;
            </a>
            <a className="text-blue" href="/sample-python.zip">
              Python 示例
            </a>
            <a className="text-blue" href="/sample-cpp.zip">
              C++ 示例
            </a>
          </div>
        </div>
      </section>

      <Dialog open={create} onOpenChange={setCreate}>
        <DialogContent className="border border-ink bg-paper">
          <DialogHeader>
            <DialogTitle className="font-normal">创建 Bot</DialogTitle>
            <DialogDescription className="text-ink-2">创建后立即上传第一个版本。</DialogDescription>
          </DialogHeader>
          <form onSubmit={createBot} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="bot-name">名称</Label>
              <Input id="bot-name" name="name" maxLength={60} required placeholder="tide-hunter" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="bot-desc">简介</Label>
              <Input id="bot-desc" name="description" maxLength={500} placeholder="一句话介绍策略（可选）" />
            </div>
            <ErrorBox message={message} />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreate(false)}>
                取消
              </Button>
              <Button disabled={busy}>创建并上传 &gt;</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(upload)} onOpenChange={(o) => !o && setUpload(null)}>
        <DialogContent className="border border-ink bg-paper">
          <DialogHeader>
            <DialogTitle className="font-normal">上传新版本 · {upload?.name}</DialogTitle>
            <DialogDescription className="text-ink-2">Bot 源码（Python / C++ 单文件或 ZIP，5 MiB 以内）和写出它的对话轨迹一起上传。</DialogDescription>
          </DialogHeader>
          <form onSubmit={uploadVersion} className="flex max-h-[70svh] flex-col gap-4 overflow-y-auto">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ver">版本标识</Label>
                <Input id="ver" name="version" key={upload?.id} defaultValue={upload ? nextVersion(upload.versions) : ""} placeholder="1.0.0" pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{0,31}" required maxLength={32} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="file">Bot 文件（bot.cpp 等）</Label>
                <Input id="file" name="file" type="file" accept=".py,.cpp,.cc,.cxx,.zip" required className="pt-1.5" />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="trace">对话轨迹</Label>
              <Input id="trace" name="trace" type="file" accept=".jsonl,.json,.md,.txt,.gz,.zip" required className="pt-1.5" />
              <span className="text-ink-3">
                Claude Code：<code>~/.claude/projects/&lt;项目&gt;/&lt;会话&gt;.jsonl</code>；Codex：<code>~/.codex/sessions/…/rollout-*.jsonl</code>；其他工具导出 JSON / Markdown 也可以。16 MiB 以内，支持 .gz。仅自己和管理员可见。
              </span>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {(
                [
                  ["model", "模型"],
                  ["effort", "推理强度 Effort"],
                  ["harness", "平台 / Harness"],
                ] as [CatalogKind, string][]
              ).map(([kind, label]) => (
                <div key={kind} className="flex min-w-0 flex-col gap-1.5">
                  <Label htmlFor={`setup-${kind}`}>{label}</Label>
                  <CatalogSelect id={`setup-${kind}`} kind={kind} name={kind} catalog={catalog} value={setup[kind]} onChange={(v) => setSetup({ ...setup, [kind]: v })} />
                </div>
              ))}
            </div>
            <p className="m-0 text-ink-3">
              括号里是 ELO 修正：模型越强、推理越深，最终 ELO 扣得越多。后台会分析轨迹；声明与检测不一致时，按修正更大的一方计算，管理员可以人工确认。
              当前选择合计 <span className="text-ink">−{(entry(catalog, "model", setup.model).elo_offset + entry(catalog, "effort", setup.effort).elo_offset + entry(catalog, "harness", setup.harness).elo_offset).toFixed(0)}</span>。
            </p>
            <label className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" name="rank" defaultChecked className="size-4 accent-[var(--blue)]" /> 上传后立即参加公开评测（对阵全部平台基准，12 场）
            </label>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="notes">版本说明</Label>
              <textarea id="notes" name="notes" rows={3} maxLength={2000} placeholder="这次改了什么？（可选）" className="border border-line bg-paper-2 p-2 outline-none focus:border-ink" />
            </div>
            <ErrorBox message={message} />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setUpload(null)}>
                取消
              </Button>
              <Button disabled={busy}>
                <Upload size={14} /> {busy ? "上传中…" : "上传到后端"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(editing)} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="border border-ink bg-paper">
          <DialogHeader>
            <DialogTitle className="font-normal">编辑版本说明 · v{editing?.version}</DialogTitle>
            <DialogDescription className="text-ink-2">源码与轨迹不可修改；说明可以随时更新。</DialogDescription>
          </DialogHeader>
          <form onSubmit={saveNotes} className="flex flex-col gap-4">
            <textarea name="notes" rows={4} maxLength={2000} defaultValue={editing?.notes} className="border border-line bg-paper-2 p-2 outline-none focus:border-ink" />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditing(null)}>
                取消
              </Button>
              <Button disabled={busy}>保存</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(rankTarget)} onOpenChange={(o) => !o && setRankTarget(null)}>
        <DialogContent className="border border-ink bg-paper">
          <DialogHeader>
            <DialogTitle className="font-normal">
              提交 {rankTarget?.bot.name} v{rankTarget?.version} 参评？
            </DialogTitle>
            <DialogDescription className="text-ink-2">将进行 12 场固定基准评测。Bot 名称、版本、成绩与评测回放会公开，源码仍然私有。</DialogDescription>
          </DialogHeader>
          <ErrorBox message={message} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRankTarget(null)}>
              再想想
            </Button>
            <Button disabled={busy} onClick={submitRank}>
              <Trophy size={14} /> 确认参评
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
