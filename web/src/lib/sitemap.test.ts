import { describe, expect, it } from "vitest";
import { EDGES, NAV, NODES, USER_MENU, headerTargets, userMenuTargets } from "./sitemap";
import { BOARD_VIEWS, leaderboardState } from "./leaderboard";

describe("site map", () => {
  const ids = new Set(NODES.map((n) => n.id));

  it("only links pages that are on the map", () => {
    for (const e of EDGES) {
      expect(ids.has(e.from), e.from).toBe(true);
      expect(ids.has(e.to), e.to).toBe(true);
    }
  });

  it("has one edge per page pair", () => {
    const pairs = EDGES.map((e) => `${e.from}>${e.to}`);
    expect(new Set(pairs).size).toBe(pairs.length);
  });

  it("puts every header and menu item on the map", () => {
    expect(headerTargets()).toHaveLength(NAV.length);
    expect(userMenuTargets()).toHaveLength(USER_MENU.length);
  });

  it("links each leaderboard view and multiplayer matrix directly", () => {
    const links = NODES.find((n) => n.id === "leaderboard")!.views!;
    const states = links.map((link) => leaderboardState(new URL(link.href, "https://arena.test").searchParams));
    expect(new Set(states.map((s) => s.view))).toEqual(new Set(BOARD_VIEWS));
    expect(states.filter((s) => s.view === "matrix").map((s) => s.mode)).toEqual(["", "2", "4", "8"]);
  });
});
