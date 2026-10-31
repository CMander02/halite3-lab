from pathlib import Path
import hashlib
import os

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
DATA = Path(os.environ.get("HALITE_DATA_DIR", str(ROOT / "data"))).resolve()
ORIGIN = os.environ.get("HALITE_APP_ORIGIN", "http://127.0.0.1:18383").rstrip("/")
ENGINE = Path(os.environ.get("HALITE_ENGINE", str(PROJECT / "build/halite"))).resolve()
EXPERIMENT_ENGINE = Path(os.environ.get('HALITE_EXPERIMENT_ENGINE', str(PROJECT / 'build/halite-experiment-1'))).resolve()
BWRAP = os.environ.get("HALITE_BWRAP", "/usr/local/lib/halite3/bwrap")
CXX = os.environ.get("HALITE_CXX", "/usr/bin/g++")
MAX_UPLOAD = 5 * 1024 * 1024
MAX_TRACE = 16 * 1024 * 1024
# The agent trace is optional: it only pins down the model / effort behind a version.
REQUIRE_TRACE = os.environ.get("HALITE_REQUIRE_TRACE", "0") == "1"
ADMIN_USERNAME = os.environ.get("HALITE_ADMIN", "cmander").lower()
MAX_UNPACKED = 20 * 1024 * 1024
MAX_USER_UPLOAD = 256 * 1024 * 1024
MAX_MATCHES_PER_DAY = 500
MAX_MATCHES_PER_JOB = 300
# The admin has no usage quotas; this only stops a mistyped test from enqueueing millions of games.
ADMIN_MAX_MATCHES_PER_JOB = 20000
MIN_DISK_FREE = int(os.environ.get("HALITE_MIN_DISK_FREE", 8 * 1024**3))
LEASE_SECONDS = 180
# Opt in after measuring the host. Eight-player matches reserve all eight seats.
RUNNER_WORKERS = int(os.environ.get("HALITE_RUNNER_WORKERS", "1"))
RUNNER_SEATS = int(os.environ.get("HALITE_RUNNER_SEATS", "8"))
if not 1 <= RUNNER_WORKERS <= 4 or not 8 <= RUNNER_SEATS <= 16:
    raise ValueError("Runner limits require 1..4 workers and 8..16 seats")
MAX_GAME_SECONDS = 100
RETENTION_DAYS = 30
RULES = {
    "LAB_PROTOCOL": True,
    "FOG_ENABLED": True,
    "VISION_RADIUS": 4,
    "REEF_PERCENT": 12,
    "LIGHT_SHIP_COLLISIONS": True,
}
# Four-player games use a larger mirrored map and wreck every ship in 3+ ship pileups
# (lab/config/rules-ffa4.json). Python bots on 48x48 need about 135 s in the sandbox.
FFA4_RULES = {**RULES, "PILEUP_WRECK_SIZE": 3, "MIRROR_REEFS": True}
MODE_SETUPS = {
    2: {"width": 32, "height": 32, "turns": 200, "rules": RULES, "seconds": MAX_GAME_SECONDS},
    4: {"width": 48, "height": 48, "turns": 300, "rules": FFA4_RULES, "seconds": 240},
    8: {"width": 32, "height": 32, "turns": 200, "rules": RULES, "seconds": MAX_GAME_SECONDS},
}
SEASON = "h3-lab1-baseline-set1"


def scope_prefix(kind):
    # Separate test arenas and the live service even when sharing a user bus.
    namespace = hashlib.sha256(str(DATA).encode()).hexdigest()[:12]
    return f"halite3-{kind}-{namespace}"
