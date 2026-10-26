import { useEffect, useRef, useState, type FormEvent, type PointerEvent } from "react";
import { Upload, Reload, Copy, Check, Trash, Plus, Logout, Edit, Image as ImageIcon } from "@nsmr/pixelart-react";
import type { Profile, User } from "@/lib/types";
import { api, date, number, useApi } from "@/lib/api";
import { navigate, useLocation } from "@/lib/router";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Empty, ErrorBox, PageHead, Panel, Stat } from "@/components/pixel";
import { avatarUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

const OUT = 128;

function PasswordPanel() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [done, setDone] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setMessage("");
    setDone(false);
    if (data.get("new_password") !== data.get("confirm")) return setMessage("两次输入的新密码不一致。");
    setBusy(true);
    try {
      await api("/me/password", { method: "POST", body: JSON.stringify({ current_password: data.get("current_password"), new_password: data.get("new_password") }) });
      form.reset();
      setDone(true);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="修改密码">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pw-current">当前密码</Label>
          <Input id="pw-current" name="current_password" type="password" autoComplete="current-password" required />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pw-new">新密码（至少 12 位）</Label>
          <Input id="pw-new" name="new_password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pw-confirm">再输入一次</Label>
          <Input id="pw-confirm" name="confirm" type="password" autoComplete="new-password" minLength={12} maxLength={128} required />
        </div>
        <div className="flex items-center gap-3 sm:col-span-3">
          <Button disabled={busy}>{busy ? "保存中…" : "修改密码"}</Button>
          {done && <span className="text-good">已修改。其他设备上的登录已退出，API Token 不受影响。</span>}
          {message && <span className="text-bad">{message}</span>}
        </div>
      </form>
    </Panel>
  );
}

