import { useState } from "react";
import type { FormEvent } from "react";
import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { api } from "./api";
import { ErrorBox } from "./ui";
export default function Auth() {
  const initial = location.pathname === "/register";
  const [register, setRegister] = useState(initial),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await api(`/auth/${register ? "register" : "login"}`, {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
          display_name: form.get("display_name") || "",
        }),
      });
      location.assign("/bots");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <div className="auth-story">
        <LockKeyhole size={34} />
        <h1>
          你的代码。
          <br />
          你的策略实验室。
        </h1>
        <p>
          为每次改进保留一个版本，
          <br />
          让每场对局都有迹可循。
        </p>
        <div className="auth-promises">
          <span>
            <ShieldCheck size={18} /> 源码和私人测试按账号隔离
          </span>
          <span>
            <ShieldCheck size={18} /> 每个 Bot 在独立进程沙箱中运行
          </span>
          <span>
            <ShieldCheck size={18} /> 自主选择是否参加公开排名
          </span>
        </div>
      </div>
      <section className="auth-form panel">
        <div className="tabs auth-tabs">
          <button
            className={!register ? "active" : ""}
            onClick={() => {
              setRegister(false);
              setError("");
            }}
          >
            登录
          </button>
          <button
            className={register ? "active" : ""}
            onClick={() => {
              setRegister(true);
              setError("");
            }}
          >
            注册
          </button>
        </div>
        <h2>{register ? "创建账号" : "欢迎回来"}</h2>
        <p className="muted">
          {register
            ? "创建独立账号，开始管理你的 Bots。"
            : "登录后查看自己的版本、任务和对战记录。"}
        </p>
        <form onSubmit={submit}>
          <label>
            用户名
            <input
              name="username"
              autoComplete="username"
              required
              minLength={3}
              maxLength={32}
              pattern="[a-zA-Z0-9][a-zA-Z0-9_-]{2,31}"
              placeholder="例如 captain_01"
            />
          </label>
          {register && (
            <label>
              显示名称
              <input
                name="display_name"
                autoComplete="nickname"
                maxLength={40}
                placeholder="排行榜展示名称（可选）"
              />
            </label>
          )}
          <label>
            密码
            <input
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              minLength={12}
              maxLength={128}
              required
              placeholder="至少 12 个字符"
            />
          </label>
          <ErrorBox message={error} />
          <button className="button full" disabled={busy}>
            {busy ? "正在处理…" : register ? "创建账号" : "登录"}
            <ArrowRight size={17} />
          </button>
        </form>
        <p className="caption">此版本不通过邮箱找回密码，请妥善保存密码。</p>
      </section>
    </div>
  );
}
