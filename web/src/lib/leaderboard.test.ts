import { describe, expect, it } from "vitest";
import { leaderboardHref, leaderboardState } from "./leaderboard";

describe("leaderboard URL state", () => {
  it("opens shared views, mode and setup filters, including the tierlist alias", () => {
    expect(leaderboardState(new URLSearchParams("view=matrix&mode=4&model=opus&effort=high&harness=codex"))).toEqual({
      view: "matrix", mode: "4", filter: { model: "opus", effort: "high", harness: "codex" },
    });
    expect(leaderboardState(new URLSearchParams("tierlist=ELO")).view).toBe("elo");
    expect(leaderboardState(new URLSearchParams("tierlist=Tier")).view).toBe("tier");
    expect(leaderboardState(new URLSearchParams("view=invalid&mode=3"))).toMatchObject({ view: "elo", mode: "" });
  });

  it("preserves independent filters and unrelated parameters when changing views", () => {
    const search = new URLSearchParams("view=elo&mode=8&model=opus&source=shared");
    const href = leaderboardHref(search, { view: "matrix" });
    expect(href).toBe("/leaderboard?view=matrix&mode=8&model=opus&source=shared");
    expect(search.get("view")).toBe("elo");
    const cleared = leaderboardHref(new URLSearchParams(href.split("?")[1]), { model: "", effort: "", harness: "" });
    expect(cleared).toBe("/leaderboard?view=matrix&mode=8&source=shared");
  });

  it("canonicalizes legacy links and safely encodes filter values", () => {
    expect(leaderboardHref(new URLSearchParams("tierlist=Tier"), { mode: "2" })).toBe("/leaderboard?view=tier&mode=2");
    const href = leaderboardHref(new URLSearchParams(), { view: "elo", model: "a&b / 中文" });
    expect(leaderboardState(new URLSearchParams(href.split("?")[1])).filter.model).toBe("a&b / 中文");
  });
});
