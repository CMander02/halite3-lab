import { useMemo, useState, type FormEvent } from "react";
import { Users, Scale, Checklist, Dashboard, Reload, Lock, LockOpen, Logout, Script, Plus } from "@nsmr/pixelart-react";
import type { AdminUser, CatalogEntry, CatalogKind, Submission, User } from "@/lib/types";
import { api, ago, date, number, useApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Empty, ErrorBox, Loading, PageHead, Panel, Stat, Tag } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";
import { CONFIDENCE, Icon, REGION, SetupLine, correctionLabel, loadCatalog } from "@/components/ModelBadge";

type AdminCatalog = Record<CatalogKind, CatalogEntry[]>;
type Overview = {
  matches: Record<string, number>;
  users: number;
  disabled: number;
  runner_online: boolean;
  disk_free: number;
  disk_total: number;
  traces: number;
  trace_bytes: number;
  mismatched: number;
};
const KIND_LABEL: Record<CatalogKind, string> = { model: "模型", effort: "推理强度", harness: "平台 / Harness" };
const gib = (b: number) => `${(b / 1024 ** 3).toFixed(1)} GiB`;

function useAction(after: () => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function run<T>(task: () => Promise<T>) {
    setBusy(true);
    setMessage("");
    try {
      const value = await task();
      await after();
      return value;
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return { busy, message, run };
}

function UsersTab() {
  const { data, loading, error, refresh } = useApi<{ users: AdminUser[] }>("/admin/users");
  const { busy, message, run } = useAction(refresh);
  const [password, setPassword] = useState<{ user: AdminUser; value: string } | null>(null);
  const call = (path: string, method: string, body: object = {}) => run(() => api<Record<string, string>>(path, { method, body: JSON.stringify(body) }));
  if (loading) return <Loading />;
  return (
    <>
      <ErrorBox message={error || message} />
      <div className="pixel-frame overflow-x-auto">
        <table className="ptable">
          <thead>
            <tr>
              <th>用户</th>
              <th>注册</th>
              <th>最近登录</th>
              <th className="right">Bot / 版本</th>
              <th className="right">对局</th>
              <th className="right">会话 / Token</th>
              <th>状态</th>
              <th className="right">操作</th>
            </tr>
          </thead>
          <tbody>
            {(data?.users || []).map((u) => (
              <tr key={u.id} className={u.disabled_at ? "opacity-60" : ""}>
                <td>
                  <span className="flex items-center gap-2">
                    <UserAvatar id={u.id} name={u.display_name} version={u.avatar_version} size="sm" />
                    <span>
                      {u.display_name}
                      <span className="block text-ink-3">@{u.username}</span>
                    </span>
                  </span>
                </td>
                <td className="text-ink-2">{date(u.created_at)}</td>
                <td className="text-ink-2">{u.last_login ? ago(u.last_login) : "—"}</td>
                <td className="right num">
                  {u.bots} / {u.versions}
                </td>
                <td className="right num">{number(u.matches)}</td>
                <td className="right num text-ink-2">
                  {u.sessions} / {u.tokens}
                </td>
                <td>{u.is_admin ? <Tag className="border-blue text-blue">唯一管理员</Tag> : u.disabled_at ? <Tag className="border-bad text-bad">已停用</Tag> : <Tag>正常</Tag>}</td>
                <td className="right">
                  {!u.is_admin && (
                    <span className="inline-flex gap-1">
                      <Button variant="outline" size="xs" disabled={busy} onClick={() => void call(`/admin/users/${u.id}`, "PATCH", { disabled: !u.disabled_at })}>
                        {u.disabled_at ? <LockOpen /> : <Lock />} {u.disabled_at ? "启用" : "停用"}
                      </Button>
                      <Button
                        variant="outline"
                        size="xs"
                        disabled={busy}
                        onClick={() =>
                          void call(`/admin/users/${u.id}/password`, "POST").then((r) => {
                            if (r?.password) setPassword({ user: u, value: r.password });
                          })
                        }
                      >
                        重置密码
                      </Button>
                      <Button variant="ghost" size="xs" disabled={busy} onClick={() => void call(`/admin/users/${u.id}/revoke`, "POST")}>
                        <Logout /> 下线
                      </Button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 mb-0 text-ink-3">停用会立即撤销该账号的全部会话与 API Token，并取消排队中的私人对局；公开评测照常完成。重置密码同样会让该账号下线。</p>
      <Dialog open={Boolean(password)} onOpenChange={(o) => !o && setPassword(null)}>
        <DialogContent className="border border-ink bg-paper">
          <DialogHeader>
            <DialogTitle className="font-normal">@{password?.user.username} 的临时密码</DialogTitle>
            <DialogDescription className="text-ink-2">只显示这一次。请通过私下渠道发给用户，登录后可在账号页修改。</DialogDescription>
          </DialogHeader>
          <code className="block border border-line bg-paper-2 p-3 text-[16px] select-all">{password?.value}</code>
          <DialogFooter>
            <Button onClick={() => setPassword(null)}>好的</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function SubmissionsTab({ catalog }: { catalog: AdminCatalog | null }) {
  const { data, loading, error, refresh } = useApi<{ submissions: Submission[] }>("/admin/submissions");
  const { busy, message, run } = useAction(refresh);
  const [onlyMismatch, setOnlyMismatch] = useState(false);
  const [target, setTarget] = useState<Submission | null>(null);
  const items = (data?.submissions || []).filter((s) => !onlyMismatch || s.attribution.mismatch.length);

  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void run(async () => {
      await api(`/admin/versions/${target!.id}/attribution`, {
        method: "PUT",
        body: JSON.stringify({ model: form.get("model") || null, effort: form.get("effort") || null, harness: form.get("harness") || null, note: form.get("note") || "" }),
      });
      setTarget(null);
    });
  };

  if (loading) return <Loading />;
  return (
    <>
      <ErrorBox message={error || message} />
      <div className="mb-3 flex items-center gap-3">
        <label className="flex cursor-pointer items-center gap-2">
          <input type="checkbox" checked={onlyMismatch} onChange={(e) => setOnlyMismatch(e.target.checked)} className="size-4 accent-[var(--blue)]" /> 只看声明与检测不一致
        </label>
        <span className="text-ink-3">{items.length} 个版本</span>
      </div>
      {items.length ? (
        <div className="pixel-frame overflow-x-auto">
          <table className="ptable">
            <thead>
              <tr>
                <th>作者 / 版本</th>
                <th>计分采用</th>
                <th>检测</th>
                <th>轨迹</th>
                <th className="right">修正</th>
                <th className="right">修正后 ELO</th>
                <th className="right">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => {
                const d = s.detection;
                return (
                  <tr key={s.id}>
                    <td>
                      <span className="flex items-center gap-2">
                        <UserAvatar id={s.author_id} name={s.author} size="sm" />
                        <span>
                          {s.bot_name} <span className="text-blue">v{s.version}</span>
                          {!s.eligible && <span className="block text-warn">历史版本 · 不可参赛</span>}
                          <span className="block text-ink-3">
                            {s.author} · {date(s.created_at)}
                          </span>
                        </span>
                      </span>
                    </td>
                    <td className="max-w-[280px]">
                      <SetupLine attribution={s.attribution} catalog={catalog} />
                      {s.admin_note && <span className="block text-[13px] text-ink-3">备注：{s.admin_note}</span>}
                    </td>
                    <td className="text-ink-2">
                      {d ? (
                        <>
                          {d.model} · {d.effort} · {d.harness}
                          <span className="block text-[13px] text-ink-3">
                            置信 {CONFIDENCE[d.model_confidence]}/{CONFIDENCE[d.effort_confidence]}/{CONFIDENCE[d.harness_confidence]}
                            {s.attribution.mismatch.length ? <span className="text-warn"> · 不一致：{s.attribution.mismatch.join("、")}</span> : null}
                          </span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="text-ink-2">
                      {s.trace ? (
                        <>
                          {(s.trace.size / 1024 / 1024).toFixed(2)} MiB
                          {d?.duration_seconds != null && <span className="block text-[13px] text-ink-3">{Math.round(d.duration_seconds / 60)} 分钟 · {number(d.messages)} 条</span>}
                        </>
                      ) : (
                        <span className="text-warn">无</span>
                      )}
                    </td>
                    <td className="right num">{correctionLabel(s.attribution.correction)}</td>
                    <td className="right num">{s.elo ? Math.round(s.elo.adjusted_elo) : "—"}</td>
                    <td className="right">
                      <span className="inline-flex gap-1">
                        <Button variant="outline" size="xs" disabled={busy} onClick={() => setTarget(s)}>
                          人工确认
                        </Button>
                        {s.trace && (
                          <>
                            <Button variant="ghost" size="xs" disabled={busy} onClick={() => void run(() => api(`/admin/versions/${s.id}/redetect`, { method: "POST", body: "{}" }))} title="按当前识别规则重新检测">
                              <Reload />
                            </Button>
                            <Button variant="ghost" size="xs" asChild>
                              <a href={`/api/versions/${s.id}/trace`} title="下载轨迹">
                                <Script />
                              </a>
                            </Button>
                          </>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title="没有需要审核的提交" />
      )}
      <Dialog open={Boolean(target)} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent className="border border-ink bg-paper">
          <DialogHeader>
            <DialogTitle className="font-normal">
              人工确认 · {target?.bot_name} v{target?.version}
            </DialogTitle>
            <DialogDescription className="text-ink-2">选择的值覆盖声明和检测；留空表示不覆盖（按“声明与检测取修正更大者”的规则）。</DialogDescription>
          </DialogHeader>
          {target && (
            <form onSubmit={save} className="flex flex-col gap-4">
              {(["model", "effort", "harness"] as CatalogKind[]).map((kind) => (
                <div key={kind} className="flex flex-col gap-1.5">
                  <Label htmlFor={`ov-${kind}`}>
                    {KIND_LABEL[kind]} <span className="text-ink-3">（声明 {target.attribution[kind].declared} / 检测 {target.attribution[kind].detected}）</span>
                  </Label>
                  <select id={`ov-${kind}`} name={kind} defaultValue={target.attribution[kind].source === "admin" ? target.attribution[kind].value : ""} className="h-9 border border-line bg-paper-2 px-2">
                    <option value="">不覆盖</option>
                    {(catalog?.[kind] || []).map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.name}（{correctionLabel(e.elo_offset)}）
                      </option>
                    ))}
                  </select>
                </div>
              ))}
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ov-note">备注</Label>
                <Input id="ov-note" name="note" maxLength={500} defaultValue={target.admin_note} placeholder="例如：轨迹显示后半程切换了模型" />
              </div>
              <ErrorBox message={message} />
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setTarget(null)}>
                  取消
                </Button>
                <Button disabled={busy}>保存</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function EntryRow({ kind, item, onSave, busy }: { kind: CatalogKind; item: CatalogEntry; onSave: (e: CatalogEntry) => void; busy: boolean }) {
  const [draft, setDraft] = useState(item);
  const [patterns, setPatterns] = useState((item.patterns || []).join("\n"));
  const dirty = JSON.stringify(draft) !== JSON.stringify(item) || patterns !== (item.patterns || []).join("\n");
  const set = (patch: Partial<CatalogEntry>) => setDraft({ ...draft, ...patch });
  return (
    <tr className={cn(!draft.enabled && "opacity-50")}>
      <td className="text-ink-3">
        <code>{item.id}</code>
      </td>
      <td>
        <span className="flex items-center gap-2">
          {kind !== "effort" && <Icon name={draft.icon} />}
          <Input value={draft.name} onChange={(e) => set({ name: e.target.value })} className="h-8 min-w-36" />
        </span>
      </td>
      {kind !== "effort" && (
        <>
          <td>
            <Input value={draft.vendor} onChange={(e) => set({ vendor: e.target.value })} className="h-8 min-w-28" />
          </td>
          <td>
            <select value={draft.region} onChange={(e) => set({ region: e.target.value as CatalogEntry["region"] })} className="h-8 border border-line bg-paper-2 px-1">
              {["us", "cn", "other", ""].map((r) => (
                <option key={r} value={r}>
                  {REGION[r]}
                </option>
              ))}
            </select>
          </td>
          <td>
            <Input value={draft.icon} onChange={(e) => set({ icon: e.target.value })} className="h-8 w-36" placeholder="lobehub 图标名" />
          </td>
        </>
      )}
      <td>
        <textarea value={patterns} onChange={(e) => setPatterns(e.target.value)} rows={1} className="h-8 w-44 resize-y border border-line bg-paper-2 px-1 py-1 font-mono text-[12px] outline-none focus:border-ink" placeholder="每行一个正则" />
      </td>
      <td className="right">
        <Input type="number" step={5} value={draft.elo_offset} onChange={(e) => set({ elo_offset: Number(e.target.value) })} className="h-8 w-20 text-right" />
      </td>
      <td>
        <input type="checkbox" checked={draft.enabled} onChange={(e) => set({ enabled: e.target.checked })} className="size-4 accent-[var(--blue)]" disabled={item.id === "unknown"} />
      </td>
      <td className="right">
        <Button size="xs" disabled={!dirty || busy} onClick={() => onSave({ ...draft, patterns: patterns.split("\n").map((p) => p.trim()).filter(Boolean) })}>
          保存
        </Button>
      </td>
    </tr>
  );
}

function CatalogTab({ catalog, refresh }: { catalog: AdminCatalog | null; refresh: () => Promise<void> }) {
  const { busy, message, run } = useAction(async () => {
    await refresh();
    await loadCatalog(true);
  });
  const [adding, setAdding] = useState<CatalogKind | null>(null);
  const save = (kind: CatalogKind, e: CatalogEntry) =>
    void run(() =>
      api(`/admin/catalog/${kind}/${encodeURIComponent(e.id)}`, {
        method: "PUT",
        body: JSON.stringify({ name: e.name, vendor: e.vendor, region: e.region, icon: e.icon, elo_offset: e.elo_offset, patterns: e.patterns || [], enabled: e.enabled, sort: e.sort }),
      }),
    );
  const add = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    const kind = adding!;
    const id = String(f.get("id")).trim().toLowerCase();
    void run(async () => {
      await api(`/admin/catalog/${kind}/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify({ name: f.get("name"), vendor: f.get("vendor") || "", region: f.get("region") || "", icon: f.get("icon") || "", elo_offset: Number(f.get("offset") || 0), patterns: String(f.get("patterns") || "").split("\n").map((p) => p.trim()).filter(Boolean), enabled: true, sort: (catalog?.[kind].length || 0) + 1 }),
      });
      setAdding(null);
    });
  };
  if (!catalog) return <Loading />;
  return (
    <div className="flex flex-col gap-6">
      <ErrorBox message={message} />
      <p className="m-0 max-w-[880px] text-ink-2">
        修正后 ELO = 原始 ELO − 模型 − 推理强度 − 平台。数值越大扣分越多；负数表示加分。“识别规则”是轨迹检测用的正则（不区分大小写），改完后可在“提交审核”里重新检测。图标名取自
        <a className="text-blue" href="https://lobehub.com/icons/" target="_blank" rel="noreferrer">
          {" "}
          LobeHub Icons ↗
        </a>
        ，需要先把 SVG 放进 <code>web/public/model-icons/</code>。
      </p>
      {(["model", "effort", "harness"] as CatalogKind[]).map((kind) => (
        <Panel
          key={kind}
          title={`${KIND_LABEL[kind]} · ${catalog[kind].length} 项`}
          action={
            <Button size="xs" variant="outline" onClick={() => setAdding(kind)}>
              <Plus /> 新增
            </Button>
          }
          bodyClassName="p-0 overflow-x-auto"
        >
          <table className="ptable">
            <thead>
              <tr>
                <th>ID</th>
                <th>名称</th>
                {kind !== "effort" && (
                  <>
                    <th>厂商</th>
                    <th>地区</th>
                    <th>图标</th>
                  </>
                )}
                <th>识别规则</th>
                <th className="right">ELO 修正</th>
                <th>启用</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {catalog[kind].map((item) => (
                <EntryRow key={`${item.id}-${item.elo_offset}-${item.name}-${item.enabled}`} kind={kind} item={item} busy={busy} onSave={(e) => save(kind, e)} />
              ))}
            </tbody>
          </table>
        </Panel>
      ))}
      <Dialog open={Boolean(adding)} onOpenChange={(o) => !o && setAdding(null)}>
        <DialogContent className="border border-ink bg-paper">
          <DialogHeader>
            <DialogTitle className="font-normal">新增{adding ? KIND_LABEL[adding] : ""}</DialogTitle>
            <DialogDescription className="text-ink-2">ID 创建后不能修改，用小写字母、数字、点和短横线。</DialogDescription>
          </DialogHeader>
          <form onSubmit={add} className="grid gap-3 sm:grid-cols-2">
            <Input name="id" required placeholder="ID，如 kimi-k3.1" pattern="[a-z0-9.\-]{1,40}" />
            <Input name="name" required placeholder="显示名称" />
            {adding !== "effort" && (
              <>
                <Input name="vendor" placeholder="厂商" />
                <select name="region" className="h-9 border border-line bg-paper-2 px-2">
                  <option value="us">美国</option>
                  <option value="cn">中国</option>
                  <option value="other">其他</option>
                </select>
                <Input name="icon" placeholder="图标名，如 kimi-color" />
              </>
            )}
            <Input name="offset" type="number" step={5} required placeholder="ELO 修正" />
            <textarea name="patterns" rows={2} placeholder="识别规则，每行一个正则" className="border border-line bg-paper-2 p-2 font-mono text-[12px] sm:col-span-2" />
            <DialogFooter className="sm:col-span-2">
              <Button type="button" variant="outline" onClick={() => setAdding(null)}>
                取消
              </Button>
              <Button disabled={busy}>添加</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Admin({ user }: { user: User | null }) {
  const overview = useApi<Overview>(user?.is_admin ? "/admin/overview" : null, 20000);
  const catalogApi = useApi<AdminCatalog>(user?.is_admin ? "/admin/catalog" : null);
  const o = overview.data;
  const queue = useMemo(() => (o ? (o.matches.queued || 0) + (o.matches.running || 0) : 0), [o]);
  if (!user?.is_admin) return <Empty title="仅管理员可以访问" />;
  return (
    <>
      <PageHead eyebrow="管理后台" title="全站管理" description={`唯一管理员 @${user.username}：用户、提交审核与 ELO 修正。`} />
      <ErrorBox message={overview.error || catalogApi.error} />
      <Tabs defaultValue="overview" className="gap-6">
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <TabsList className="h-10">
            <TabsTrigger value="overview" className="px-4">
              <Dashboard size={14} /> 概览
            </TabsTrigger>
            <TabsTrigger value="users" className="px-4">
              <Users size={14} /> 用户
            </TabsTrigger>
            <TabsTrigger value="submissions" className="px-4">
              <Checklist size={14} /> 提交审核
              {o?.mismatched ? <span className="bg-warn px-1 text-white">{o.mismatched}</span> : null}
            </TabsTrigger>
            <TabsTrigger value="catalog" className="px-4">
              <Scale size={14} /> ELO 修正
            </TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="overview">
          {o ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="用户" value={number(o.users)} hint={`${o.disabled} 个已停用`} />
              <Stat label="已完成对局" value={number(o.matches.complete || 0)} hint={`${queue} 场排队/运行 · ${o.matches.failed || 0} 场失败`} />
              <Stat label="对话轨迹" value={number(o.traces)} hint={`${(o.trace_bytes / 1024 / 1024).toFixed(1)} MiB（解压后）`} />
              <Stat label="待审核" value={number(o.mismatched)} hint="声明与检测不一致" />
              <Stat label="执行器" value={o.runner_online ? "在线" : "离线"} />
              <Stat label="磁盘可用" value={gib(o.disk_free)} hint={`共 ${gib(o.disk_total)}`} />
            </div>
          ) : (
            <Loading />
          )}
        </TabsContent>
        <TabsContent value="users">
          <UsersTab />
        </TabsContent>
        <TabsContent value="submissions">
          <SubmissionsTab catalog={catalogApi.data} />
        </TabsContent>
        <TabsContent value="catalog">
          <CatalogTab catalog={catalogApi.data} refresh={catalogApi.refresh} />
        </TabsContent>
      </Tabs>
    </>
  );
}