function Cropper({ file, onCancel, onSave }: { file: File; onCancel: () => void; onSave: (blob: Blob) => Promise<void> }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [pixelate, setPixelate] = useState(false);
  const [busy, setBusy] = useState(false);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  useEffect(() => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => setImage(img);
      img.src = String(reader.result);
    };
    reader.readAsDataURL(file);
  }, [file]);

  // offset is measured in 256px preview pixels
  const render = (target: HTMLCanvasElement, size: number) => {
    if (!image) return;
    const ctx = target.getContext("2d")!;
    const base = Math.min(image.width, image.height) / zoom;
    const sx = (image.width - base) / 2 - offset.x * (base / 256),
      sy = (image.height - base) / 2 - offset.y * (base / 256);
    if (pixelate) {
      const small = document.createElement("canvas");
      small.width = small.height = 24;
      small.getContext("2d")!.drawImage(image, sx, sy, base, base, 0, 0, 24, 24);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(small, 0, 0, size, size);
    } else {
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(image, sx, sy, base, base, 0, 0, size, size);
    }
  };

  useEffect(() => {
    if (canvas.current) {
      canvas.current.width = canvas.current.height = 256;
      canvas.current.getContext("2d")!.clearRect(0, 0, 256, 256);
      render(canvas.current, 256);
    }
  });

  const move = (e: PointerEvent) => {
    if (!drag.current) return;
    setOffset({ x: drag.current.ox + (e.clientX - drag.current.x), y: drag.current.oy + (e.clientY - drag.current.y) });
  };

  async function save() {
    const out = document.createElement("canvas");
    out.width = out.height = OUT;
    render(out, OUT);
    setBusy(true);
    try {
      const blob = await new Promise<Blob | null>((resolve) => out.toBlob(resolve, "image/png"));
      if (blob) await onSave(blob);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="border border-ink bg-paper sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle className="font-normal">调整头像</DialogTitle>
          <DialogDescription className="text-ink-2">拖动画面选择区域，滑块缩放。保存为 128×128 PNG。</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col items-center gap-4">
          <div className="relative size-64 overflow-hidden border border-ink bg-[repeating-conic-gradient(var(--blue-50)_0_25%,transparent_0_50%)] bg-[length:16px_16px]">
            <canvas
              ref={canvas}
              className="size-64 cursor-grab touch-none active:cursor-grabbing"
              onPointerDown={(e) => {
                e.currentTarget.setPointerCapture(e.pointerId);
                drag.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
              }}
              onPointerMove={move}
              onPointerUp={() => (drag.current = null)}
            />
            <div className="pointer-events-none absolute inset-0 rounded-full shadow-[0_0_0_999px_rgba(245,242,233,.55)]" />
          </div>
          <label className="flex w-full items-center gap-3">
            缩放
            <input type="range" min={1} max={4} step={0.05} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} className="flex-1 accent-[var(--blue)]" />
          </label>
          <label className="flex w-full cursor-pointer items-center gap-2">
            <input type="checkbox" checked={pixelate} onChange={(e) => setPixelate(e.target.checked)} className="accent-[var(--blue)]" />
            像素化（24×24 采样，和全站风格一致）
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            取消
          </Button>
          <Button disabled={!image || busy} onClick={() => void save()}>
            <Upload size={14} /> {busy ? "上传中…" : "保存头像"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Account({ user, onChange }: { user: User | null; onChange: () => Promise<void> }) {
  const { search } = useLocation();
  const profile = useApi<Profile>(user ? "/me" : null);
  const tokens = useApi<{ tokens: { id: string; name: string; created_at: number; expires_at: number }[] }>(user ? "/tokens" : null);
  const [file, setFile] = useState<File | null>(null);
  const [editing, setEditing] = useState(false);
  const [token, setToken] = useState("");
  const [copied, setCopied] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const p = profile.data;

  if (!user)
    return (
      <>
        <PageHead eyebrow="账号" title="请先登录" />
        <Empty title="登录后管理头像、显示名称与 API Token">
          <Button asChild>
            <a href="/login">登录 / 注册 &gt;</a>
          </Button>
        </Empty>
      </>
    );

  async function run(task: () => Promise<unknown>) {
    setBusy(true);
    setMessage("");
    try {
      await task();
      await Promise.all([profile.refresh(), onChange()]);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadAvatar(blob: Blob) {
    const form = new FormData();
    form.append("file", blob, "avatar.png");
    await run(() => api("/me/avatar", { method: "POST", body: form }));
    setFile(null);
  }

  async function rename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("display_name") || "");
    await run(() => api("/me", { method: "PATCH", body: JSON.stringify({ display_name: name }) }));
    setEditing(false);
  }

  async function createToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    await run(async () => {
      const r = await api<{ token: string }>("/tokens", { method: "POST", body: JSON.stringify({ name: new FormData(form).get("name") }) });
      setToken(r.token);
      setCopied(false);
      form.reset();
      await tokens.refresh();
    });
  }

  const kda = p ? ((p.stats.kills || 0) / Math.max(1, p.stats.deaths || 0)).toFixed(2) : "—";

  return (
    <>
      <PageHead eyebrow="账号与头像" title={p?.display_name || user.display_name} description={`@${user.username}${p ? ` · ${date(p.created_at)} 加入` : ""}`} />
      {search.has("welcome") && (
        <div className="mb-6 border border-blue bg-blue-50 px-3 py-2 text-blue">注册成功！系统已为你生成一枚独一无二的对角对称像素头像，也可以上传自己的图片。</div>
      )}
      <ErrorBox message={message || profile.error} />
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Panel title="头像" ticks>
          <div className="flex flex-col items-center gap-4">
            <Avatar className="size-32 bg-paper ring-2 ring-ink ring-offset-4 ring-offset-paper-2">
              <AvatarImage src={avatarUrl(user.id, p?.avatar_version ?? user.avatar_version)} alt="我的头像" className="[image-rendering:pixelated]" />
              <AvatarFallback className="text-[36px]">{user.display_name.slice(0, 1)}</AvatarFallback>
            </Avatar>
            <span className="text-ink-2">{p?.has_custom_avatar ? "自定义头像" : "默认像素头像 · 对角对称 · 全站唯一"}</span>
            <input
              ref={picker}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={(e) => {
                const chosen = e.target.files?.[0];
                e.target.value = "";
                if (!chosen) return;
                if (chosen.size > 10 * 1024 * 1024) return setMessage("图片不能超过 10 MiB。");
                setFile(chosen);
              }}
            />
            <div className="flex flex-wrap justify-center gap-2">
              <Button onClick={() => picker.current?.click()} disabled={busy}>
                <ImageIcon size={14} /> 上传新头像
              </Button>
              {p?.has_custom_avatar && (
                <Button variant="outline" disabled={busy} onClick={() => void run(() => api("/me/avatar", { method: "DELETE" }))}>
                  <Reload size={14} /> 恢复默认
                </Button>
              )}
            </div>
          </div>
          <div className="mt-6 border-t border-line pt-4">
            {editing ? (
              <form onSubmit={rename} className="flex flex-col gap-2">
                <Label htmlFor="display_name">显示名称</Label>
                <div className="flex gap-2">
                  <Input id="display_name" name="display_name" defaultValue={p?.display_name || user.display_name} maxLength={40} required autoFocus />
                  <Button disabled={busy}>保存</Button>
                </div>
              </form>
            ) : (
              <div className="flex items-center justify-between">
                <span>
                  <span className="text-ink-2">显示名称 </span>
                  {p?.display_name || user.display_name}
                </span>
                <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
                  <Edit size={14} /> 修改
                </Button>
              </div>
            )}
          </div>
        </Panel>

        <div className="flex flex-col gap-6">
          <section className="grid grid-cols-2 gap-5 sm:grid-cols-4">
            <Stat label="Bot / 版本" value={p ? `${p.bots}/${p.versions}` : "—"} />
            <Stat label="参赛场次" value={p ? number(p.stats.games) : "—"} hint={p ? `胜 ${p.stats.wins || 0}` : undefined} />
            <Stat label="KDA" value={kda} hint={p ? `${p.stats.kills || 0} 击沉 / ${p.stats.deaths || 0} 沉没` : undefined} />
            <Stat label="累计搬运" value={p ? number(p.stats.delivered) : "—"} hint={p ? `抢劫 ${number(p.stats.robbed)}` : undefined} />
          </section>

          <PasswordPanel />

          <Panel title="API Token">
            <p className="mt-0 text-ink-2">Token 只显示一次，30 天有效，可访问当前账号的 Bot 与测试。不要写进 Bot 源码或分享给他人。</p>
            <form onSubmit={createToken} className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <div className="flex flex-1 flex-col gap-1.5">
                <Label htmlFor="token-name">用途名称</Label>
                <Input id="token-name" name="name" placeholder="laptop-cli" maxLength={40} required />
              </div>
              <Button disabled={busy}>
                <Plus size={14} /> 创建 Token
              </Button>
            </form>
            {token && (
              <div className="mt-3 flex items-center gap-2 border border-blue bg-blue-50 p-2">
                <code className="min-w-0 flex-1 truncate">{token}</code>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    void navigator.clipboard
                      .writeText(token)
                      .then(() => setCopied(true))
                      .catch(() => setMessage("请手动选中复制。"))
                  }
                >
                  {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "已复制" : "复制"}
                </Button>
              </div>
            )}
            <div className="mt-4 flex flex-col">
              {tokens.data?.tokens.map((t) => (
                <div key={t.id} className="flex items-center gap-3 border-t border-line-2 py-2">
                  <div className="min-w-0 flex-1">
                    <div>{t.name}</div>
                    <div className="text-ink-3">
                      创建 {date(t.created_at)} · 到期 {date(t.expires_at)}
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" className="text-bad" onClick={() => void run(async () => (await api(`/tokens/${t.id}`, { method: "DELETE" }), await tokens.refresh()))}>
                    <Trash size={14} /> 撤销
                  </Button>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="命令行">
            <pre className={cn("m-0 overflow-x-auto bg-ink p-3 text-paper")}>
              {`python3 web/client.py login\npython3 web/client.py upload bot.py --name my-bot --version 1.0\npython3 web/client.py test --bots BOT_ID,builtin-baseline --modes 2`}
            </pre>
            <a className="mt-2 inline-block text-blue" href="/api/docs">
              全部后端接口 &gt;
            </a>
          </Panel>

          <div>
            <Button
              variant="outline"
              onClick={() =>
                void api("/auth/logout", { method: "POST", body: "{}" })
                  .then(onChange)
                  .then(() => navigate("/"))
              }
            >
              <Logout size={14} /> 退出登录
            </Button>
          </div>
        </div>
      </div>
      {file && <Cropper file={file} onCancel={() => setFile(null)} onSave={uploadAvatar} />}
    </>
  );
}
