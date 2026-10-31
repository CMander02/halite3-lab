import { describe, it, expect } from "vitest";
import { normalizeReplay, wrappedDistance } from "./replay";
import type { Frame, Replay } from "@/lib/types";
const frame = (overrides: Partial<Frame>): Frame => ({
  cells: [],
  entities: {},
  energy: {},
  events: [],
  moves: {},
  ...overrides,
});
describe("H3 replay turn alignment", () => {
  it("uses next-frame ships with this-frame end banks and mineral updates", () => {
    const replay: Replay = {
      production_map: { width: 1, height: 1, grid: [[{ energy: 100 }]] },
      players: [],
      map_generator_seed: 11,
      lab_replay_schema: "halite3-lab-v1",
      GAME_CONSTANTS: {
        VISION_RADIUS: 4,
        FOG_ENABLED: true,
        LIGHT_SHIP_COLLISIONS: true,
        MAX_ENERGY: 1000,
      },
      full_frames: [
        frame({ energy: { "0": 5000 } }),
        frame({
          energy: { "0": 4000 },
          cells: [{ x: 0, y: 0, production: 75 }],
        }),
        frame({
          energy: { "0": 4300 },
          cells: [{ x: 0, y: 0, production: 50 }],
          entities: {
            "0": { "1": { x: 0, y: 0, energy: 25, is_inspired: false } },
          },
        }),
        frame({
          entities: {
            "0": { "1": { x: 0, y: 0, energy: 0, is_inspired: false } },
          },
        }),
      ],
    };
    const result = normalizeReplay(replay);
    expect(result).toHaveLength(3);
    expect(result[1].banks["0"]).toBe(4000);
    expect(result[1].ships["0"]["1"].energy).toBe(25);
    expect(result[1].halite[0]).toBe(75);
    expect(result[2].ships["0"]["1"].energy).toBe(0);
    expect(result[0].halite[0]).toBe(100);
  });
  it("computes toroidal Manhattan distance across boundaries", () => {
    expect(wrappedDistance(0, 0, 31, 31, 32, 32)).toBe(2);
    expect(wrappedDistance(2, 2, 6, 5, 32, 32)).toBe(7);
  });
  it("keeps bounded visibility distances from wrapping at an edge", () => {
    expect(wrappedDistance(0, 0, 31, 31, 32, 32, true)).toBe(62);
    expect(wrappedDistance(2, 2, 6, 5, 32, 32, true)).toBe(7);
  });
});
