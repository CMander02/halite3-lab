---
title: 2026-10-31-rule-diagnostics
model: GPT-6 (Codex)
effort: high
created: 2026-10-31 09:40:00
last_modified: 2026-10-31 09:40:00
abstract: Versioned replay diagnostics distinguish collision events, participating ships, cargo timing and residual map resources without changing the benchmark.
lifecycle: implemented
class: feature
---

# Agent Note: Rule diagnostics

## Problem

CMA-279 needs observed high-strength collisions and resource use to inform map and economy discussion. Existing per-version KDA/loot boards do not distinguish spawn collisions, post-movement cargo, event counts and participant counts. Loading thousands of replays in an HTTP request would block delivery.

## Decision

`backend/rule_analytics.py` reconstructs movement from source-cell energy, inspired costs and actual moves. It processes confirmed construction, shipwreck and spawn events in order, including friendly deposits before spawning. Its independent versioned `match_rule_stats` JSON summaries are written alongside existing match statistics. Additive migration creates the table; historical replay processing is explicit through `scripts/backfill_rule_stats.py`, one replay per transaction. Startup and GET never scan the historical replay corpus for this new feature.

`/api/leaderboard/rules?mode=2|4|8&group=all|top` aggregates public complete matches only when every participating version is public/eligible/unarchived on the existing rating board. Excluding a whole match avoids leaking hidden-version resources through whole-map totals. The top group is the raw-ELO top quartile among non-builtin versions with at least 12 public seat appearances, with boundary ties included. It contains those versions' seats and their collisions with any opponents. Whole-map resource ratios describe matches involving those versions. It is an ex-post descriptive cohort, not an all-expert table or a causal comparison.

Event outcomes and seat counters preserve their separate denominators; same-owner and enemy collisions are separate, including outcome breakdowns for both; unknown reconstructions are explicit. The initial corpus reveals 2024 same-owner pileups in 1328 top-participant four-player games, while enemy pileups are zero, making that distinction material. Cargo histograms use start-of-turn ship states and exclude the final snapshot. Rule configurations stay separate. The old KDA and robbery calculations are unchanged.

`/leaderboard?view=rules&mode=8&group=top` restores all controls from the URL and fetches new diagnostics only while the tab is active. It reuses the existing chart components; the site map includes the new view. A supersession search found local notes on shareable leaderboard views and engine rules; they retain their independent decisions and are not superseded by this addition.

## Alternatives considered

- Replay parsing in each API request: duplicates historical work and competes with serving the site. Store summaries and aggregate them.
- Infer intentional attacks from movement: successful movement into a collision does not establish intent. Report observable movement only.
- Use adjusted ELO for strategy strength: model corrections deliberately change standings. Use raw strength for this descriptive cohort.
- Change #0 maps/economy immediately: breaks the published benchmark comparison. Record independent experiments in [the rule discussion](../../../lab/RULE_DISCUSSION.md).

## Consequences

New matches gain a replay-analysis pass; the runner must restart when deploying this module. Backfill coverage is explicit. Summary schema changes require a version bump and controlled backfill. The ranking cohort changes with public results and visibility; discussion figures are a dated snapshot. Map leftovers include recycled collision cargo and cannot measure depletion of original ore. No new rules, rankings, quotas, or scheduler configuration are enabled.

## Testing

Regression fixtures cover post-cost empty ships, ties and pileups, same-owner spawn collisions after deposit, blocked/insufficient moves, unknown events, privacy, mode/config separation, raw ELO selection, minimum games and idempotence. The 2026-10-31 analysis processed all 2739 public replays in a consistent snapshot with zero errors and zero unknown collision events; visibility filters retained 2725 matches. UI checks cover desktop/mobile, direct links, mode/group controls, history, tooltips and chart presence. Public findings and experiment proposals are in the rule discussion; source replays, private database and credentials are excluded from Git.
