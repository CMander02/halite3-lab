import { useEffect, useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import type { Attribution, Catalog, CatalogEntry, CatalogKind } from "@/lib/types";
import { cn } from "@/lib/utils";

// The catalog changes rarely: fetch it once per page load and share it.
let cached: Promise<Catalog> | null = null;
export function loadCatalog(force = false) {
  if (!cached || force) cached = api<Catalog>("/catalog").catch((e) => ((cached = null), Promise.reject(e)));
  return cached;
}

export function useCatalog() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  useEffect(() => {
    let live = true;
    loadCatalog().then((c) => live && setCatalog(c), () => undefined);
    return () => {
      live = false;
    };
  }, []);
  return catalog;
}

export function entry(catalog: Catalog | null, kind: CatalogKind, id: string | null | undefined): CatalogEntry {
  const found = catalog?.[kind].find((e) => e.id === (id || "unknown"));
  return found || { id: id || "unknown", name: id && id !== "unknown" ? id : "未知", vendor: "", region: "", icon: "", elo_offset: 0, sort: 0, enabled: true };
}

export const REGION: Record<string, string> = { us: "美国", cn: "中国", other: "其他", "": "其他" };
export const SOURCE: Record<string, string> = { declared: "用户声明", detected: "轨迹检测", admin: "管理员确认" };
export const CONFIDENCE: Record<string, string> = { high: "高", medium: "中", low: "低", none: "无" };

export function Icon({ name, className }: { name?: string; className?: string }) {
  if (!name) return <span className={cn("inline-block size-4 shrink-0 bg-[var(--line)]", className)} aria-hidden />;
  return <img src={`/model-icons/${name}.svg`} alt="" className={cn("size-4 shrink-0", className)} loading="lazy" />;
}

const signed = (v: number) => (v > 0 ? `−${v}` : v < 0 ? `+${-v}` : "±0");
export const correctionLabel = signed;

/** Icon + name of one catalog entry. */
export function CatalogChip({ kind, id, catalog, className, muted }: { kind: CatalogKind; id?: string | null; catalog: Catalog | null; className?: string; muted?: boolean }) {
  const e = entry(catalog, kind, id);
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5", muted && "text-ink-2", className)}>
      {kind !== "effort" && <Icon name={e.icon} />}
      <span className="truncate">{e.name}</span>
    </span>
  );
}

/** Model · effort · harness in one line, with the source of each value on hover. */
export function SetupLine({ attribution, catalog, compact = false }: { attribution: Attribution | { model: { value: string }; effort: { value: string }; harness: { value: string }; mismatch?: string[]; correction?: number } | null; catalog: Catalog | null; compact?: boolean }) {
  if (!attribution) return <span className="text-ink-3">平台基准</span>;
  const parts = attribution as Attribution;
  const body = (
    <span className={cn("flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5", compact && "flex-nowrap")}>
      <CatalogChip kind="model" id={parts.model.value} catalog={catalog} />
      <span className="border border-line px-1 text-[12px] leading-[16px] text-ink-2">{entry(catalog, "effort", parts.effort.value).name}</span>
      {!compact && <CatalogChip kind="harness" id={parts.harness.value} catalog={catalog} muted />}
      {parts.mismatch?.length ? <span className="text-warn" title="声明与轨迹检测不一致">⚠</span> : null}
    </span>
  );
  if (!("declared" in parts.model)) return body;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="min-w-0 cursor-help">{body}</span>
      </TooltipTrigger>
      <TooltipContent className="max-w-80 bg-ink text-paper">
        {(["model", "effort", "harness"] as CatalogKind[]).map((kind) => {
          const p = parts[kind];
          return (
            <div key={kind}>
              {{ model: "模型", effort: "推理", harness: "平台" }[kind]}：{entry(catalog, kind, p.value).name}（{SOURCE[p.source]}，{signed(p.offset)}）
              {p.declared !== p.detected && p.detected !== "unknown" && (
                <span className="opacity-70">
                  {" "}
                  声明 {entry(catalog, kind, p.declared).name} / 检测 {entry(catalog, kind, p.detected).name}
                </span>
              )}
            </div>
          );
        })}
        <div className="mt-1">合计 ELO 修正 {signed(parts.correction)}</div>
      </TooltipContent>
    </Tooltip>
  );
}

/** Native select grouped by region; options carry the correction so users see the trade-off. */
export function CatalogSelect({ kind, catalog, name, value, onChange, id }: { kind: CatalogKind; catalog: Catalog | null; name: string; value: string; onChange: (v: string) => void; id?: string }) {
  const entries = catalog?.[kind] || [];
  const groups: [string, CatalogEntry[]][] =
    kind === "effort"
      ? [["", entries]]
      : (["us", "cn", "other"] as const).map((r) => [REGION[r] + (kind === "model" ? "模型" : " Harness / 平台"), entries.filter((e) => (e.region || "other") === r)]);
  const current = entry(catalog, kind, value);
  return (
    <div className="flex h-9 items-center gap-2 border border-line bg-paper-2 px-2 focus-within:border-ink">
      {kind !== "effort" && <Icon name={current.icon} />}
      <select id={id} name={name} value={value} onChange={(e) => onChange(e.target.value)} className="h-full min-w-0 flex-1 cursor-pointer bg-transparent outline-none">
        {groups.map(([label, list]) =>
          label ? (
            list.length ? (
              <optgroup key={label} label={label}>
                {list.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                    {e.vendor ? ` · ${e.vendor}` : ""}（{signed(e.elo_offset)}）
                  </option>
                ))}
              </optgroup>
            ) : null
          ) : (
            list.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}（{signed(e.elo_offset)}）
              </option>
            ))
          ),
        )}
      </select>
    </div>
  );
}
