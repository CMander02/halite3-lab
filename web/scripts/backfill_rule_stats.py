"""Idempotent offline backfill; commit one replay at a time to keep locks short."""
import argparse
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import rule_analytics as rules, settings as S
from backend.db import connect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=10000)
    args = parser.parse_args()
    with connect() as db:
        rules.migrate(db)
        rows = db.execute('''SELECT m.id,m.replay_key FROM matches m
            LEFT JOIN match_rule_stats s ON s.match_id=m.id AND s.schema_version=?
            WHERE m.public=1 AND m.status='complete' AND m.replay_key IS NOT NULL
            AND s.match_id IS NULL ORDER BY m.finished_at DESC LIMIT ?''', (rules.SCHEMA, args.limit)).fetchall()
    errors = 0
    for i, row in enumerate(rows, 1):
        try:
            with gzip.open(S.DATA / row['replay_key'], 'rt', encoding='utf-8') as stream:
                value = rules.analyze(json.load(stream))
            with connect() as db:
                db.execute('INSERT OR REPLACE INTO match_rule_stats VALUES(?,?,?)',
                           (row['id'], rules.SCHEMA, json.dumps(value, separators=(',', ':'))))
        except Exception as error:
            errors += 1
            print(row['id'], type(error).__name__, str(error), flush=True)
        if i % 100 == 0:
            print(f'{i}/{len(rows)} processed; errors={errors}', flush=True)
    print(f'Finished {len(rows)} replays; errors={errors}', flush=True)
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
