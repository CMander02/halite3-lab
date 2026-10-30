---
title: 2026-10-30-bounded-native-match-workers
model: Codex
effort: high
created: 2026-10-30 06:59:52
last_modified: 2026-10-30 06:59:52
abstract: One locked coordinator owns a bounded native-process match pool, transactional seat admission and lease-protected result publication.
lifecycle: implemented
class: architecture
---

# Agent Note: Bounded native match workers

## Problem

CMA-276 observed 1,242 unfinished games on 2026-10-29. At the start of CMA-278 on 2026-10-30, all 7,486 games were complete and no matches were queued or running. The production runner still admitted only one game globally, so future batch submissions would face the same serialization.

## Decision

Keep one coordinator holding the data directory's advisory lock. Spawn independent Python worker processes for matches, with default one worker and eight seats. Environment configuration permits one to four workers and eight to sixteen seats. The initial deployment enables two workers and eight seats. Eight-player games therefore execute alone; two four-player or two duel games may overlap.

Admission reads both running count and summed seats under `BEGIN IMMEDIATE`, retaining immutable job configuration, version snapshots, source digests, seed and seats. The coordinator reserves seats until a worker exits and its sandboxes are stopped, including the interval after result publication. Select the head of the existing per-user fair queue before applying the seat budget, so an eight-seat match cannot starve behind newly arriving duels.

Workers do not initialize the database, run contest ticks, delete old replays, or perform global scope cleanup. Only the coordinator does those operations. Scope names include a digest of the absolute data directory, so isolated test arenas cannot stop production sandboxes. Each bot scope also includes the full match ID and attempt. A worker stops only its own match's scopes.

The coordinator renews live worker leases every four seconds, including during cold builds. A cross-process file lock serializes all cold compilation and cache publication; waiting for the lock and compilation are cancellable. Build metadata is written before the runtime directory is renamed into place, so a crash between these steps leaves a safely rebuildable version. Failures due to stopping the runner are retryable and do not poison the immutable build-error cache. Successful and failed match publication checks current lease ownership in a write transaction before changing replay, current logs, attempt state or analytics. Temporary replay files are unique to the lease token.

Worker parent-death handling requests graceful stop when the coordinator disappears. Engine parent-death handling uses SIGKILL. After a child exits, the coordinator stops that match's sandboxes before recovering its lease; completed matches are untouched. On restart, under the singleton lock, the coordinator clears only its namespaced sandboxes and expires outstanding leases for whole-match recovery.

## Alternatives considered

- Launch multiple independent coordinators: rejected because of singleton initialization, shared cache publication and global queue ownership. Removing the lock alone leaves races and the original single-match admission check.
- Wrap the current runner in threads: rejected because engine limits use `preexec_fn`; independent workers keep subprocess setup outside a threaded process.
- Admit smaller matches ahead of an eight-player queue head: rejected because sustained small submissions could starve large games.
- Change map, targets, timeouts or bot CPU limits: rejected because existing evaluation results must remain comparable. All benchmark fixtures use existing mode setups and sandbox limits.
- A remote execution node: deferred. The current implementation depends on a local SQLite database and local immutable version directories; this change does not introduce network task transport.

## Consequences

The deployment drop-in raises coordinator aggregate CPU quota from 80% to 160%, memory from 640 MiB to 1 GiB, task limit to 256 and stop timeout to 120 seconds. Independent bot scopes retain 35% single-core CPU, 192 MiB memory and existing mode runtime limits. A seat budget bounds concurrent upper limits but does not guarantee sufficient capacity on every host. More workers require a fresh capacity measurement.

Stopping or restarting the service interrupts active games and consumes their existing retry budget. Worker crashes affect only the failed worker's match; coordinator failure can interrupt all its active games. No schema migration is needed. Removing the drop-in and restarting restores single-worker execution while retaining results and the new recovery implementation.

Source contracts and repeatable isolated performance measurement are documented in [web/README.md](../../../web/README.md). The single-machine lab arena remains a separate tool; its historical architecture note is retained locally. The CMA-276 ETA evidence remains historical and does not describe the current queue.

## Testing

`web/tests/test_runner.py` covers simultaneous process claims, fair ordering, worker and seat limits, seat reservations during cleanup, shared cold C++ builds, coordinator lease renewal, isolated worker recovery, and rejection of stale success/failure publication. `web/scripts/benchmark_runner.py` compares the same six frozen duel/four/eight-player fixtures in fresh serial and parallel arenas, checks deterministic results, first-attempt completion, bot termination flags and production health response, and samples aggregate coordinator plus bot scope memory.

Deployment measurements and forced worker/coordinator crash checks are recorded in the CMA-278 delivery and operator change log. Sampling does not establish a maximum resource bound for all submitted bots.
