import { useState } from "react";
import { ArrowRight, GitMerge, List, Map as MapIcon } from "@nsmr/pixelart-react";
import { EDGES, NAV, NODES, USER_MENU, ZONES, headerTargets, userMenuTargets, type SiteEdge, type SiteNode } from "@/lib/sitemap";
import { useLocation } from "@/lib/router";
import { cn } from "@/lib/utils";
import { PageHead, Panel, Tag } from "@/components/pixel";

const W = 176;
const H = 64;
const VIEW = { width: 1280, height: 760 };

const WHEN: Record<NonNullable<SiteEdge["when"]>, string> = { login: "登录后", guest: "未登录", admin: "管理员", owner: "作者本人" };
const ACCESS: Record<NonNullable<SiteNode["access"]>, string> = { login: "需登录", admin: "仅管理员" };

const byId = new Map(NODES.map((n) => [n.id, n]));
const header = headerTargets();
const menu = userMenuTargets();

/** Where the ray from the node centre towards (tx, ty) leaves the node's box. */
function exit(n: SiteNode, tx: number, ty: number, pad = 4) {
  const dx = tx - n.x;
  const dy = ty - n.y;
  const sx = dx ? (W / 2 + pad) / Math.abs(dx) : Infinity;
  const sy = dy ? (H / 2 + pad) / Math.abs(dy) : Infinity;
  const s = Math.min(sx, sy);
  return [n.x + dx * s, n.y + dy * s];
}

function edgePath(e: SiteEdge) {
  const a = byId.get(e.from)!;
  const b = byId.get(e.to)!;
  if (a === b) {
    const x = a.x + W / 2 - 20;
    const y = a.y - H / 2;
    return `M ${x - 14} ${y - 4} C ${x - 18} ${y - 40}, ${x + 30} ${y - 40}, ${x + 18} ${y - 4}`;
  }
  // bend both directions of a two-way pair apart; one-way edges get a slight bend too
  const twoWay = EDGES.some((o) => o.from === e.to && o.to === e.from);
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const len = Math.hypot(b.x - a.x, b.y - a.y);
  const bend = twoWay ? 26 : 10;
  const cx = mx + (-(b.y - a.y) / len) * bend;
  const cy = my + ((b.x - a.x) / len) * bend;
  const [x1, y1] = exit(a, cx, cy);
  const [x2, y2] = exit(b, cx, cy, 8);
  return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
}

