export interface User {
  id: string;
  username: string;
  display_name: string;
}
export interface Version {
  id: string;
  language: "python" | "cpp";
  version: string;
  sha256: string;
  filename: string;
  size: number;
  notes: string;
  created_at: number;
}
export interface Bot {
  id: string;
  name: string;
  description: string;
  builtin: number;
  owned: boolean;
  author: string | null;
  versions: Version[];
  created_at: number;
}
export interface Seat {
  id: string;
  name: string;
  version: string;
  sha256: string;
  author: string | null;
  builtin: number;
  bot_id: string;
  filename: string;
}
export interface MatchResult {
  stats: Record<string, { rank: number; score: number }>;
  terminated: Record<string, boolean>;
  turns: number;
  engine_sha256: string;
}
export interface Match {
  id: string;
  job_id: string;
  job_name: string;
  kind: string;
  mode: number;
  seed: number;
  seats: Seat[];
  status: string;
  attempts: number;
  error: string | null;
  result: MatchResult | null;
  has_replay: boolean;
  created_at: number;
  finished_at: number | null;
  can_view_logs?: boolean;
  attempt_history?: { number: number; status: string; error: string | null }[];
}
export interface Job {
  id: string;
  name: string;
  kind: string;
  status: string;
  created_at: number;
  total: number;
  counts: Record<string, number>;
  matches?: Match[];
  config: { modes: number[]; seeds: number[]; rotate_seats: boolean };
}
export interface Health {
  ok: boolean;
  runner_online: boolean;
  upload_limit: number;
  retention_days: number;
}
export interface LeaderEntry {
  version_id: string;
  bot_name: string;
  version: string;
  author: string;
  games: number;
  wins: number;
  win_rate: number;
  mean_score: number;
  tier: string;
  job_id: string;
}
export interface Ship {
  x: number;
  y: number;
  energy: number;
  is_inspired: boolean;
}
export interface ReplayEvent {
  type: string;
  location: { x: number; y: number };
  owner_id?: number;
  ships?: number[];
}
export interface Frame {
  cells: { x: number; y: number; production: number }[];
  entities: Record<string, Record<string, Ship>>;
  energy: Record<string, number>;
  events: ReplayEvent[];
  moves: Record<string, unknown>;
}
export interface Replay {
  production_map: {
    width: number;
    height: number;
    grid: { energy: number; reef?: boolean }[][];
  };
  full_frames: Frame[];
  players: {
    player_id: number;
    name: string;
    factory_location: { x: number; y: number };
  }[];
  GAME_CONSTANTS: {
    VISION_RADIUS: number;
    FOG_ENABLED: boolean;
    LIGHT_SHIP_COLLISIONS: boolean;
    MAX_ENERGY: number;
  };
  map_generator_seed: number;
  lab_replay_schema: string;
}
