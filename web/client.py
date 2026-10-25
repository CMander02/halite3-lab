#!/usr/bin/env python3
"""Upload versions and schedule Halite 3 tests directly through the backend."""

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
            return json.load(response), response.headers
    except urllib.error.HTTPError as exc:
        raise SystemExit(str(json.load(exc).get("detail", str(exc))))


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
    upload.add_argument("--trace", required=True, help="conversation trace that produced this version (JSONL / JSON / text, .gz ok)")
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
    if not token:
        raise SystemExit("Run login first or set HALITE_TOKEN.")
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
        file = Path(args.file)
        data = file.read_bytes()
        if len(data) > 5 * 1024**2:
            raise SystemExit("Upload limit: 5 MiB.")
        trace = Path(args.trace)
        trace_data = trace.read_bytes()
        if len(trace_data) > 16 * 1024**2:
            raise SystemExit("Trace limit: 16 MiB (gzip it first).")
        bots, _ = request(origin, "/bots", token)
        bot = next(
            (b for b in bots["bots"] if b["owned"] and b["name"] == args.name), None
        )
        if not bot:
            bot, _ = request(
                origin, "/bots", token, payload={"name": args.name}, method="POST"
            )
        boundary = "halite3-" + secrets.token_hex(16)
        parts = []
        fields = [("version", args.version), ("notes", args.notes), ("model", args.model),
                  ("effort", args.effort), ("harness", args.harness), ("rank", "true" if args.rank else "false")]
        for key, value in fields:
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            )
        for field, path, content in [("file", file, data), ("trace", trace, trace_data)]:
            filename = path.name.replace('"', "").replace("\r", "").replace("\n", "")
            parts += [
                f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
                content,
                b"\r\n",
            ]
        parts.append(f"--{boundary}--\r\n".encode())
        result, _ = request(
            origin,
            f"/bots/{bot['id']}/versions",
            token,
            method="POST",
            raw=b"".join(parts),
            content_type="multipart/form-data; boundary=" + boundary,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
