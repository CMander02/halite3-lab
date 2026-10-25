import { useState } from "react";
import { ChevronLeft, ChevronRight, Plus } from "@nsmr/pixelart-react";
import type { Match, User } from "@/lib/types";
import { useApi } from "@/lib/api";
import { useLocation } from "@/lib/router";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ErrorBox, Loading, PageHead } from "@/components/pixel";
import MatchList from "@/components/MatchList";

const MODES = [
  ["", "全部"],
  ["2", "1v1"],
  ["4", "4 人"],
  ["8", "8 人"],
];

export default function Matches({ user }: { user: User | null }) {
  const { search } = useLocation();
  const [mode, setMode] = useState("");
  const [scope, setScope] = useState("all");
  const [offset, setOffset] = useState(0);
  const query = new URLSearchParams({ offset: String(offset), scope });
  if (mode) query.set("mode", mode);
  const version = search.get("version");
  if (version) query.set("version", version);
  const { data, error, loading } = useApi<{ matches: Match[]; total: number }>(`/matches?${query}`, 8000);
  const total = data?.total || 0;

  return (
    <>
      <PageHead
        eyebrow="对战记录"
        title="每一局都能回放"
        description="完整轨迹、参赛版本与结果。私人测试只有自己可见。"
        action={
          user && (
            <Button asChild>
              <a href="/tests?new=1">
                <Plus size={16} /> 新建测试
              </a>
            </Button>
          )
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex border border-ink">
          {MODES.map(([key, label]) => (
            <button
              key={key}
              className={cn("h-8 cursor-pointer px-3", mode === key ? "bg-ink text-paper" : "hover:bg-blue-50")}
              onClick={() => {
                setMode(key);
                setOffset(0);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {user && (
          <div className="flex border border-line">
            {[
              ["all", "我的与公开"],
              ["mine", "仅我的"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={cn("h-8 cursor-pointer px-3", scope === key ? "bg-blue text-white" : "hover:bg-blue-50")}
                onClick={() => {
                  setScope(key);
                  setOffset(0);
                }}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        {version && (
          <a href="/matches" className="text-blue">
            × 清除版本筛选
          </a>
        )}
        <span className="ml-auto text-ink-2">共 {total} 场</span>
      </div>
      <ErrorBox message={error} />
      <div className="pixel-frame">{loading ? <Loading /> : <MatchList matches={data?.matches || []} />}</div>
      {total > 30 && (
        <div className="mt-4 flex items-center justify-end gap-2">
          <span className="text-ink-2">
            第 {Math.floor(offset / 30) + 1} / {Math.ceil(total / 30)} 页
          </span>
          <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>
            <ChevronLeft size={14} /> 上一页
          </Button>
          <Button variant="outline" size="sm" disabled={offset + 30 >= total} onClick={() => setOffset(offset + 30)}>
            下一页 <ChevronRight size={14} />
          </Button>
        </div>
      )}
    </>
  );
}
