# Halite 3 Lab

This repository owns both the modded C++ engine (`game_engine/`, local tests in `lab/`) and the arena website (`web/`).

- Canonical website: `https://halite3.cmander02.com`; `/halite3` on the main domain redirects there.
- Source: `/home/cmander/Project/halite3-lab`.
- Live state: `/home/cmander/Services/halite3/data/`. Do not commit user uploads, accounts, API tokens, credentials, logs, replays, or compiled bot binaries.
- User preference: bots run as native processes, **without Docker**. Use the existing Bubblewrap + systemd scope launcher, which exposes only that version's files and enforces filesystem, network, CPU, memory and process limits. Never run uploaded code directly as the web server user in the unrestricted host filesystem.
- User submissions and competition entries support C++17 only (`.cpp`, `.cc`, `.cxx`, or C++ ZIP projects). Historical user Python versions stay readable but cannot enter or retry matches, become defaults, or appear on public leaderboards. Only the two immutable platform baselines retain their internal Python runtime. Each user/bot has immutable version directories and a latest pointer. Resolve eligible latest at test submission, then preserve version IDs and source hashes throughout execution.
- The lab observation protocol is JSON Lines. Original H3 text-observation SDKs need adaptation; sample clients live under `web/examples/` and generated sample ZIP downloads.
- Public rankings come from contest #0 (the standing 12-game benchmark: 1v1 against the baseline and raider targets on seeds 11 / 29 / 47, seats swapped) and from published contest finals. Changing #0's setup (map size, turns, rules, seeds, targets) makes old and new scores incomparable, so ask the owner before doing it. Keep arbitrary private tests out of the public Tier List. Public replays must not expose source or private runner logs.
- Live user services: `halite3-web`, `halite3-runner`, `halite3-tunnel`, `halite3-backup.timer`. Configuration is under `/home/cmander/Services/halite3/`; do not print credentials.

## Delivering changes: straight to main, no PRs

The owner's rule (2026-10-26): do not open pull requests or leave work waiting for review. When a change is done and verified, merge it into `main` yourself and deploy it.

1. Work in your own branch or worktree if you like. Before merging, fetch and merge the latest `origin/main`, then resolve any conflicts.
2. Run the verification below on the merged result. Never merge or deploy with failing tests or a failing build.
3. Merge into `main` and `git push origin main`. If other agents' branches or PRs are still open, merging them is part of the same job when the owner asks for it.
4. Deploy from the live checkout `/home/cmander/Project/halite3-lab`, which must stay on `main`:
   - Run `git status` first and don't overwrite anyone's uncommitted work.
   - Back up the database: `sqlite3 "file:$D/arena.sqlite3?mode=ro" ".backup $D/backups/pre-<task>-$(date +%Y%m%d-%H%M%S).sqlite3"` with `D=/home/cmander/Services/halite3/data`.
   - Check for running matches. Restarting the runner interrupts them and requeues them.
   - Run `git pull --ff-only`.
   - If `game_engine/` changed, run `./lab/dev.sh build`.
   - In `web/`, run `npm ci && npm run build`.
   - Run the backend tests with `HALITE_ENGINE=../build/halite`.
   - Run `systemctl --user restart halite3-web halite3-runner`. Restarting only `halite3-web` is enough when the runner, engine and scheduler are untouched.
   - Check `https://halite3.cmander02.com/api/health`.
   Database migrations run at startup and must stay additive, so the previous commit can still run on the new schema.
5. Record the deployment in `~/Server/changes/` (server-change-log skill) and in the local `agentspace/DEPLOY.md`. Include the commit, the backup path and the rollback steps.

Verification:

```bash
./lab/dev.sh test
cd web
npm run build
.venv/bin/python -m unittest discover -s tests -v
```

Keep operations documentation in `~/Server` updated after verified deployments using the server-change-log skill. Read `web/README.md` and current `agentspace/implemented/` notes before changing runtime contracts.
