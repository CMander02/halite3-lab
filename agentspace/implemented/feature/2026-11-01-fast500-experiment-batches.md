---
title: 2026-11-01-fast500-experiment-batches
model: GPT-6 Codex
effort: high
created: 2026-11-01 15:54:00
last_modified: 2026-11-01 16:05:50
abstract: Preserve the completed 2-second experiment and run a complete 500ms batch under measured host budgets.
lifecycle: implemented
class: feature
---

# Agent Note: 500ms experiment batches

## Problem

The user requests a uniform 500ms response limit and higher utilization of txcloud, while keeping already completed tests intact. Mixing partial 2s/35%-CPU results with 500ms/100%-CPU results would obscure the execution conditions and leave the remaining schedule with incomplete mode/seat coverage.

## Decision

Archive the drained original batch, preserve all 902 completed match rows and their artifacts, and stop only its unexecuted games. Start a new complete 28×80 schedule using the exact frozen seats, source hashes, map seeds and physical rules. The active and archived jobs share contest #1 and have separate rankings and progress, selectable through URL state. The active job remains excluded from global ratings.

The engine gains an optional response-deadline argument; its default remains 2000ms. Runner results and public match metadata expose timeout, CPU quota and batch identity. The importer validates the execution profile as well as the existing frozen identities and physics. The explicit remote transition/adoption commands are idempotent and reject running or inconsistent legacy states. Native sandbox defaults remain unchanged; the new job opts into 100% CPU per bot and a shared host slice. The host budget and concurrency are selected using real frozen fixtures with terminated-bot and result-equivalence checks. Two workers use distinct inherited CPU affinities (0/1), with sixteen seat reservations; the pinned mixed and double-8p stress fixtures preserve results without termination. Unpinned 3/4 workers and double-8p runs exceed response deadlines and are rejected.

This extends the [original experiment feature](2026-10-31-rule-experiments-on-txcloud.md); its map and physics decisions remain in force. The execution-profile change supersedes the original single-batch assumption.

## Alternatives considered

- Change completed results or their engine hashes: breaks provenance and the user's preservation requirement.
- Only finish the old partial schedule at a different deadline: leaves the new condition without a full 80-game coverage per rule variant.
- Attribute a fourfold gain solely to the shorter deadline: normal replies already advance immediately; measure CPU and concurrency gains instead.
- Pick concurrency using elapsed time alone: early bot termination can make overloaded runs appear faster. Require equivalent outcomes without bot termination.

## Consequences

Old artifacts remain inspectable. The new batch repeats games under a single execution profile; its total is 2240. Historical and active rankings stay separate. The live local supplemental runner and its original engine file are preserved. Operational backups, host measurements, chosen concurrency and rollback handles are maintained in Server records and the deployment log. The full batch continues under systemd and the existing Multica wakeup.

## Testing

The 500ms engine test rejects a 650ms reply while the default deadline allows it. Lab checks cover all physics; backend tests cover immutable completed rows, idempotence, complete schedule cloning, central adoption, separate rankings and local-claim isolation. Frontend build/tests and browser validation cover batch selection and public limits. Remote 1/2/3/4-process fixtures use identical sources, rules, maps and outputs, record host CPU and memory, and reject settings with bot termination or result drift.
