from pathlib import Path
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import settings as S

os.umask(0o077)
folder = S.DATA / "backups"
folder.mkdir(exist_ok=True)
target = folder / (datetime.now().strftime("%Y-%m-%d") + ".sqlite3")
source = sqlite3.connect(S.DATA / "arena.sqlite3")
destination = sqlite3.connect(target)
source.backup(destination)
destination.close()
source.close()
for old in sorted(folder.glob("*.sqlite3"))[:-7]:
    old.unlink()
print("Database backup saved:", target.name)
