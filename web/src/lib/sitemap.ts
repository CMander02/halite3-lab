import { BOARD_VIEWS } from "./leaderboard";

const BOARD_LABELS = ["ELO 总榜", "Tier", "胜率矩阵", "KDA", "抢劫", "搬运", "视野", "采矿"];
const CONTEST_TABS: [string, string][] = [["", "概览"], ["standings", "排行"], ["tier", "Tier"], ["matches", "对局"], ["rules", "规则"], ["mine", "我的提交"]];

// Site map: which page (type) links to which. The header and the 我的 menu read their
// items from here, so the /sitemap page always shows the real navigation order. The
// in-page edges are written by hand from the page sources — update them with the page.

/** Contest #0, the standing test contest: the public benchmark, Tier list and default way in. */
export const PRACTICE = "/contests/test-0";

/** Header: public pages only, in the order of the main flow. The logo is the way home. */
export const NAV = [
  { href: "/contests", label: "比赛", code: "CUP" },
  { href: "/leaderboard", label: "排行", code: "RANK" },
  { href: "/matches", label: "对战", code: "MATCH" },
  { href: "/sitemap", label: "地图", code: "MAP" },
];

/** The 我的 menu (header dropdown and mobile menu): everything personal. */
export const USER_MENU = [
  { href: "/me", label: "我的主页" },
  { href: "/bots", label: "我的 Bots" },
  { href: "/tests", label: "私人对练" },
  { href: "/settings", label: "账号与头像" },
  { href: "/admin", label: "管理后台", admin: true },
];

export type Zone = "public" | "contest" | "personal" | "entry";

export type SiteNode = {
  id: string;
  label: string;
  route: string;
  zone: Zone;
  /** who can see the page's content */
  access?: "login" | "admin";
  /** in-page tabs */
  tabs?: string[];
  /** the tabs have their own URLs */
  tabsInUrl?: boolean;
  /** direct links to the page's views */
  views?: { label: string; href: string }[];
  note: string;
  x: number;
  y: number;
};

export const ZONES: Record<Zone, { label: string; color: string }> = {
  public: { label: "公开浏览", color: "var(--blue)" },
  contest: { label: "比赛", color: "#f2542d" },
  personal: { label: "个人工作台", color: "var(--good)" },
  entry: { label: "入口 / 文件", color: "var(--ink-2)" },
};

