import { describe, expect, it } from "vitest";
import { EDGES, NAV, NODES, USER_MENU, headerTargets, userMenuTargets } from "./sitemap";

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
});
