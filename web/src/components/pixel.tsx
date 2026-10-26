import type { ComponentType, ReactNode } from "react";
import { Loader, WarningBox } from "@nsmr/pixelart-react";
import { cn } from "@/lib/utils";
import { IconTile, type Tone } from "@/components/glyphs";

export function PageHead({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rise mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
        <h1 className="m-0 font-pixel text-[24px] leading-[28px] font-normal break-words sm:text-[36px] sm:leading-[40px]">{title}</h1>
        {description && <p className="mt-2 mb-0 max-w-[640px] text-ink-2">{description}</p>}
      </div>
      {action && <div className="flex shrink-0 flex-wrap gap-2">{action}</div>}
    </div>
  );
}

export function Panel({
  title,
  icon,
  tone,
  action,
  children,
  className,
  bodyClassName,
  ticks = false,
}: {
  title?: ReactNode;
  /** pixelart-react icon or glyphIcon(); shown on a colour tile before the title */
  icon?: ComponentType<{ size?: number; className?: string }>;
  tone?: Tone;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  ticks?: boolean;
}) {
  return (
    <section className={cn("pixel-frame", ticks && "ticks", className)}>
      {(title || action) && (
        <header className="flex min-h-12 items-center justify-between gap-3 border-b border-line px-4 py-2">
          <h2 className="m-0 flex min-w-0 items-center gap-2.5 text-[16px] leading-[24px] font-bold">
            {icon ? <IconTile icon={icon} tone={tone} size={16} /> : <span className="notch size-2.5 shrink-0 bg-blue" aria-hidden />}
            <span className="min-w-0">{title}</span>
          </h2>
          {action}
        </header>
      )}
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, className }: { label: ReactNode; value: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <div className={cn("hairline-top pt-3", className)}>
      <div className="num font-pixel text-[36px] leading-[40px] text-ink sm:text-[48px] sm:leading-[52px]">{value}</div>
      <div className="mt-1 text-ink">{label}</div>
      {hint && <div className="text-ink-3">{hint}</div>}
    </div>
  );
}

export function Loading({ label = "正在加载" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-ink-2" role="status">
      <Loader size={16} className="animate-spin" /> {label}
      <span className="blink">_</span>
    </div>
  );
}

export function ErrorBox({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-4 flex items-start gap-2 border border-bad bg-[#fff1ee] px-3 py-2 text-bad" role="alert">
      <WarningBox size={16} className="mt-0.5 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

export function Empty({ title, children, art }: { title: ReactNode; children?: ReactNode; art?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
      {art ?? <div className="dots h-10 w-24 opacity-70" />}
      <strong className="font-normal text-ink">{title}</strong>
      {children && <div className="max-w-[420px] text-ink-2">{children}</div>}
    </div>
  );
}

const statusLabels: Record<string, string> = {
  queued: "等待",
  running: "运行中",
  complete: "完成",
  failed: "失败",
  cancelled: "取消",
  interrupted: "中断",
};
const statusColors: Record<string, string> = {
  queued: "text-ink-3",
  running: "text-blue",
  complete: "text-good",
  failed: "text-bad",
  cancelled: "text-ink-3",
  interrupted: "text-warn",
};

export function Status({ value }: { value: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", statusColors[value] || "text-ink-2")}>
      <i className={cn("pip", value === "running" && "blink")} />
      {statusLabels[value] || value}
    </span>
  );
}

export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center border border-line px-1.5 text-[13px] leading-[20px] whitespace-nowrap text-ink-2", className)}>{children}</span>;
}

export function TierBadge({ tier, className }: { tier: string; className?: string }) {
  const tone: Record<string, string> = {
    S: "bg-ink text-paper",
    A: "bg-blue text-white",
    B: "bg-blue-100 text-blue-700",
    C: "bg-paper text-ink-2 border border-line",
  };
  return <span className={cn("notch inline-flex size-7 items-center justify-center font-pixel text-[12px]", tone[tier] || tone.C, className)}>{tier}</span>;
}

/** Proportional pixel bar (stepped by 2px to keep the grid). */
export function PixelBar({ value, max, color = "var(--blue)", className }: { value: number; max: number; color?: string; className?: string }) {
  const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  return (
    <div className={cn("dither-25 h-2 w-full", className)}>
      <div className="h-full" style={{ width: `${Math.round(ratio * 50) * 2}%`, background: color }} />
    </div>
  );
}

export function ModeLabel({ mode }: { mode: number }) {
  return <>{mode === 2 ? "1v1" : `${mode} 人混战`}</>;
}
