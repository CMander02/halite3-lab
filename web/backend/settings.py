from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
DATA = Path(os.environ.get("HALITE_DATA_DIR", str(ROOT / "data"))).resolve()
ORIGIN = os.environ.get("HALITE_APP_ORIGIN", "http://127.0.0.1:18383").rstrip("/")
ENGINE = Path(os.environ.get("HALITE_ENGINE", str(PROJECT / "build/halite"))).resolve()
BWRAP = os.environ.get("HALITE_BWRAP", "/usr/local/lib/halite3/bwrap")
CXX = os.environ.get("HALITE_CXX", "/usr/bin/g++")
MAX_UPLOAD = 5 * 1024 * 1024
MAX_UNPACKED = 20 * 1024 * 1024
MAX_USER_UPLOAD = 256 * 1024 * 1024
MAX_MATCHES_PER_DAY = 500
MAX_MATCHES_PER_JOB = 300
MIN_DISK_FREE = int(os.environ.get("HALITE_MIN_DISK_FREE", 8 * 1024**3))
LEASE_SECONDS = 180
MAX_GAME_SECONDS = 100
RETENTION_DAYS = 30
RULES = {
    "LAB_PROTOCOL": True,
    "FOG_ENABLED": True,
    "VISION_RADIUS": 4,
    "REEF_PERCENT": 12,
    "LIGHT_SHIP_COLLISIONS": True,
}
SEASON = "h3-lab1-baseline-set1"
