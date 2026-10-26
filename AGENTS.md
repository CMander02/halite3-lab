# Halite 3 Lab

This repository owns both the modded C++ engine (`game_engine/`, local tests in `lab/`) and the arena website (`web/`).

- Canonical website: `https://halite3.cmander02.com`; `/halite3` on the main domain redirects there.
- Source: `/home/cmander/Project/halite3-lab`.
- Live state: `/home/cmander/Services/halite3/data/`. Do not commit user uploads, accounts, API tokens, credentials, logs, replays, or compiled bot binaries.
- User preference: bots run as native processes, **without Docker**. Use the existing Bubblewrap + systemd scope launcher, which exposes only that version's files and enforces filesystem, network, CPU, memory and process limits. Never run uploaded code directly as the web server user in the unrestricted host filesystem.
- User submissions and competition entries support C++17 only (`.cpp`, `.cc`, `.cxx`, or C++ ZIP projects). Historical user Python versions stay readable but cannot enter or retry matches, become defaults, or appear on public leaderboards. Only the two immutable platform baselines retain their internal Python runtime. Each user/bot has immutable version directories and a latest pointer. Resolve eligible latest at test submission, then preserve version IDs and source hashes throughout execution.
- The lab observation protocol is JSON Lines. Original H3 text-observation SDKs need adaptation; sample clients live under `web/examples/` and generated sample ZIP downloads.
- Public rankings use the fixed 12-game benchmark. Keep arbitrary private tests out of the public Tier List. Public replays must not expose source or private runner logs.
- Live user services: `halite3-web`, `halite3-runner`, `halite3-tunnel`, `halite3-backup.timer`. Configuration is under `/home/cmander/Services/halite3/`; do not print credentials.

Verification:

```bash
./lab/dev.sh test
cd web
npm run build
.venv/bin/python -m unittest discover -s tests -v
```

Keep operations documentation in `~/Server` updated after verified deployments using the server-change-log skill. Read `web/README.md` and current `agentspace/implemented/` notes before changing runtime contracts.
