import { lazy, Suspense, useEffect, useState } from "react";
import { Menu, Logout, User as UserIcon, Code, Login, Ship, Human, Shield } from "@nsmr/pixelart-react";
import { api, useApi } from "@/lib/api";
import { interceptLinks, navigate, useLocation } from "@/lib/router";
import type { Health, User } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ErrorBox, Loading } from "@/components/pixel";
import { UserAvatar } from "@/components/UserAvatar";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import Overview from "@/pages/Overview";

const Matches = lazy(() => import("@/pages/Matches"));
const ReplayPage = lazy(() => import("@/replay/ReplayPage"));
const Leaderboard = lazy(() => import("@/pages/Leaderboard"));
const Bots = lazy(() => import("@/pages/Bots"));
const Tests = lazy(() => import("@/pages/Tests"));
const Account = lazy(() => import("@/pages/Account"));
const Auth = lazy(() => import("@/pages/Auth"));
const Me = lazy(() => import("@/pages/Me"));
const Admin = lazy(() => import("@/pages/Admin"));

const NAV = [
  { href: "/", label: "概览", code: "HOME" },
  { href: "/matches", label: "对战", code: "MATCH" },
  { href: "/leaderboard", label: "排行", code: "RANK" },
  { href: "/bots", label: "Bots", code: "BOTS" },
  { href: "/tests", label: "测试", code: "TEST" },
];

export type Session = { user: User | null; refresh: () => Promise<void> };

function Logo() {
  return (
    <a href="/" className="flex items-center gap-2 whitespace-nowrap" aria-label="Halite 3 Arena 首页">
      <span className="notch flex size-8 items-center justify-center bg-blue text-white">
        <Ship size={20} />
      </span>
      <span className="leading-[14px]">
        HALITE III
        <br />
        <span className="text-blue">ARENA</span>
      </span>
    </a>
  );
}

