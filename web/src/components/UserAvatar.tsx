import { Avatar, AvatarFallback, AvatarGroup, AvatarGroupCount, AvatarImage } from "@/components/ui/avatar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { avatarUrl } from "@/lib/api";
import type { Seat } from "@/lib/types";
import { cn } from "@/lib/utils";

// Platform baseline bots get a fixed pixel "robot" mark instead of a user avatar.
const PLATFORM =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" shape-rendering="crispEdges"><rect width="10" height="10" fill="#0a1a4a"/><g fill="#f5f2e9"><rect x="4" y="1" width="2" height="1"/><rect x="2" y="2" width="6" height="1"/><rect x="2" y="3" width="1" height="3"/><rect x="7" y="3" width="1" height="3"/><rect x="2" y="6" width="6" height="1"/><rect x="3" y="8" width="1" height="1"/><rect x="6" y="8" width="1" height="1"/></g><g fill="#1f4fff"><rect x="4" y="4" width="1" height="1"/><rect x="5" y="4" width="1" height="1"/></g></svg>',
  );

type Size = "sm" | "default" | "lg";

export function UserAvatar({
  id,
  name,
  version,
  size = "default",
  className,
}: {
  id?: string | null;
  name?: string | null;
  version?: number;
  size?: Size;
  className?: string;
}) {
  return (
    <Avatar size={size} className={cn("bg-paper ring-1 ring-ink/20", className)}>
      <AvatarImage src={id ? avatarUrl(id, version) : PLATFORM} alt={name ? `${name} 的头像` : "平台基准"} className="[image-rendering:pixelated]" />
      <AvatarFallback className="bg-blue-50 text-blue">{(name || "?").slice(0, 1).toUpperCase()}</AvatarFallback>
    </Avatar>
  );
}

/** Overlapping circles: everyone whose bot took part in a match. */
export function AvatarStack({ seats, max = 4, size = "sm" }: { seats: Seat[]; max?: number; size?: Size }) {
  const people = new Map<string, { id: string | null; name: string }>();
  for (const seat of seats) {
    const key = seat.author_id || (seat.builtin ? "platform" : seat.author || seat.name);
    if (!people.has(key)) people.set(key, { id: seat.author_id || null, name: seat.builtin ? "平台基准" : seat.author || "未知作者" });
  }
  const list = [...people.values()];
  const shown = list.slice(0, max);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <AvatarGroup className="w-fit">
          {shown.map((person, i) => (
            <UserAvatar key={i} id={person.id} name={person.name} size={size} className="ring-2 ring-paper" />
          ))}
          {list.length > max && <AvatarGroupCount className="bg-ink text-[12px] text-paper ring-paper">+{list.length - max}</AvatarGroupCount>}
        </AvatarGroup>
      </TooltipTrigger>
      <TooltipContent className="bg-ink text-paper">
        {list.length} 位作者：{list.map((p) => p.name).join("、")}
      </TooltipContent>
    </Tooltip>
  );
}
