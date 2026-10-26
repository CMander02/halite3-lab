export interface User {
  id: string;
  username: string;
  display_name: string;
  avatar_version?: number;
  is_admin?: boolean;
}
export interface Profile extends User {
  avatar_version: number;
  has_custom_avatar: boolean;
  created_at: number;
  bots: number;
  versions: number;
  stats: { games: number; wins: number; kills: number; deaths: number; robbed: number; delivered: number };
}
export interface PlayerStats {
  seat: number;
  version_id: string;
  author_id: string | null;
  rank: number;
  score: number;
  kills: number;
  deaths: number;
  assists: number;
  robbed: number;
  lost: number;
  delivered: number;
  mined: number;
  territory: number;
  ships_built: number;
  dropoffs: number;
}
export interface BoardEntry {
  version_id: string;
  version: string;
  bot_name: string;
  builtin: number;
  author: string | null;
  author_id: string | null;
  games: number;
  wins: number;
  win_rate: number;
  avg_rank: number;
  score: number;
  kills: number;
  deaths: number;
  assists: number;
  kda: number;
  robbed: number;
  robbed_per_game: number;
  lost: number;
  delivered: number;
  mined: number;
  territory: number;
  ships_built: number;
}
export interface Summary {
  users: number;
  bots: number;
  versions: number;
  matches: number;
  pending: number;
  wrecks: number;
  delivered: number;
  daily: { day: number; matches: number }[];
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
  listed?: number;
  archived?: number;
  declared_model?: string | null;
  declared_effort?: string | null;
  declared_harness?: string | null;
  has_trace?: number;
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
  default_version_id?: string | null;
  /** Model behind the default version (admin > confident detection > declared), for the bot icon. */
  model?: string | null;
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
  author_id?: string | null;
  language?: string;
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
  players?: PlayerStats[];
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
  author_id: string | null;
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
    PILEUP_WRECK_SIZE?: number;
    MAX_ENERGY: number;
  };
  map_generator_seed: number;
  lab_replay_schema: string;
}
export type CatalogKind = "model" | "effort" | "harness";
export interface CatalogEntry {
  id: string;
  name: string;
  vendor: string;
  region: "cn" | "us" | "other" | "";
  icon: string;
  elo_offset: number;
  sort: number;
  enabled: boolean;
  patterns?: string[];
}
export type Catalog = Record<CatalogKind, CatalogEntry[]>;
export interface AttributionPart {
  declared: string;
  detected: string;
  value: string;
  source: "declared" | "detected" | "admin";
  offset: number;
}
export interface Attribution {
  model: AttributionPart;
  effort: AttributionPart;
  harness: AttributionPart;
  correction: number;
  mismatch: CatalogKind[];
}
export interface Detection {
  model: string;
  model_confidence: string;
  models: Record<string, number>;
  effort: string;
  effort_confidence: string;
  harness: string;
  harness_confidence: string;
  format: string;
  records: number;
  messages: number;
  output_tokens: number;
  started_at: number | null;
  ended_at: number | null;
  duration_seconds: number | null;
  evidence: string[];
}
export interface EloStats {
  elo: number;
  elo_sd: number;
  adjusted_elo: number;
  correction: number;
  rank: number | null;
  games: number;
  wins: number;
  win_rate: number;
}
export interface RankedStatus {
  job_id: string;
  counts: Record<string, number>;
  total: number;
  complete: number;
  tier: string | null;
  wins?: number;
  win_rate?: number;
}
export interface Submission {
  id: string;
  bot_id: string;
  bot_name: string;
  version: string;
  language: string;
  filename: string;
  size: number;
  sha256: string;
  notes: string;
  created_at: number;
  listed: boolean;
  archived: boolean;
  is_default: boolean;
  author: string | null;
  author_id: string | null;
  username: string | null;
  trace: { filename: string; size: number; sha256: string } | null;
  detection: Detection | null;
  attribution: Attribution;
  ranked: RankedStatus | null;
  elo: EloStats | null;
  admin_note?: string;
}
export interface EloEntry extends EloStats {
  version_id: string;
  bot_id: string;
  bot_name: string;
  version: string;
  author: string | null;
  author_id: string | null;
  username: string | null;
  builtin: number;
  listed: boolean;
  avg_rank: number;
  attribution: { model: { value: string; offset: number; source: string }; effort: { value: string; offset: number; source: string }; harness: { value: string; offset: number; source: string }; correction: number; mismatch: string[] } | null;
}
export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  created_at: number;
  is_admin: boolean;
  disabled_at: number | null;
  avatar_version: number;
  bots: number;
  versions: number;
  matches: number;
  last_login: number | null;
  sessions: number;
  tokens: number;
}
export type ContestStatus = "draft" | "upcoming" | "open" | "closed" | "finished";
export interface ContestBot {
  version_id: string;
  bot_name: string;
  version: string;
  language: string;
  author: string | null;
  builtin: boolean;
  downloadable: boolean;
  notes: string;
}
export interface ContestMap {
  width: number;
  height: number;
  turns: number;
  seconds: number;
  rules: Record<string, number | boolean>;
  public: number[];
  /** Seeds are revealed to players once the results are published. */
  hidden: number[] | null;
  hidden_count: number;
}
export interface ContestConfig {
  modes: number[];
  public_maps: Record<string, number[]>;
  hidden_maps: Record<string, number[]>;
  targets: string[];
  base_version_id: string | null;
  downloads: string[];
  languages: string[];
  max_submissions: number;
  bench_rotate: boolean;
  final_rounds: number;
  auto_final: boolean;
}
export interface Progress {
  counts: Record<string, number>;
  total: number;
}
export interface ContestSummary {
  id: string;
  number: number;
  /** Contest #0: the standing test contest (no deadline, no final round). */
  practice: boolean;
  slug: string;
  title: string;
  summary: string;
  status: ContestStatus;
  visible_at: number | null;
  open_at: number;
  close_at: number;
  published: boolean;
  final_started_at: number | null;
  finalized_at: number | null;
  modes: number[];
  participants: number;
  submissions: number;
  max_submissions: number;
  languages: string[];
  my_submissions?: number;
}
export interface Contest extends ContestSummary {
  description: string;
  /** Written rules generated from the frozen configuration plus the admin's extra rules (Markdown). */
  rules_text: string;
  /** The problem prompt handed to agents (Markdown). */
  prompt_text: string;
  /** Admin only: the raw prompt / extra rules fields. */
  prompt?: string;
  rules?: string;
  maps: Record<string, ContestMap>;
  targets: ContestBot[];
  base: ContestBot | null;
  downloads: ContestBot[];
  bench_rotate: boolean;
  final_rounds: number;
  auto_final: boolean;
  bench_games: number;
  progress: { bench: Progress; final: Progress };
  config?: ContestConfig;
  final_games_estimate?: number;
}
export interface StandingRow {
  version_id: string;
  bot_id: string;
  bot_name: string;
  version: string;
  language: string;
  target: boolean;
  entry_id: string | null;
  seq: number | null;
  user_id: string | null;
  author: string | null;
  current: boolean;
  rank: number | null;
  games: number;
  wins: number;
  win_rate: number;
  avg_rank: number;
  mean_score: number;
  elo: number;
  elo_sd: number;
  correction: number;
  adjusted_elo: number;
  attribution: EloEntry["attribution"];
  versus: Record<string, { score: number; games: number }>;
  hidden: { wins: number; games: number } | null;
}
export type Standings = Record<string, StandingRow[]>;
export interface ContestEntry {
  id: string;
  seq: number;
  version_id: string;
  bot_id: string;
  bot_name: string;
  version: string;
  language: string;
  note: string;
  picked: boolean;
  current: boolean;
  created_at: number;
  job_id: string | null;
  counts: Record<string, number>;
  total: number;
  stats: Record<string, StandingRow | null>;
  final?: Record<string, StandingRow | null>;
}
export interface BotProfileVersion {
  id: string;
  version: string;
  language: string;
  notes: string;
  created_at: number;
  archived: boolean;
  listed: boolean;
  is_default: boolean;
  attribution: EloEntry["attribution"];
  ranked: RankedStatus | null;
  elo: (EloStats & { avg_rank: number }) | null;
  contests: {
    contest_id: string;
    slug: string;
    title: string;
    status: ContestStatus;
    seq: number;
    created_at: number;
    current: boolean;
    bench: { elo: number; adjusted_elo: number; games: number; win_rate: number; rank: number | null } | null;
    final: { elo: number; adjusted_elo: number; games: number; win_rate: number; rank: number | null } | null;
  }[];
}
export interface BotProfile {
  bot: {
    id: string;
    name: string;
    description: string;
    builtin: boolean;
    author: string | null;
    author_id: string | null;
    username: string | null;
    created_at: number;
    owned: boolean;
    default_version_id: string | null;
  };
  versions: BotProfileVersion[];
}