export const NODES: SiteNode[] = [
  { id: "home", label: "概览", route: "/", zone: "public", note: "首页（点 Logo 回来）：进入比赛、近期对战、#0 Tier 前 5、规则摘要、起航流程（读题 → 提交 → 看排行）", x: 120, y: 90 },
  { id: "matches", label: "对战列表", route: "/matches", zone: "public", note: "全站公开对局 + 自己的私人对局，可按模式 / 版本筛选", x: 120, y: 330 },
  { id: "replay", label: "回放", route: "/matches/:id", zone: "public", tabs: ["战况", "数据", "近期"], note: "单局回放；返回到打开它的页面，参赛者可点进 Bot 页，比赛对局可点回比赛", x: 120, y: 570 },
  { id: "leaderboard", label: "全局排行", route: "/leaderboard", zone: "public", tabs: BOARD_LABELS, tabsInUrl: true,
    views: [
      ...BOARD_VIEWS.map((view, i) => ({ label: BOARD_LABELS[i], href: `/leaderboard?view=${view}` })),
      ...[["2", "1v1"], ["4", "4 人"], ["8", "8 人"]].map(([mode, label]) => ({ label: `胜率矩阵 · ${label}`, href: `/leaderboard?view=matrix&mode=${mode}` })),
    ],
    note: "跨比赛的全局榜：修正后 ELO 总榜、对战胜率矩阵、子榜（全部公开对局）；Tier 是 #0 的成绩，和 #0 比赛页共用一个榜。视图、人数和筛选都在 URL 里。", x: 380, y: 210 },
  { id: "bot", label: "Bot 详情", route: "/bots/:id", zone: "public", note: "任何人的 Bot 公开页：版本、ELO 走势、参加过的比赛", x: 380, y: 450 },
  { id: "contests", label: "比赛列表", route: "/contests", zone: "contest", note: "按状态分组的比赛卡片（#0 常驻测试赛也在这里）", x: 640, y: 90 },
  { id: "contest", label: "比赛详情", route: "/contests/:slug/:tab", zone: "contest", tabs: ["概览", "排行", "Tier（#0）", "对局", "规则", "我的提交", "管理"], tabsInUrl: true,
    views: CONTEST_TABS.map(([tab, label]) => ({ label: `#0 ${label}`, href: `${PRACTICE}${tab && `/${tab}`}` })), note: "比赛的一切：题面与题目包、排行（#0 另有 4 / 8 人评测榜）、Tier、全部对局、规则、提交", x: 640, y: 330 },
  { id: "contestNew", label: "新建比赛", route: "/contests/new", zone: "contest", access: "admin", note: "管理员创建比赛", x: 900, y: 90 },
  { id: "bots", label: "我的 Bots", route: "/bots", zone: "personal", note: "创建 Bot、上传版本、管理版本；参评会提交到 #0 并转到 #0 的“我的提交”", x: 640, y: 570 },
  { id: "me", label: "我的主页", route: "/me", zone: "personal", access: "login", note: "每个版本的模型 / 推理强度 / 轨迹检测与 ELO", x: 900, y: 450 },
  { id: "tests", label: "私人对练", route: "/tests", zone: "personal", access: "login", note: "自选对手的私人循环赛；默认只列私人任务，可勾选显示比赛 / #0 评测任务", x: 1160, y: 450 },
  { id: "test", label: "对练详情", route: "/tests/:id", zone: "personal", access: "login", note: "一个任务的进度和对局；只有任务所有者能打开；比赛任务可回到所属比赛", x: 1160, y: 210 },
  { id: "settings", label: "账号与头像", route: "/settings", zone: "personal", access: "login", note: "头像、密码、API Token、命令行说明", x: 900, y: 210 },
  { id: "admin", label: "管理后台", route: "/admin", zone: "personal", access: "admin", tabs: ["概览", "用户", "提交审核", "模型目录"], note: "用户、提交审核、ELO 修正目录", x: 1160, y: 690 },
  { id: "auth", label: "登录 / 注册", route: "/login · /register", zone: "entry", note: "登录后进 /bots，注册后进 /settings?welcome=1", x: 900, y: 690 },
  { id: "files", label: "下载 / API", route: "*.zip · /api/…", zone: "entry", note: "题目包、prompt.md、靶子源码、示例 ZIP、源码 / 轨迹下载、API 文档", x: 380, y: 690 },
  { id: "sitemap", label: "站点地图", route: "/sitemap", zone: "entry", note: "本页", x: 1160, y: 90 },
];

export type SiteEdge = {
  from: string;
  to: string;
  label: string;
  /** link: a link or button; action: navigation after a form / action succeeds */
  kind?: "link" | "action";
  /** shown only to some visitors */
  when?: "login" | "guest" | "admin" | "owner" | "other";
};

