---
title: 2026-10-31-rule-experiments-on-txcloud
model: GPT-6 (Codex)
effort: high
created: 2026-10-31 20:17:38
last_modified: 2026-10-31 20:17:38
abstract: Freeze eight existing bots and evaluate 28 rule variants in contest 1 on a separate txcloud worker without changing contest 0 or its active queue.
lifecycle: implemented
class: feature
---

# Agent Note: Rule experiments on txcloud

## Problem

CMA-279 asks to test the discussed rules with eight strong existing bots, unchanged source, in a new contest #1. Additional user guidance puts execution on txcloud because the local host is completing another evaluation batch. Experiments with different economies must not change the standing benchmark or global ELO.

## Decision

The catalogue in `backend/experiments.py` defines 28 cases, each with 32 duels, 16 four-player and 32 eight-player games with full seat rotations. Versions come from eight distinct public bots with at least 12 public seat appearances, sorted by raw ELO. Source digests and immutable version IDs are frozen. Both platform baselines participate; their source is unchanged.

Opt-in engine flags implement symmetric map generation, bounded distance/movement, fixed mining/free movement, ship caps, production intervals, loss cooldown, safe friendly spawning, enemy-only pileups and alternating scout/hauler production. Defaults retain #0 behavior. Low-granularity initial ore is capped at 15; collision overflow remains on the ground. Replay and observation extensions preserve type/capacity information.

The remote runner owns an independent sanitized database and only the ten needed source artifacts. It uses native Bubblewrap/systemd isolation. Central matches have remote-prefixed pending states, so the existing local coordinator can remain running and cannot claim them. Per-seed frozen setups bind each match to a case and pair actual map seeds. Result imports verify identity, source/engine digests and configuration before publication, and are idempotent. A systemd timer imports results until completion.

The active local runner and its `build/halite` remain in place. The new engine is built and tested separately; only `build/halite-experiment-1` is installed locally for experimental map downloads. Updating the original engine during a running match could cause its later recorded file digest to identify the wrong binary. This deployment therefore restarts the web service only.

`jobs.rating_scope` defaults to global; experiment jobs use contest scope. Global ELO, the matchup matrix and statistical boards omit them. Contest #1 ranks the combined case by default; the experiments view selects other cases and modes without mixing rules. All eight entries remain eligible even when one account owns multiple bots. Standard contest editing, restart and local job retry/cancel reject this frozen remote experiment.

This extends the [rule diagnostics](2026-10-31-rule-diagnostics.md) and implements experiments motivated in [the discussion](../../../lab/RULE_DISCUSSION.md). Existing diagnostics and leaderboard identity decisions retain their independent scope. The experiment contract is [documented separately](../../../lab/EXPERIMENT_1.md).

## Alternatives considered

- Run on the local coordinator: the user explicitly requests txcloud to keep the active local batch independent.
- Adapt or regenerate the bots: violates the requested source freeze; migration failures are observed outcomes.
- Put changed rules in #0 or global ELO: changes the comparison population. Keep contest-local ratings.
- Use a complete Cartesian product of parameters: grows far beyond the requested first coverage pass. Test the combined case plus named variants with paired tables and a single terrain seed.
- Copy production credentials and the full database remotely: unnecessary for running a fixed public roster. Export disabled-login placeholders and this queue only.

## Consequences

The 2240-game batch continues under systemd after an agent turn. Only the remote native worker executes the new matches. Completed artifacts survive a run ending and can be reimported. The experiment is a one-seed transfer evaluation, not an estimate of optimized strategies under every new rule. Hardcoded economic or topology assumptions may cause no spawning, no delivery or bot termination; these remain visible.

## Testing

Physics tests cover symmetry, budgets, connectivity and determinism; bounded motion/fog; fixed mining/free movement; enemy-only pileups; protected spawning; ship caps, scout metadata, and production/cooldown timing; low-granularity ore and overflow. Backend tests cover coverage, all seats, roster/source freeze, remote queue isolation, global rating exclusion, sanitized export and repeat creation. Browser checks cover case/mode URL state, mobile overflow and console health. Real native matches and matching engine/source hashes are verified on txcloud before handoff; full batch completion is tracked separately.

## Execution-profile update

The [500ms batches](2026-11-01-fast500-experiment-batches.md) preserve the original completed results and add a complete, separately ranked execution under the requested deadline. The map, roster and physics contracts above remain unchanged.
