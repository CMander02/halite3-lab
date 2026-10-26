---
title: 2026-10-26-cpp-only-competition
model: GPT-6 (Codex)
effort: high
created: 2026-10-26 05:29:50
last_modified: 2026-10-26 05:29:50
abstract: Restrict user uploads and competition entries to C++17 while retaining historical records and immutable benchmark opponents.
lifecycle: implemented
class: bug-fix
---

# Agent Note: C++17 competition entries

## Problem

CMA-259 requires C++ submissions and participation throughout the arena. Removing the Python upload option alone leaves direct API uploads, Python ZIP detection, stored versions, default pointers, retries, queued matches, and compiled-cache reuse available.

## Decision

Public upload validation accepts UTF-8 `.cpp`, `.cc`, `.cxx`, and ZIP projects with actual C++ compilation units. Python source and bytecode files in ZIPs are rejected, including mixed projects. Existing archive size, path, symlink, encryption, and compilation-unit limits remain. All compilation units use explicit C++17 language selection, including uppercase extensions.

The scheduler checks eligibility before creating private or ranked jobs, even when a ranked job already exists. Automatic bot resolution skips non-C++ versions and stale Python defaults. Retry checks are transactional. The runner checks stored version metadata before launching any participant; the builder checks eligibility before reading a cached runtime. Unsupported queued matches finish with a deterministic failure and cannot be retried.

Only the two ownerless, explicitly identified platform versions `builtin-baseline-v1` and `builtin-raider-v1` retain their internal Python execution path. Their source, hashes, version IDs, and the benchmark season remain unchanged. Users cannot upload or modify those versions. This preserves the benchmark contract documented in [the arena README](../../../web/README.md).

Historical user Python sources, traces, results, and raw ELO remain available to their existing readers. These versions cannot be defaults or enter new matches; they receive no public rank and are excluded from the Tier List, ELO board, and statistics boards. The API exposes eligibility to the Bot, submission, admin, and test interfaces. Python starter links and generated archives are removed, and the old URL returns 404 even when an old archive remains on disk.

The existing fog/terrain/resumable-arena note concerns the local lab and game rules; this policy does not supersede it. Local `lab/` fixtures and the backend/CLI implementation may still use Python.

## Alternatives considered

- Only remove frontend Python options: direct API requests and historical-version entry points still permit Python participation.
- Replace the internal benchmark opponents with C++ implementations: changing their immutable source would change the existing benchmark and require a separate version/season decision.
- Delete historical Python versions: retaining read access preserves users' sources and results while eligibility checks prevent further participation.

## Consequences

Users with only Python versions must upload a new C++17 version. Historical queued Python matches fail once with a language-policy explanation. No source, replay, or account migration is required. The change is delivered for review; production deployment is separate.

## Testing

The backend suite covers rejected Python and mixed archives, accepted C++ extensions/projects, direct entry points, legacy defaults and caches, retry restrictions, leaderboard filtering, and retained history. Real sandboxed matches cover a single-file C++ example against baseline and a multi-unit C++ ZIP against raider. Browser checks cover upload rejection/success, legacy controls, test selection, account examples, admin visibility, match/replay pages, and desktop/mobile layouts.