function UserMenu({ user, onLogout }: { user: User; onLogout: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex cursor-pointer items-center gap-2 outline-none" aria-label="账号菜单">
        <UserAvatar id={user.id} name={user.display_name} version={user.avatar_version} />
        <span className="hidden max-w-[120px] truncate lg:inline">{user.display_name}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-48">
        <DropdownMenuLabel className="font-normal">
          <div>{user.display_name}</div>
          <div className="text-ink-3">@{user.username}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/me")}>
          <Human size={16} /> 我的主页
        </DropdownMenuItem>
        {user.is_admin && (
          <DropdownMenuItem onSelect={() => navigate("/admin")}>
            <Shield size={16} /> 管理后台
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={() => navigate("/settings")}>
          <UserIcon size={16} /> 账号与头像
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/bots")}>
          <Code size={16} /> 我的 Bots
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onLogout} className="text-bad">
          <Logout size={16} /> 退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function App() {
  const session = useApi<{ user: User | null }>("/session");
  const health = useApi<Health>("/health", 15000);
  const { path } = useLocation();
  const [menu, setMenu] = useState(false);
  const user = session.data?.user || null;
  useEffect(() => interceptLinks(), []);
  useEffect(() => setMenu(false), [path]);

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST", body: "{}" });
    } finally {
      await session.refresh();
      navigate("/");
    }
  }

  const matchId = path.match(/^\/matches\/([^/]+)$/)?.[1];
  const jobId = path.match(/^\/tests\/([^/]+)$/)?.[1];
  const refresh = async () => void (await session.refresh());
  let page;
  if (path === "/") page = <Overview user={user} />;
  else if (matchId) page = <ReplayPage id={matchId} />;
  else if (path === "/matches") page = <Matches user={user} />;
  else if (path === "/leaderboard") page = <Leaderboard />;
  else if (path === "/bots") page = <Bots user={user} />;
  else if (path === "/tests" || jobId) page = <Tests user={user} jobId={jobId} />;
  else if (path === "/me") page = <Me user={user} />;
  else if (path === "/admin") page = <Admin user={user} />;
  else if (path === "/settings") page = <Account user={user} onChange={refresh} />;
  else if (path === "/login" || path === "/register") page = <Auth mode={path === "/register" ? "register" : "login"} onDone={refresh} />;
  else
    page = (
      <div className="py-24 text-center">
        <div className="text-[72px] leading-[72px] text-blue">404</div>
        <p className="text-ink-2">这片海域还没有被探索。</p>
        <Button asChild>
          <a href="/">返回港口 &gt;</a>
        </Button>
      </div>
    );
  const fullBleed = Boolean(matchId) || path === "/";
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  const online = health.data?.runner_online;

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex min-h-svh flex-col">
        <header className="sticky top-0 z-40 border-b border-line bg-paper/95 backdrop-blur-[2px]">
          <div className="mx-auto flex h-[52px] max-w-[1440px] items-center gap-4 px-4 sm:h-[60px] sm:px-6">
            <Logo />
            <nav className="ml-6 hidden items-center gap-1 md:flex" aria-label="主导航">
              {NAV.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "relative px-3 py-2 transition-colors duration-200 hover:text-blue",
                    active(item.href) ? "text-blue after:absolute after:inset-x-3 after:-bottom-[9px] after:h-[2px] after:bg-blue sm:after:-bottom-[13px]" : "text-ink",
                  )}
                >
                  {item.label}
                </a>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-3">
              <span className="hidden items-center gap-1.5 text-ink-2 lg:flex" title="比赛执行器状态">
                <i className={cn("pip", online ? "blink text-good" : "text-ink-3")} />
                {online ? "执行器在线" : "执行器离线"}
              </span>
              {user ? (
                <UserMenu user={user} onLogout={() => void logout()} />
              ) : (
                !session.loading && (
                  <div className="hidden items-center gap-2 sm:flex">
                    <Button variant="ghost" size="sm" asChild>
                      <a href="/login">登录</a>
                    </Button>
                    <Button size="sm" asChild>
                      <a href="/register">注册 &gt;</a>
                    </Button>
                  </div>
                )
              )}
              <Sheet open={menu} onOpenChange={setMenu}>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="icon" className="md:hidden" aria-label="打开菜单">
                    <Menu size={20} />
                  </Button>
                </SheetTrigger>
                <SheetContent side="right" className="w-full border-l border-ink bg-paper p-0 sm:max-w-sm">
                  <SheetTitle className="border-b border-line px-5 py-4 font-normal">
                    <span className="text-blue">&gt;_</span> 航行菜单
                  </SheetTitle>
                  <nav className="flex flex-col px-5 py-4" aria-label="移动端导航">
                    {NAV.map((item, i) => (
                      <a
                        key={item.href}
                        href={item.href}
                        className={cn("rise flex items-baseline justify-between border-b border-line py-4 text-[24px] leading-[28px]", `rise-${Math.min(4, i + 1)}`, active(item.href) ? "text-blue" : "text-ink")}
                      >
                        <span>
                          {active(item.href) ? "> " : ""}
                          {item.label}
                        </span>
                        <span className="text-[12px] text-ink-3">{item.code}</span>
                      </a>
                    ))}
                  </nav>
                  <div className="mt-auto flex flex-col gap-2 p-5">
                    {user ? (
                      <>
                        <a href="/settings" className="flex items-center gap-3 border border-line p-3">
                          <UserAvatar id={user.id} name={user.display_name} version={user.avatar_version} size="lg" />
                          <span>
                            {user.display_name}
                            <br />
                            <span className="text-ink-3">账号与头像 &gt;</span>
                          </span>
                        </a>
                        <a href="/me" className="flex items-center gap-2 border border-line p-3">
                          <Human size={16} /> 我的主页 · 提交与排名
                        </a>
                        {user.is_admin && (
                          <a href="/admin" className="flex items-center gap-2 border border-line p-3">
                            <Shield size={16} /> 管理后台
                          </a>
                        )}
                        <Button variant="outline" onClick={() => void logout()}>
                          <Logout size={16} /> 退出登录
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button asChild size="lg">
                          <a href="/register">创建账号 &gt;</a>
                        </Button>
                        <Button asChild variant="outline" size="lg">
                          <a href="/login">
                            <Login size={16} /> 登录
                          </a>
                        </Button>
                      </>
                    )}
                    <span className="mt-2 flex items-center gap-1.5 text-ink-2">
                      <i className={cn("pip", online ? "text-good" : "text-ink-3")} />
                      {online ? "比赛执行器在线" : "执行器离线"}
                    </span>
                  </div>
                </SheetContent>
              </Sheet>
            </div>
          </div>
        </header>
        <main className={cn("flex-1", !fullBleed && "mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 sm:py-10")}>
          {session.error && <ErrorBox message={session.error} />}
          <Suspense fallback={<Loading />}>{session.loading ? <Loading /> : page}</Suspense>
        </main>
        {!matchId && (
          <footer className="border-t border-line">
            <div className="mx-auto flex max-w-[1440px] flex-col gap-2 px-4 py-6 text-ink-2 sm:flex-row sm:items-center sm:justify-between sm:px-6">
              <span>
                HALITE III ARENA <span className="text-ink-3">·</span> 代码保持私有，结果有据可查。
              </span>
              <span className="flex gap-4">
                <a className="hover:text-blue" href="/api/docs">
                  API 文档
                </a>
                <a className="hover:text-blue" href="https://github.com/CMander02/halite3-lab" target="_blank" rel="noreferrer">
                  规则与源码 ↗
                </a>
              </span>
            </div>
          </footer>
        )}
      </div>
    </TooltipProvider>
  );
}
