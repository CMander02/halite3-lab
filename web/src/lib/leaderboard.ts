export const BOARD_VIEWS = ["elo", "tier", "matrix", "kda", "robbed", "delivered", "vision", "mined", "rules"] as const;

export function leaderboardState(search: URLSearchParams) {
  const view = (search.get("view") || search.get("tierlist") || "elo").toLowerCase();
  const mode = search.get("mode") || "";
  return {
    view: BOARD_VIEWS.includes(view as typeof BOARD_VIEWS[number]) ? view : "elo",
    mode: ["2", "4", "8"].includes(mode) ? mode : "",
    filter: { model: search.get("model") || "", effort: search.get("effort") || "", harness: search.get("harness") || "" },
  };
}

/** Preserve other filters and unrelated query parameters when changing one control. */
export function leaderboardHref(search: URLSearchParams, changes: Record<string, string>) {
  const next = new URLSearchParams(search);
  if (next.has("tierlist")) {
    next.set("view", leaderboardState(search).view);
    next.delete("tierlist");
  }
  for (const [key, value] of Object.entries(changes)) {
    if (value) next.set(key, value);
    else next.delete(key);
  }
  return `/leaderboard${next.size ? `?${next}` : ""}`;
}
