"""ELO from public matches plus the per-version model / effort / harness correction.

Raw ELO is a Bradley-Terry maximum-likelihood fit over every complete public
match (each pair of seats is one comparison, weighted 1/(n-1) so a match of any
size counts the same). Every version also plays one virtual win and one virtual
loss against a fixed 1500 anchor, which keeps unbeaten or winless versions
finite and makes the scale stable; the result does not depend on match order.
"""
import json
import math
import threading
from . import catalog as C
from .catalog import UNKNOWN

ANCHOR = 1500.0
PRIOR_GAMES = 1.0
_cache = {"key": None, "value": None}
_lock = threading.Lock()


def attribution(row, catalog):
    """Effective model / effort / harness for a version row.

    Admin override wins. Otherwise the declaration is used, except that a
    confident detection (medium or high) of a setup with a *larger* correction
    replaces it, so under-declaring cannot earn points.
    """
    detection = json.loads(row["detection_json"]) if row["detection_json"] else {}
    result, flags = {}, []
    for kind in C.KINDS:
        declared = row[f"declared_{kind}"] or UNKNOWN
        detected = detection.get(kind) or UNKNOWN
        confident = detection.get(f"{kind}_confidence") in ("medium", "high")
        override = row[f"admin_{kind}"]
        if override:
            value, source = override, "admin"
        elif confident and detected != UNKNOWN and detected != declared:
            stronger = C.offset(catalog, kind, detected) > C.offset(catalog, kind, declared)
            value, source = (detected, "detected") if stronger or declared == UNKNOWN else (declared, "declared")
        else:
            value, source = declared, "declared"
        if confident and detected != UNKNOWN and declared != UNKNOWN and detected != declared:
            flags.append(kind)
        result[kind] = {"declared": declared, "detected": detected, "value": value, "source": source,
                        "offset": C.offset(catalog, kind, value)}
    result["correction"] = sum(result[kind]["offset"] for kind in C.KINDS)
    result["mismatch"] = flags
    return result


def _fit(pairs, players):
    """pairs: {(a, b): [wins_a, games]} with a < b. Returns {id: elo}."""
    gamma = {p: 1.0 for p in players}
    wins = {p: PRIOR_GAMES for p in players}
    opponents = {p: [] for p in players}
    for (a, b), (won, games) in pairs.items():
        wins[a] += won
        wins[b] += games - won
        opponents[a].append((b, games))
        opponents[b].append((a, games))
    for _ in range(500):
        delta = 0.0
        for p in players:
            denominator = 2 * PRIOR_GAMES / (gamma[p] + 1.0)
            denominator += sum(games / (gamma[p] + gamma[q]) for q, games in opponents[p])
            value = wins[p] / denominator
            delta = max(delta, abs(math.log(value / gamma[p])))
            gamma[p] = value
        if delta < 1e-7:
            break
    scale = 400 / math.log(10)
    result = {}
    for p in players:
        info = 2 * PRIOR_GAMES * gamma[p] / (gamma[p] + 1.0) ** 2
        info += sum(games * gamma[p] * gamma[q] / (gamma[p] + gamma[q]) ** 2 for q, games in opponents[p])
        result[p] = (ANCHOR + scale * math.log(gamma[p]), scale / math.sqrt(info))
    return result


def ratings(db):
    """{version_id: {elo, elo_sd, games, wins, rank_sum}} over public complete matches (cached)."""
    key = tuple(db.execute("SELECT COUNT(*),COALESCE(MAX(finished_at),0) FROM matches WHERE status='complete' AND public=1").fetchone())
    with _lock:
        if _cache["key"] == key:
            return _cache["value"]
    pairs, stats = {}, {}
    for row in db.execute("SELECT seat_json,result_json FROM matches WHERE status='complete' AND public=1 AND result_json IS NOT NULL"):
        seats = json.loads(row["seat_json"])
        result = json.loads(row["result_json"]).get("stats", {})
        ranks = [(seat["id"], result.get(str(index), {}).get("rank")) for index, seat in enumerate(seats)]
        ranks = [(vid, rank) for vid, rank in ranks if rank is not None]
        if len(ranks) < 2:
            continue
        weight = 1.0 / (len(ranks) - 1)
        for vid, rank in ranks:
            item = stats.setdefault(vid, {"games": 0, "wins": 0, "rank_sum": 0})
            item["games"] += 1
            item["wins"] += rank == 1
            item["rank_sum"] += rank
        for i, (a, ra) in enumerate(ranks):
            for b, rb in ranks[i + 1:]:
                if a == b:
                    continue
                score = 1.0 if ra < rb else 0.0 if ra > rb else 0.5
                low, high = (a, b) if a < b else (b, a)
                cell = pairs.setdefault((low, high), [0.0, 0.0])
                cell[0] += (score if low == a else 1.0 - score) * weight
                cell[1] += weight
    fitted = _fit(pairs, list(stats)) if stats else {}
    value = {vid: {**stats[vid], "elo": fitted[vid][0], "elo_sd": fitted[vid][1]} for vid in stats}
    with _lock:
        _cache["key"], _cache["value"] = key, value
    return value


def board(db, include_hidden=False):
    """Every rated version with its raw ELO, correction and adjusted ELO, best first."""
    catalog = C.load(db)
    rated = ratings(db)
    if not rated:
        return []
    marks = ",".join("?" * len(rated))
    rows = db.execute(
        f"""SELECT v.*,b.name AS bot_name,b.builtin,b.owner_id,u.display_name AS author,u.username
        FROM versions v JOIN bots b ON b.id=v.bot_id LEFT JOIN users u ON u.id=b.owner_id WHERE v.id IN ({marks})""",
        list(rated),
    ).fetchall()
    entries = []
    for row in rows:
        stats = rated[row["id"]]
        builtin = bool(row["builtin"])
        attr = None if builtin else attribution(row, catalog)
        correction = 0.0 if builtin else attr["correction"]
        entries.append({
            "version_id": row["id"], "bot_id": row["bot_id"], "bot_name": row["bot_name"], "version": row["version"],
            "author": row["author"], "author_id": row["owner_id"], "username": row["username"], "builtin": int(builtin),
            "listed": bool(row["listed"]) and not row["archived"],
            "games": stats["games"], "wins": stats["wins"], "win_rate": stats["wins"] / stats["games"],
            "avg_rank": stats["rank_sum"] / stats["games"],
            "elo": round(stats["elo"], 1), "elo_sd": round(stats["elo_sd"], 1),
            "correction": correction, "adjusted_elo": round(stats["elo"] - correction, 1),
            "attribution": attr,
        })
    entries.sort(key=lambda e: (-e["adjusted_elo"], -e["elo"], e["bot_name"]))
    rank = 0
    for entry in entries:
        if not entry["builtin"] and entry["listed"]:
            rank += 1
            entry["rank"] = rank
        else:
            entry["rank"] = None
    return entries if include_hidden else [e for e in entries if e["listed"] or e["builtin"]]
