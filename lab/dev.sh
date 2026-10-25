#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
if ! docker image inspect halite3-lab-dev >/dev/null 2>&1; then
  docker build -t halite3-lab-dev -f lab/Dockerfile .
fi
case "${1:-}" in
  build)
    docker run --rm --init --user "$(id -u):$(id -g)" -v "$project_root:/workspace" -w /workspace halite3-lab-dev sh -c 'cmake -S game_engine -B build -DHALITE_SYSTEM_DEPS=ON -DCMAKE_BUILD_TYPE=Release && cmake --build build -j 4'
    ;;
  test)
    docker run --rm --init --user "$(id -u):$(id -g)" -v "$project_root:/workspace" -w /workspace halite3-lab-dev sh -c 'ctest --test-dir build --output-on-failure && python3 -m unittest discover -s lab/tests -v'
    ;;
  arena)
    shift
    # Preserve absolute replay paths so host and container can inspect the same run.
    docker run --rm --init --user "$(id -u):$(id -g)" -v "$project_root:$project_root" -w "$project_root" halite3-lab-dev python3 lab/arena.py "$@"
    ;;
  *)
    echo 'Usage: lab/dev.sh build | test | arena <plan|run|status> ...' >&2
    exit 2
    ;;
esac
