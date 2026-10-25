import { useState } from "react";
import type { FormEvent } from "react";
import { KeyRound, Copy, Trash2, Plus, Check, LogOut } from "lucide-react";
import { api, date, useApi } from "./api";
import type { User } from "./types";
import { PageHead, Empty, ErrorBox } from "./ui";
export default function Settings({ user }: { user: User | null }) {
  const { data, error, refresh } = useApi<{
    tokens: {
      id: string;
      name: string;
      created_at: number;
      expires_at: number;
    }[];
  }>(user ? "/tokens" : null);
  const [token, setToken] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [copied, setCopied] = useState(false);
  async function generate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const r = await api<{ token: string }>("/tokens", {
        method: "POST",
        body: JSON.stringify({
          name: new FormData(e.currentTarget).get("name"),
        }),
      });
      setToken(r.token);
      setCopied(false);
      await refresh();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    setMessage("");
    try {
      await api(`/tokens/${id}`, { method: "DELETE" });
      await refresh();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <>
      <PageHead
        title="账号与 API"
        description="通过 Token 直接向后端上传代码、提交测试和收集结果。"
        action={
          user ? (
            <button
              className="button secondary"
              onClick={() => {
                void api("/auth/logout", { method: "POST", body: "{}" })
                  .then(() => location.assign("/"))
                  .catch((e) => setMessage((e as Error).message));
              }}
            >
              <LogOut size={16} />
              退出登录
            </button>
          ) : undefined
        }
      />
      <ErrorBox message={error || message} />
      {!user ? (
        <Empty title="请先登录">
          <a className="button" href="/login">
            登录 / 注册
          </a>
        </Empty>
      ) : (
        <>
          <section className="panel form-panel">
            <div className="section-title">
              <KeyRound size={22} />
              <h2>API Token</h2>
            </div>
            <p className="muted">
              Token 仅显示一次，有效期 30 天，可访问当前账号的 Bot
              与测试。请勿写入 Bot 源码或分享给他人。
            </p>
            <form className="inline-form" onSubmit={generate}>
              <label className="grow">
                用途名称
                <input
                  name="name"
                  placeholder="例如 laptop-cli"
                  maxLength={40}
                  required
                />
              </label>
              <button className="button" disabled={busy}>
                <Plus size={16} />
                创建 Token
              </button>
            </form>
            {token && (
              <div className="token-result">
                <label>
                  新 Token（仅本次显示）
                  <input
                    className="mono"
                    readOnly
                    value={token}
                    onFocus={(e) => e.target.select()}
                  />
                </label>
                <button
                  className="button secondary small"
                  onClick={() => {
                    void navigator.clipboard
                      .writeText(token)
                      .then(() => setCopied(true))
                      .catch(() => setMessage("请选中文本手动复制 Token。"));
                  }}
                >
                  {copied ? <Check size={15} /> : <Copy size={15} />}{" "}
                  {copied ? "已复制" : "复制"}
                </button>
              </div>
            )}
            {data?.tokens.map((t) => (
              <div className="token-row" key={t.id}>
                <div className="grow">
                  <strong>{t.name}</strong>
                  <span className="table-sub">
                    创建于 {date(t.created_at)} · 到期 {date(t.expires_at)}
                  </span>
                </div>
                <button
                  className="button secondary small"
                  onClick={() => void revoke(t.id)}
                >
                  <Trash2 size={14} />
                  撤销
                </button>
              </div>
            ))}
          </section>
          <section className="panel form-panel">
            <h2>从命令行开始</h2>
            <p className="muted">
              先在网页注册账号，再使用项目中的 CLI。登录后的凭据保存在本机权限为
              0600 的配置文件。
            </p>
            <pre className="code-block">
              python3 web/client.py login{`\n`}python3 web/client.py upload
              bot.py --name my-bot --version 1.0{`\n`}python3 web/client.py bots
            </pre>
            <a className="text-link" href="/api/docs">
              查看全部后端接口 →
            </a>
          </section>
        </>
      )}
    </>
  );
}
