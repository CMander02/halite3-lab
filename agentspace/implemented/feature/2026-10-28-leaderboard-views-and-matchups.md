---
title: 2026-10-28-leaderboard-views-and-matchups
model: GPT-6 (Codex)
effort: high
created: 2026-10-28 09:25:52
last_modified: 2026-10-28 09:25:52
abstract: Shareable leaderboard views, compact identities and observed public head-to-head comparisons.
lifecycle: implemented
class: feature
---

# Agent Note: Leaderboard views and matchups

## Problem

Leaderboard tabs and filters reset on reload and cannot be shared. Long Tier labels do not fit compact cards, and no public table exposes how each rated version performed against another version.

## Decision

`/leaderboard?view=elo|tier|matrix|kda|robbed|delivered|vision|mined` selects a controlled tab. `mode=2|4|8` selects the matrix/statistics population. `model`, `effort`, and `harness` preserve ELO filters. Existing `tierlist=ELO` and `tierlist=Tier` links are read as aliases and canonicalized on interaction. The site map offers direct links to every view and all matrix modes; homepage Tier/KDA/robbery links open the corresponding view. All state is derived from the existing router, so reload, direct navigation, browser back and forward restore it. Invalid views/modes fall back to defaults, and changing one control retains other query parameters.

Tier cards have bounded width, user and Bot icons, ellipsis, full author/version tooltips and accessible labels. Bot identities reuse the established model mark or deterministic pixel sprite. The Tier API adds `bot_id` and respects listed/archived visibility.

`GET /api/leaderboard/matrix?mode=2|4|8` returns the public ELO roster plus sparse comparison cells. Identity metadata comes only from eligible, listed, unarchived public rated versions and platform baselines. The roster stays fixed across mode filters; missing cells mean no observed comparison, never an estimated 50%. Each pair of different-version seats in a completed public match contributes a comparison. Row rate is `(wins + draws / 2) / comparisons`; reverse cells complement it. Repeated seats count separately and self comparisons are omitted. ELO priors, model corrections, private tests, failed matches, and unpublished finals do not contribute. The API sends no private attribution declarations, detection or source data.

The UI renders a scrollable table with sticky row/column headers, explicit row-to-column direction, comparison counts and rate legend. Clickable cells expose full identities and wins/draws/losses for touch and keyboard access. Matrix data is fetched only when its tab is active.

The existing [C++ participation policy](../bug-fix/2026-10-26-cpp-only-competition.md) remains authoritative for eligibility. This extends its public leaderboard visibility contract.

## Alternatives considered

- Local tab state: loses reload/share/back navigation state, the reported problem.
- Bot-wide aggregation: mixes immutable versions with different behavior; existing ELO and Tier already use versions.
- Predicted ELO probabilities for empty cells: do not answer the request for observed matchup performance.
- First-place rate for multiplayer pairs: does not measure whether the row version ranked ahead of the column version. Pairwise final ranks preserve that direction.

## Consequences

Many versions require horizontal/vertical scrolling; sticky headers retain identities. Sparse public coverage remains explicit, including versions with no results in a selected mode. Counts are seat comparisons rather than distinct matches when opponents repeat in one match. No schema, benchmark, ELO fitting or scheduler change is needed.

## Testing

Backend regression coverage checks row direction, ties, repeated seats, missing cells, mode filters, public-only inclusion, hidden/archived/legacy-language exclusions and invalid mode rejection. URL tests cover defaults, aliases, preserved filters and encoding. Browser QA covers direct links, reload/back/forward, full-name tooltips, long labels, mobile overflow, matrix details and console health.
