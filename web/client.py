#!/usr/bin/env python3
"""Upload versions, submit to contests and schedule Halite 3 tests directly through the backend.

Agents: set HALITE_TOKEN (create one under 账号与头像) instead of running `login`."""

import argparse, getpass, json, os, secrets, urllib.request, urllib.error
from pathlib import Path

CONFIG = Path.home() / ".config/halite3/credentials.json"


def request(
    origin,
    path,
    token=None,
    payload=None,
    method=None,
    raw=None,
    content_type=None,
    cookie=None,
    binary=False,
):
    # Cloudflare rejects the default Python-urllib signature.
    headers = {"Origin": origin, "Accept": "application/json", "User-Agent": "halite3-cli/1.1 (+https://github.com/CMander02/halite3-lab)"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if cookie:
        headers["Cookie"] = cookie
    if payload is not None:
        raw = json.dumps(payload).encode()
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                origin + "/api" + path, data=raw, headers=headers, method=method
            ),
            timeout=60,
        ) as response:
            return (response.read() if binary else json.load(response)), response.headers
    except urllib.error.HTTPError as exc:
        raise SystemExit(str(json.load(exc).get("detail", str(exc))))


def multipart(fields, files):
    """(body, content type) for form fields and (field, path) file parts."""
    boundary = "halite3-" + secrets.token_hex(16)
    parts = []
    for key, value in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    for field, path in files:
        content = path.read_bytes()
        limit = 16 * 1024**2 if field == "trace" else 5 * 1024**2
        if len(content) > limit:
            raise SystemExit(f"{path}: over the {limit // 1024**2} MiB limit" + (" (gzip it first)" if field == "trace" else ""))
        filename = path.name.replace('"', "").replace("\r", "").replace("\n", "")
        parts += [
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
            content,
            b"\r\n",
        ]
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("login")
    commands.add_parser("bots")
    upload = commands.add_parser("upload")
    upload.add_argument("file")
    upload.add_argument("--name", required=True)
    upload.add_argument("--version", required=True)
    upload.add_argument("--notes", default="")
    upload.add_argument("--trace", help="optional agent trace that produced this version (JSONL / JSON / text, .gz ok)")
    upload.add_argument("--model", default="unknown", help="catalog id, see `catalog`")
    upload.add_argument("--effort", default="unknown")
    upload.add_argument("--harness", default="unknown")
    upload.add_argument("--rank", action="store_true", help="submit the new version to the public evaluation")
    commands.add_parser("catalog")
    test = commands.add_parser("test")
    test.add_argument("--versions")
    test.add_argument("--bots")
    test.add_argument("--modes", default="2")
    test.add_argument("--seeds", default="11,29,47")
    test.add_argument("--rotate", action="store_true")
    test.add_argument("--name", default="CLI 循环赛")
    status = commands.add_parser("status")
    status.add_argument("job", nargs="?")
    rank = commands.add_parser("rank")
    rank.add_argument("version_id")
    commands.add_parser("contests")
    kit = commands.add_parser("kit", help="download a contest's problem kit (prompt, rules, maps, reference bots)")
    kit.add_argument("contest")
    kit.add_argument("-o", "--output")
    submit = commands.add_parser("contest-submit", help="upload bot.cpp and submit it to a contest")
    submit.add_argument("contest")
    submit.add_argument("file", help="must be named bot.cpp")
    submit.add_argument("--bot", default="", help="bot to iterate on (created on first use; default: the contest slug)")
    submit.add_argument("--version", default="", help="default: next number")
    submit.add_argument("--note", default="")
    submit.add_argument("--trace", help="optional agent trace (Claude Code / Codex session JSONL, .gz ok)")
    submit.add_argument("--model", default="unknown", help="catalog id, see `catalog`")
    submit.add_argument("--effort", default="unknown")
    submit.add_argument("--harness", default="unknown")
    contest_status = commands.add_parser("contest-status", help="your submissions to a contest: progress and provisional ELO")
    contest_status.add_argument("contest")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    origin = (
        args.origin or config.get("origin") or "https://halite3.cmander02.com"
    ).rstrip("/")
    if args.action == "login":
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        _, headers = request(
            origin,
            "/auth/login",
            payload={"username": username, "password": password},
            method="POST",
        )
        result, _ = request(
            origin,
            "/tokens",
            payload={"name": "halite3-cli"},
            method="POST",
            cookie=headers["Set-Cookie"].split(";", 1)[0],
        )
        CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"origin": origin, "token": result["token"]}, stream)
        CONFIG.chmod(0o600)
        print("Logged in. Token saved with permissions 0600; expires in 30 days.")
        return
    token = os.environ.get("HALITE_TOKEN") or config.get("token")
    if args.action == "contests":
        result, _ = request(origin, "/contests", token)
        result = [{k: c[k] for k in ("number", "slug", "title", "status", "open_at", "close_at", "modes")} for c in result["contests"]]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.action == "kit":
        data, _ = request(origin, f"/contests/{args.contest}/kit.zip", token, binary=True)
        output = Path(args.output or f"halite3-{args.contest}-kit.zip")
        output.write_bytes(data)
        print(f"Saved {output} ({len(data)} bytes). Unzip it and start from PROMPT.md.")
        return
    if not token:
        raise SystemExit("Run login first or set HALITE_TOKEN.")
    if args.action == "contest-submit":
        file = Path(args.file)
        if file.name not in ("bot.cpp", "bot.py"):
            raise SystemExit("Contest submissions must be a single file named bot.cpp.")
        body, content_type = multipart(
            [("bot", args.bot), ("version", args.version), ("note", args.note), ("model", args.model),
             ("effort", args.effort), ("harness", args.harness)],
            [("file", file)] + ([("trace", Path(args.trace))] if args.trace else []),
        )
        result, _ = request(origin, f"/contests/{args.contest}/submit", token, method="POST", raw=body, content_type=content_type)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.action == "contest-status":
        result, _ = request(origin, f"/contests/{args.contest}/entries", token)
        result = [{"seq": e["seq"], "bot": e["bot_name"], "version": e["version"], "current": e["current"],
                   "complete": e["counts"].get("complete", 0), "total": e["total"], "failed": e["counts"].get("failed", 0),
                   "elo": {mode: s and {"adjusted": s["adjusted_elo"], "raw": s["elo"], "win_rate": round(s["win_rate"], 3), "games": s["games"]}
                           for mode, s in e["stats"].items()}}
                  for e in result["entries"]]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.action == "bots":
        result, _ = request(origin, "/bots", token)
    elif args.action == "catalog":
        result, _ = request(origin, "/catalog", token)
        result = {kind: [e["id"] for e in entries] for kind, entries in result.items()}
    elif args.action == "status":
        result, _ = request(
            origin, "/tests" + ("/" + args.job if args.job else ""), token
        )
    elif args.action == "rank":
        result, _ = request(
            origin,
            f"/versions/{args.version_id}/rank",
            token,
            payload={},
            method="POST",
        )
    elif args.action == "test":
        if bool(args.versions) == bool(args.bots):
            parser.error("Use one of --versions or --bots")
        result, _ = request(
            origin,
            "/tests",
            token,
            payload={
                "name": args.name,
                "version_ids": args.versions.split(",") if args.versions else [],
                "bot_ids": args.bots.split(",") if args.bots else [],
                "modes": [int(v) for v in args.modes.split(",")],
                "seeds": [int(v) for v in args.seeds.split(",")],
                "rotate_seats": args.rotate,
            },
            method="POST",
        )
    else:
        bots, _ = request(origin, "/bots", token)
        bot = next(
            (b for b in bots["bots"] if b["owned"] and b["name"] == args.name), None
        )
        if not bot:
            bot, _ = request(
                origin, "/bots", token, payload={"name": args.name}, method="POST"
            )
        body, content_type = multipart(
            [("version", args.version), ("notes", args.notes), ("model", args.model),
             ("effort", args.effort), ("harness", args.harness), ("rank", "true" if args.rank else "false")],
            [("file", Path(args.file))] + ([("trace", Path(args.trace))] if args.trace else []),
        )
        result, _ = request(
            origin,
            f"/bots/{bot['id']}/versions",
            token,
            method="POST",
            raw=body,
            content_type=content_type,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