function Graph({ focus, files, onFocus, onHover }: { focus: string | null; files: boolean; onFocus: (id: string | null) => void; onHover: (id: string | null) => void }) {
  const tone = (e: SiteEdge) => (!focus ? "idle" : e.from === focus ? "out" : e.to === focus ? "in" : "dim");
  const colors = { idle: "var(--ink-3)", out: "var(--blue)", in: "#f2542d", dim: "var(--line)" };
  // draw highlighted edges last so they sit on top
  const edges = EDGES.filter((e) => files || e.to !== "files").sort((a, b) => Number(tone(a) !== "dim") - Number(tone(b) !== "dim"));
  return (
    <svg viewBox={`0 0 ${VIEW.width} ${VIEW.height}`} className="block h-auto w-full min-w-[960px] select-none" role="img" aria-label="站点有向图：页面之间的链接">
      <defs>
        {Object.entries(colors).map(([key, color]) => (
          <marker key={key} id={`arrow-${key}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
          </marker>
        ))}
      </defs>
      <rect x={0} y={0} width={VIEW.width} height={VIEW.height} fill="transparent" onClick={() => onFocus(null)} />
      {edges.map((e) => {
        const t = tone(e);
        return (
          <path
            key={`${e.from}-${e.to}`}
            d={edgePath(e)}
            fill="none"
            stroke={colors[t]}
            strokeWidth={t === "out" || t === "in" ? 2.5 : 1.5}
            strokeDasharray={e.kind === "action" ? "6 4" : undefined}
            markerEnd={`url(#arrow-${t})`}
          >
            <title>{`${byId.get(e.from)!.label} → ${byId.get(e.to)!.label}：${e.label}${e.when ? `（${WHEN[e.when]}）` : ""}`}</title>
          </path>
        );
      })}
      {NODES.filter((n) => files || n.id !== "files").map((n) => {
        const on = focus === n.id;
        const linked = focus && EDGES.some((e) => (e.from === focus && e.to === n.id) || (e.to === focus && e.from === n.id));
        const nav = header.indexOf(n.id);
        return (
          <g
            key={n.id}
            transform={`translate(${n.x - W / 2} ${n.y - H / 2})`}
            className="cursor-pointer"
            opacity={!focus || on || linked ? 1 : 0.35}
            onClick={() => onFocus(on ? null : n.id)}
            onMouseEnter={() => onHover(n.id)}
            onMouseLeave={() => onHover(null)}
          >
            <rect width={W} height={H} fill={on ? "var(--blue-50)" : "var(--paper-2)"} stroke={on ? "var(--ink)" : "var(--line)"} strokeWidth={on ? 2 : 1} />
            <rect width={5} height={H} fill={ZONES[n.zone].color} />
            <text x={16} y={25} fontSize={17} fontWeight={700} fill="var(--ink)">
              {n.label}
            </text>
            <text x={16} y={46} fontSize={12} fill="var(--ink-3)" fontFamily="var(--font-mono)">
              {n.route}
            </text>
            {(n.access || n.tabs) && (
              <text x={W - 8} y={46} fontSize={11} textAnchor="end" fill={n.access === "admin" ? "#f2542d" : "var(--ink-2)"}>
                {[n.tabs && `${n.tabs.length} tab`, n.access && ACCESS[n.access]].filter(Boolean).join(" · ")}
              </text>
            )}
            {nav >= 0 && (
              <g transform={`translate(${W - 34} -10)`}>
                <rect width={34} height={18} fill="var(--ink)" />
                <text x={17} y={13} fontSize={11} textAnchor="middle" fill="var(--paper)">
                  页头{nav + 1}
                </text>
              </g>
            )}
            {menu.includes(n.id) && (
              <g transform={`translate(${nav >= 0 ? W - 72 : W - 34} -10)`}>
                <rect width={34} height={18} fill="var(--good)" />
                <text x={17} y={13} fontSize={11} textAnchor="middle" fill="white">
                  菜单
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function EdgeLine({ edge, side }: { edge: SiteEdge; side: "out" | "in" }) {
  const other = byId.get(side === "out" ? edge.to : edge.from)!;
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 border-b border-line-2 py-1.5 last:border-0">
      <span className={side === "out" ? "text-blue" : "text-[#f2542d]"}>{side === "out" ? "→" : "←"}</span>
      <span className="font-bold">{other.label}</span>
      <span className="text-ink-2">{edge.label}</span>
      {edge.kind === "action" && <Tag>操作后跳转</Tag>}
      {edge.when && <Tag>{WHEN[edge.when]}</Tag>}
    </li>
  );
}

function NodePanel({ id }: { id: string | null }) {
  const n = id ? byId.get(id) : null;
  if (!n)
    return (
      <Panel title="怎么看" icon={GitMerge} tone="blue">
        <ul className="m-0 flex list-none flex-col gap-2 p-0 text-ink-2">
          <li>每个方框是一类页面，箭头是页面里的链接或按钮：A → B 表示在 A 上能直接点到 B。</li>
          <li>虚线是操作成功后的自动跳转（上传、提交、登录之后）。</li>
          <li>
            <span className="bg-ink px-1 text-paper">页头n</span> 是页头导航的第 n 项，<span className="bg-good px-1 text-white">菜单</span> 是右上角账号菜单里的项。页头和菜单在每一页都有，所以不另外画箭头。
          </li>
          <li>点一个方框：蓝色是它能去的页面，橙色是能来到它的页面。</li>
        </ul>
        <div className="mt-4 flex flex-wrap gap-3 border-t border-line pt-3">
          {Object.values(ZONES).map((z) => (
            <span key={z.label} className="flex items-center gap-1.5 text-ink-2">
              <span className="inline-block h-3 w-1.5" style={{ background: z.color }} /> {z.label}
            </span>
          ))}
        </div>
      </Panel>
    );
  const out = EDGES.filter((e) => e.from === n.id);
  const inc = EDGES.filter((e) => e.to === n.id);
  const nav = header.indexOf(n.id);
  const concrete = !/[:*·]/.test(n.route);
  return (
    <Panel
      title={
        <>
          {n.label} <span className="font-normal text-ink-3">{n.route}</span>
        </>
      }
      icon={MapIcon}
      tone="blue"
      action={
        concrete && (
          <a href={n.route} className="flex items-center gap-1 text-blue">
            打开 <ArrowRight size={12} />
          </a>
        )
      }
    >
      <p className="mt-0 text-ink-2">{n.note}</p>
      <div className="mb-3 flex flex-wrap gap-2">
        <Tag>{ZONES[n.zone].label}</Tag>
        {n.access && <Tag>{ACCESS[n.access]}</Tag>}
        {nav >= 0 && <Tag className="border-ink bg-ink text-paper">页头第 {nav + 1} 项</Tag>}
        {menu.includes(n.id) && <Tag className="border-good bg-good text-white">账号菜单</Tag>}
        {n.tabs && <Tag>tab：{n.tabs.join(" / ")}（{n.views ? "可直接链接" : "不在 URL 里"}）</Tag>}
      </div>
      {n.views && (
        <nav aria-label={`${n.label}视图链接`} className="mb-4 flex flex-wrap gap-2">
          {n.views.map((view) => <a key={view.href} href={view.href} className="border border-line px-2 py-1 text-blue hover:border-ink">{view.label}</a>)}
        </nav>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
        <div>
          <div className="eyebrow mb-1">能去 · {out.length}</div>
          <ul className="m-0 list-none p-0">{out.length ? out.map((e) => <EdgeLine key={e.to} edge={e} side="out" />) : <li className="text-ink-3">没有出口（只能靠页头离开）</li>}</ul>
        </div>
        <div>
          <div className="eyebrow mb-1">从哪来 · {inc.length}</div>
          <ul className="m-0 list-none p-0">{inc.length ? inc.map((e) => <EdgeLine key={e.from} edge={e} side="in" />) : <li className="text-ink-3">没有页面链到这里{nav >= 0 || menu.includes(n.id) ? "，只能从页头 / 菜单进入" : ""}</li>}</ul>
        </div>
      </div>
    </Panel>
  );
}

export default function SiteMap() {
  const { search } = useLocation();
  const [selected, setSelected] = useState<string | null>(() => search.get("focus"));
  const [files, setFiles] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const focus = hover || selected;
  return (
    <>
      <PageHead eyebrow="站点地图" title="哪个页面能进入哪个页面" description="页头导航、账号菜单和每个页面里的链接，画成一张有向图。点方框查看它的出口和入口。" />
      <section className="pixel-frame mb-6 flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-20 shrink-0 text-ink-2">页头顺序</span>
          {NAV.map((item, i) => (
            <span key={item.href} className="flex items-center gap-2">
              {i > 0 && <span className="text-ink-3">·</span>}
              <button className={cn("cursor-pointer border px-2 py-0.5", focus === header[i] ? "border-ink bg-blue-50" : "border-line hover:border-ink")} onClick={() => setSelected(header[i])}>
                <span className="num mr-1 text-ink-3">{i + 1}</span>
                {item.label}
              </button>
            </span>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-20 shrink-0 text-ink-2">账号菜单</span>
          {USER_MENU.map((item, i) => (
            <span key={item.href} className="flex items-center gap-2">
              {i > 0 && <span className="text-ink-3">·</span>}
              <button className={cn("cursor-pointer border px-2 py-0.5", focus === menu[i] ? "border-ink bg-blue-50" : "border-line hover:border-ink")} onClick={() => setSelected(menu[i])}>
                {item.label}
                {item.admin && <span className="ml-1 text-ink-3">（管理员）</span>}
              </button>
            </span>
          ))}
          <span className="text-ink-3">· 退出登录 → 概览</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-20 shrink-0 text-ink-2">页脚</span>
          <span>API 文档</span>
          <span className="text-ink-3">·</span>
          <span>规则与源码 ↗（GitHub）</span>
          <label className="ml-auto flex cursor-pointer items-center gap-2 text-ink-2">
            <input type="checkbox" checked={files} onChange={(e) => setFiles(e.target.checked)} className="size-4 accent-[var(--blue)]" /> 在图上显示“下载 / API”
          </label>
        </div>
      </section>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="pixel-frame overflow-x-auto p-2">
          <Graph focus={focus} files={files} onFocus={setSelected} onHover={setHover} />
        </div>
        <div>
          <NodePanel id={focus} />
        </div>
      </div>
      <Panel title={`全部链接 · ${EDGES.length} 条`} icon={List} className="mt-6" bodyClassName="p-0 overflow-x-auto">
        <table className="ptable">
          <thead>
            <tr>
              <th>从</th>
              <th>到</th>
              <th>入口</th>
              <th>条件</th>
            </tr>
          </thead>
          <tbody>
            {EDGES.map((e) => (
              <tr key={`${e.from}-${e.to}`} className="cursor-pointer hover:bg-blue-50" onClick={() => setSelected(e.from)}>
                <td className="whitespace-nowrap">{byId.get(e.from)!.label}</td>
                <td className="whitespace-nowrap">{byId.get(e.to)!.label}</td>
                <td className="text-ink-2">{e.label}</td>
                <td className="whitespace-nowrap text-ink-2">{[e.kind === "action" && "操作后跳转", e.when && WHEN[e.when]].filter(Boolean).join(" · ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </>
  );
}