export const EDGES: SiteEdge[] = [
  { from: "home", to: "contest", label: "进入比赛（进行中的比赛，否则 #0）· 起航流程 ①②③ · #0 Tier 榜 · 完整规则" },
  { from: "home", to: "contests", label: "全部比赛" },
  { from: "home", to: "matches", label: "观看回放 · 近期对战“全部”" },
  { from: "home", to: "replay", label: "近期对战行" },
  { from: "home", to: "leaderboard", label: "KDA 王 / 抢劫王（?view=kda / robbed）" },
  { from: "home", to: "auth", label: "创建账号", when: "guest" },
  { from: "home", to: "files", label: "C++ 示例 ZIP" },

  { from: "matches", to: "replay", label: "对局行" },
  { from: "matches", to: "tests", label: "新建私人对练（?new=1）", when: "login" },

  { from: "replay", to: "matches", label: "返回（直接打开时）· 全部记录" },
  { from: "replay", to: "contest", label: "所属比赛" },
  { from: "replay", to: "bot", label: "参赛者" },
  { from: "replay", to: "replay", label: "近期对战" },
  { from: "replay", to: "files", label: "下载回放" },

  { from: "leaderboard", to: "bot", label: "ELO 总榜行 · Tier · 胜率矩阵行列标题 · 子榜行" },
  { from: "leaderboard", to: "contest", label: "#0 比赛页的 Tier · Tier 回放 · 去 #0 提交参评" },

  { from: "bot", to: "bots", label: "返回我的 Bots", when: "owner" },
  { from: "bot", to: "leaderboard", label: "返回排行", when: "other" },
  { from: "bot", to: "contest", label: "参加过的比赛" },
  { from: "bot", to: "matches", label: "最新版本对局 · 版本对局（?version=）" },
  { from: "bot", to: "files", label: "下载源码", when: "owner" },

  { from: "contests", to: "contest", label: "比赛卡片" },
  { from: "contests", to: "contestNew", label: "新建比赛", when: "admin" },
  { from: "contestNew", to: "contest", label: "创建后跳转", kind: "action", when: "admin" },

  { from: "contest", to: "contests", label: "全部比赛 · 删除比赛后" },
  { from: "contest", to: "files", label: "题目包 · prompt.md · 靶子下载" },
  { from: "contest", to: "bot", label: "排行 / Tier / 我的提交 中的 Bot" },
  { from: "contest", to: "replay", label: "对局 tab（我的提交“对局”带 ?version=）" },
  { from: "contest", to: "settings", label: "让 Agent 提交 · 创建 Token", when: "login" },

  { from: "bots", to: "bot", label: "Bot 名称" },
  { from: "bots", to: "files", label: "源码 / 轨迹 · 示例 ZIP · API 文档" },
  { from: "bots", to: "settings", label: "命令行 · API Token" },
  { from: "bots", to: "auth", label: "登录后上传", when: "guest" },
  { from: "bots", to: "contest", label: "参评 · 上传并参评后（#0 我的提交）", kind: "action", when: "login" },
  { from: "bots", to: "me", label: "上传版本后（不参评）", kind: "action", when: "login" },

  { from: "me", to: "bots", label: "上传新版本" },
  { from: "me", to: "matches", label: "版本对局（?version=）" },
  { from: "me", to: "files", label: "下载轨迹" },

  { from: "tests", to: "test", label: "任务卡片 · 提交后跳转" },
  { from: "tests", to: "auth", label: "登录 / 注册", when: "guest" },
  { from: "test", to: "tests", label: "返回列表" },
  { from: "test", to: "replay", label: "比赛记录行" },
  { from: "test", to: "contest", label: "所属比赛（比赛 / #0 任务）" },

  { from: "settings", to: "files", label: "API 文档" },
  { from: "settings", to: "auth", label: "登录 / 注册", when: "guest" },
  { from: "settings", to: "home", label: "退出登录后", kind: "action" },

  { from: "auth", to: "bots", label: "登录后", kind: "action" },
  { from: "auth", to: "settings", label: "注册后", kind: "action" },

  { from: "admin", to: "files", label: "下载轨迹" },
];

/** Node ids reached from the header nav, in header order. */
export function headerTargets() {
  return NAV.map((item) => NODES.find((n) => n.route === item.href)?.id).filter((id): id is string => Boolean(id));
}

export function userMenuTargets() {
  return USER_MENU.map((item) => NODES.find((n) => n.route === item.href)?.id).filter((id): id is string => Boolean(id));
}
