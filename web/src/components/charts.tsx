import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { compact } from "@/lib/api";
import { playerColor } from "@/lib/colors";
import type { SeriesPoint } from "@/replay/replay";
import { cn } from "@/lib/utils";

/*
 * Recharts (via shadcn/ui chart) restyled for the pixel system: stepped lines,
 * square bars, 1px dashed grid, pixel font ticks, no easing animations.
 */
const axis = { tickLine: false, axisLine: { stroke: "var(--ink)" }, tick: { fontSize: 12, fill: "var(--ink-2)" } } as const;
const grid = <CartesianGrid vertical={false} stroke="var(--line)" strokeDasharray="2 4" />;
const frame = "[&_.recharts-surface]:overflow-visible [&_.recharts-tooltip-wrapper]:font-[inherit]";

export function BankChart({ data, players, names, turn, className }: { data: SeriesPoint[]; players: number; names: string[]; turn?: number; className?: string }) {
  const config: ChartConfig = Object.fromEntries(Array.from({ length: players }, (_, p) => [`bank${p}`, { label: names[p] || `P${p}`, color: playerColor(p) }]));
  return (
    <ChartContainer config={config} className={cn("aspect-auto h-[180px] w-full", frame, className)}>
      <LineChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -8 }}>
        {grid}
        <XAxis dataKey="turn" {...axis} interval="preserveStartEnd" minTickGap={24} />
        <YAxis {...axis} width={44} tickFormatter={(v: number) => compact(v)} />
        <ChartTooltip cursor={{ stroke: "var(--ink)", strokeDasharray: "2 2" }} content={<ChartTooltipContent indicator="line" labelFormatter={(_, p) => `回合 ${p?.[0]?.payload?.turn ?? ""}`} />} />
        {Array.from({ length: players }, (_, p) => (
          <Line key={p} dataKey={`bank${p}`} type="stepAfter" stroke={playerColor(p)} strokeWidth={2} dot={false} isAnimationActive={false} />
        ))}
        {turn !== undefined && <ReferenceLine x={turn} stroke="var(--ink)" strokeDasharray="3 3" />}
      </LineChart>
    </ChartContainer>
  );
}

export function DailyChart({ data, className }: { data: { day: number; matches: number }[]; className?: string }) {
  const rows = data.map((d) => ({ ...d, label: new Date(d.day * 1000).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" }) }));
  return (
    <ChartContainer config={{ matches: { label: "完成对局", color: "var(--blue)" } }} className={cn("aspect-auto h-[160px] w-full", frame, className)}>
      <BarChart data={rows} margin={{ top: 6, right: 0, bottom: 0, left: -20 }}>
        {grid}
        <XAxis dataKey="label" {...axis} interval="preserveStartEnd" minTickGap={12} />
        <YAxis {...axis} allowDecimals={false} width={40} />
        <ChartTooltip cursor={{ fill: "var(--blue-50)" }} content={<ChartTooltipContent hideIndicator />} />
        <Bar dataKey="matches" fill="var(--blue)" radius={0} isAnimationActive={false} />
      </BarChart>
    </ChartContainer>
  );
}

/** Horizontal ranked bars for one leaderboard metric. */
export function MetricBars({
  rows,
  format = (v: number) => compact(v),
  label,
  className,
}: {
  rows: { name: string; value: number }[];
  format?: (value: number) => string;
  label: string;
  className?: string;
}) {
  const height = Math.max(120, rows.length * 28 + 24);
  return (
    <ChartContainer config={{ value: { label, color: "var(--blue)" } }} className={cn("aspect-auto w-full", frame, className)} style={{ height }}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 0 }} barCategoryGap={6}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="name" {...axis} width={120} tickFormatter={(v: string) => (v.length > 14 ? `${v.slice(0, 13)}…` : v)} />
        <ChartTooltip cursor={{ fill: "var(--blue-50)" }} content={<ChartTooltipContent hideIndicator formatter={(v) => `${label} ${format(Number(v))}`} />} />
        <Bar
          dataKey="value"
          radius={0}
          isAnimationActive={false}
          label={{ position: "right", fill: "var(--ink)", fontSize: 12, formatter: (v: unknown) => format(Number(v)) }}
        >
          {rows.map((_, i) => (
            <Cell key={i} fill={i === 0 ? "var(--ink)" : i < 3 ? "var(--blue)" : "var(--blue-300)"} />
          ))}
        </Bar>
      </BarChart>
    </ChartContainer>
  );
}

/** ELO across a bot's versions (oldest first); gaps where a version has no rating. */
export function VersionEloChart({ data, className }: { data: { label: string; elo?: number; adjusted?: number; contest?: number }[]; className?: string }) {
  const config: ChartConfig = {
    adjusted: { label: "修正后 ELO", color: "var(--blue)" },
    elo: { label: "原始 ELO", color: "var(--ink-3)" },
    contest: { label: "比赛临时 ELO", color: "var(--ink)" },
  };
  return (
    <ChartContainer config={config} className={cn("aspect-auto h-[220px] w-full", frame, className)}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
        {grid}
        <XAxis dataKey="label" {...axis} interval="preserveStartEnd" minTickGap={12} />
        <YAxis {...axis} width={44} domain={["auto", "auto"]} allowDecimals={false} />
        <ChartTooltip cursor={{ stroke: "var(--ink)", strokeDasharray: "2 2" }} content={<ChartTooltipContent indicator="line" />} />
        <Line dataKey="elo" type="linear" stroke="var(--ink-3)" strokeDasharray="3 3" strokeWidth={1} dot={{ r: 2 }} connectNulls isAnimationActive={false} />
        <Line dataKey="contest" type="linear" stroke="var(--ink)" strokeWidth={1} dot={{ r: 2 }} connectNulls isAnimationActive={false} />
        <Line dataKey="adjusted" type="linear" stroke="var(--blue)" strokeWidth={2} dot={{ r: 3 }} connectNulls isAnimationActive={false} />
      </LineChart>
    </ChartContainer>
  );
}
