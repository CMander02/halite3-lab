import { useState, type FormEvent } from "react";
import { Plus, Upload, Download, Trophy, ChevronDown, Code, Shield, Command } from "@nsmr/pixelart-react";
import type { Bot, User } from "@/lib/types";
import { api, date, useApi } from "@/lib/api";
import { navigate } from "@/lib/router";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Empty, ErrorBox, Loading, PageHead, Tag } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";

export default function Bots({ user }: { user: User | null }) {
  const { data, error, loading, refresh } = useApi<{ bots: Bot[] }>("/bots");
  const [create, setCreate] = useState(false);
  const [upload, setUpload] = useState<Bot | null>(null);
  const [rankTarget, setRankTarget] = useState<{ bot: Bot; id: string; version: string } | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

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
      await api(`/bots/${upload!.id}/versions`, { method: "POST", body: form });
      setExpanded(upload!.id);
      setUpload(null);
      await refresh();
    });
  };

  const submitRank = () =>
    void guard(async () => {
      const r = await api<{ id: string }>(`/versions/${rankTarget!.id}/rank`, { method: "POST", body: "{}" });
      setRankTarget(null);
      navigate(`/tests/${r.id}`);
    });

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
            return (
              <section key={bot.id} className={cn("pixel-frame flex flex-col", bot.builtin ? "border-dashed" : "")}>
                <header className="flex items-start gap-3 p-4">
                  {bot.builtin ? (
                    <UserAvatar size="lg" />
                  ) : (
                    <span className="notch flex size-10 shrink-0 items-center justify-center bg-blue text-white">
                      <Code size={20} />
                    </span>
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
                      bot.versions.map((v, i) => (
                        <div key={v.id} className="flex flex-col gap-2 border-b border-line-2 px-4 py-3 last:border-0 sm:flex-row sm:items-center">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-blue">v{v.version}</span>
                              <Tag>{v.language === "cpp" ? "C++17" : "Python"}</Tag>
                              {i === 0 && <Tag className="border-blue text-blue">最新</Tag>}
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
                          </div>
                        </div>
                      ))
                    ) : (
                      <Empty title="还没有版本">上传第一个版本，开始测试。</Empty>
                    )}
                  </div>
                )}
                <footer className="mt-auto flex items-center justify-between gap-2 border-t border-line px-4 py-2">
                  {bot.versions.length > 1 ? (
                    <button className="flex cursor-pointer items-center gap-1 text-ink-2 hover:text-blue" onClick={() => setExpanded(expanded === bot.id ? null : bot.id)}>
                      <ChevronDown size={14} className={cn("transition-transform", expanded === bot.id && "rotate-180")} />
                      {expanded === bot.id ? "收起版本" : "展开版本"}
                    </button>
                  ) : (
                    <span />
                  )}
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
            <DialogDescription className="text-ink-2">Python / C++ 单文件，或含 bot.py / C++ 源码的 ZIP，5 MiB 以内。</DialogDescription>
          </DialogHeader>
          <form onSubmit={uploadVersion} className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ver">版本标识</Label>
                <Input id="ver" name="version" placeholder="1.0.0" pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{0,31}" required maxLength={32} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="file">Bot 文件</Label>
                <Input id="file" name="file" type="file" accept=".py,.cpp,.cc,.cxx,.zip" required className="pt-1.5" />
              </div>
            </div>
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
