import { useCatalog } from "@/components/ModelBadge";
import { UserAvatar } from "@/components/UserAvatar";
import { BotIcon } from "@/components/BotIcon";

export type Identity = { author_id: string | null; author: string | null; bot_name: string; version: string; bot_id?: string; builtin?: number; model?: string | null; attribution?: { model: { value: string } } | null };

export function fullName(e: Identity) {
  return `${e.bot_name} v${e.version} · ${e.builtin ? "平台基准" : e.author || "未知作者"}`;
}

/** Author avatar + bot icon + truncated name; the full name is in the title. */
export function Who({ e }: { e: Identity }) {
  const catalog = useCatalog();
  return (
    <span className="flex min-w-0 items-center gap-2" title={fullName(e)}>
      <UserAvatar id={e.author_id} name={e.author || "平台基准"} size="sm" />
      {e.bot_id && <BotIcon id={e.bot_id} model={e.model || e.attribution?.model.value} catalog={catalog} className="size-6" />}
      <span className="min-w-0">
        <span className="block truncate">
          {e.bot_name} <span className="text-ink-3">v{e.version}</span>
        </span>
        <span className="block truncate text-ink-3">{e.builtin ? "平台基准" : e.author}</span>
      </span>
    </span>
  );
}
