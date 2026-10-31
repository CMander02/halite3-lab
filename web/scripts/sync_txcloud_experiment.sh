#!/usr/bin/env bash
set -euo pipefail
app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_dir="${HALITE_DATA_DIR:?Set HALITE_DATA_DIR}"
remote_dir=/home/zychen/Services/halite3-game1/data
spool_dir="$data_dir/remotes/test-1"
mkdir -p "$spool_dir/replays"
exec 9>"$spool_dir/sync.lock"
flock -n 9 || exit 0
ssh -o BatchMode=yes -o ConnectTimeout=15 txcloud "sqlite3 '$remote_dir/arena.sqlite3' \".backup '$remote_dir/snapshot.sqlite3'\""
rsync -a --chmod=F600 -e 'ssh -o BatchMode=yes -o ConnectTimeout=15' "txcloud:$remote_dir/snapshot.sqlite3" "$spool_dir/"
rsync -a --prune-empty-dirs --include='*/' --include='*.json.gz' --exclude='*' --chmod=D700,F600 \
  -e 'ssh -o BatchMode=yes -o ConnectTimeout=15' "txcloud:$remote_dir/replays/" "$spool_dir/replays/"
"$app_dir/.venv/bin/python" "$app_dir/scripts/experiment_transfer.py" import "$spool_dir"
