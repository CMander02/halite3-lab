import { lazy, Suspense } from "react";
import {
  Ship,
  LayoutDashboard,
  Boxes,
  FlaskConical,
  ListVideo,
  ChartNoAxesColumnIncreasing,
  UserRound,
  LogOut,
  Settings as SettingsIcon,
  ArrowUpRight,
} from "lucide-react";
import { api, useApi } from "./api";
import type { Health, User } from "./types";
import { Loading, ErrorBox } from "./ui";
import Overview from "./Overview";
const Bots = lazy(() => import("./Bots"));
const Tests = lazy(() => import("./Tests"));
const Matches = lazy(() => import("./Matches"));
const ReplayPage = lazy(() => import("./ReplayPage"));
const Leaderboard = lazy(() => import("./Leaderboard"));
const Auth = lazy(() => import("./Auth"));
const Settings = lazy(() => import("./Settings"));
const nav = [
  { href: "/", label: "概览", icon: LayoutDashboard },
  { href: "/bots", label: "我的 Bots", icon: Boxes },
  { href: "/tests", label: "测试任务", icon: FlaskConical },
  { href: "/matches", label: "对战记录", icon: ListVideo },
  { href: "/leaderboard", label: "排行榜", icon: ChartNoAxesColumnIncreasing },
];
export default function App() {
  const session = useApi<{ user: User | null }>("/session");
  const health = useApi<Health>("/health", 15000);
  const user = session.data?.user || null;
  const path = location.pathname.replace(/\/$/, "") || "/";
  const matchId = path.match(/^\/matches\/([^/]+)$/)?.[1],
    jobId = path.match(/^\/tests\/([^/]+)$/)?.[1];
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST", body: "{}" });
      location.assign("/");
    } catch (e) {
      alert((e as Error).message);
    }
  }
  let page;
  if (path === "/") page = <Overview user={user} />;
  else if (path === "/bots") page = <Bots user={user} />;
  else if (path === "/tests" || jobId)
    page = <Tests user={user} jobId={jobId} />;
  else if (path === "/matches") page = <Matches user={user} />;
  else if (matchId) page = <ReplayPage id={matchId} />;
  else if (path === "/leaderboard") page = <Leaderboard />;
  else if (path === "/login" || path === "/register") page = <Auth />;
  else if (path === "/settings") page = <Settings user={user} />;
  else
    page = (
      <div className="empty">
        <h1>页面不存在</h1>
        <a className="button" href="/">
          返回概览
        </a>
      </div>
    );
  return (
    <div className="app">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="Halite 3 Arena 首页">
          <Ship size={34} strokeWidth={1.65} />
          <span>
            HALITE 3<small>ARENA</small>
          </span>
        </a>
        <nav>
          {nav.map(({ href, label, icon: Icon }) => (
            <a
              className={
                (href === "/" ? path === "/" : path.startsWith(href))
                  ? "active"
                  : ""
              }
              href={href}
              key={href}
            >
              <Icon size={21} strokeWidth={1.65} />
              <span>{label}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="runner-indicator">
            <i className={health.data?.runner_online ? "online" : ""} />
            <span>
              {health.data?.runner_online ? "比赛执行器在线" : "执行器等待连接"}
            </span>
          </div>
          <a className="account-link" href={user ? "/settings" : "/login"}>
            <UserRound size={22} />
            <span>
              {user?.display_name || "游客"}
              <small>{user ? "账号与 API" : "登录后管理你的 Bots"}</small>
            </span>
          </a>
          {user ? (
            <button className="sidebar-logout" onClick={() => void logout()}>
              <LogOut size={15} />
              退出登录
            </button>
          ) : (
            <div className="sidebar-signin">
              <a href="/login">登录</a>
              <span>/</span>
              <a href="/register">注册</a>
            </div>
          )}
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <span>Bot 对战实验室</span>
          <div>
            {user ? (
              <a href="/settings">
                <SettingsIcon size={15} />
                {user.display_name}
              </a>
            ) : (
              <>
                <a href="/login">登录</a>
                <span>/</span>
                <a href="/register">注册</a>
              </>
            )}
            <a
              className="home-link"
              href="https://cmander02.com"
              aria-label="CMander 主页"
            >
              <ArrowUpRight size={16} />
            </a>
          </div>
        </header>
        {session.error && <ErrorBox message={session.error} />}
        <div className="content">
          <Suspense fallback={<Loading />}>
            {session.loading ? <Loading /> : page}
          </Suspense>
        </div>
        <footer>
          Halite 3 Arena <span>·</span> 代码保持私有，结果有据可查。
          <a href="/api/docs">API 文档</a>
        </footer>
      </main>
    </div>
  );
}
