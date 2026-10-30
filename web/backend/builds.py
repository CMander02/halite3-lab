import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid
from . import settings as S
from .storage import extract
from .eligibility import CPP_ONLY, eligible, trusted_builtin


class BotBuildError(RuntimeError):
    pass


spec = importlib.util.spec_from_file_location(
    "halite_sandbox", S.ROOT / "runner/sandbox.py"
)
sandbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandbox)


def prepare(seat, cancelled=lambda: False):
    # Serialize cold builds across workers, including publication of cache metadata.
    # Cache hits also take the lock, so they never observe a partially published build.
    with (S.DATA / "build.lock").open("a") as lock:
        while True:
            if cancelled():
                raise RuntimeError("执行器停止，编译等待重试。")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.1)
        return _prepare(seat, cancelled)


def _prepare(seat, cancelled):
    if not eligible(seat):
        raise BotBuildError(CPP_ONLY)
    directory = (
        (S.DATA / seat["object_key"]).parent
        if seat["owner_id"]
        else S.DATA / "builtin" / seat["id"]
    )
    cache = directory / "runtime"
    metadata = directory / "build.json"
    if metadata.exists() and cache.exists():
        info = json.loads(metadata.read_text())
        if info["source_sha256"] == seat["sha256"] and info["language"] == seat["language"]:
            return cache, info
    failure = directory / "build-error.json"
    if failure.exists():
        previous = json.loads(failure.read_text())
        if previous["source_sha256"] == seat["sha256"]:
            raise BotBuildError(previous["error"])
    payload = (S.DATA / seat["object_key"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != seat["sha256"]:
        raise RuntimeError("源码摘要校验失败。")
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".build-{uuid.uuid4().hex}"
    try:
        try:
            language = extract(
                payload, seat["filename"], temporary,
                allow_builtin_python=trusted_builtin(seat),
            )
        except ValueError as exc:
            raise BotBuildError(str(exc)) from exc
        info = {"language": language, "source_sha256": seat["sha256"]}
        if language == "cpp":
            temporary.chmod(0o700)
            sources = sorted(
                "/bot/" + str(path.relative_to(temporary))
                for path in temporary.rglob("*")
                if path.is_file() and path.suffix.lower() in (".cpp", ".cc", ".cxx")
            )
            args = [
                S.CXX,
                "-std=c++17",
                "-O2",
                "-pipe",
                "-w",
                "-fmax-errors=8",
                "-o",
                "/bot/bot",
                "-x",
                "c++",
                *sources,
            ]
            unit = f"{S.scope_prefix('build')}-{uuid.uuid4().hex[:12]}"
            proc = None
            try:
                proc = subprocess.Popen(
                    sandbox.command(temporary, args, unit, compile=True),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                deadline = time.monotonic() + 65
                while True:
                    if cancelled():
                        raise RuntimeError("执行器停止，编译等待重试。")
                    if time.monotonic() >= deadline:
                        raise BotBuildError("C++ 编译超过 60 秒。")
                    try:
                        _, stderr = proc.communicate(timeout=0.5)
                        break
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                if proc and proc.poll() is None:
                    proc.kill()
                    proc.communicate()
                subprocess.run(
                    ["systemctl", "--user", "stop", unit + ".scope"],
                    capture_output=True,
                    timeout=10,
                )
            if proc.returncode:
                raise BotBuildError("C++ 编译失败：" + stderr[-5000:])
            info["compiler"] = subprocess.check_output(
                [S.CXX, "--version"], text=True
            ).splitlines()[0]
            info["binary_sha256"] = hashlib.sha256(
                (temporary / "bot").read_bytes()
            ).hexdigest()
        for item in temporary.rglob("*"):
            item.chmod(0o555 if item.is_dir() or item.name == "bot" else 0o444)
        temporary.chmod(0o555)
        if cache.exists():
            raise RuntimeError("版本编译缓存与源码不一致，请发布新版本。")
        # Publish metadata first: an interrupted build with no runtime is safe to
        # rebuild. A runtime without metadata would block all future retries.
        metadata.write_text(json.dumps(info, ensure_ascii=False, indent=2))
        temporary.replace(cache)
        return cache, info
    except BotBuildError as exc:
        failure.write_text(
            json.dumps(
                {"source_sha256": seat["sha256"], "error": str(exc)}, ensure_ascii=False
            )
        )
        raise
    finally:
        if temporary.exists():
            temporary.chmod(0o700)
            for path in temporary.rglob("*"):
                if path.is_dir():
                    path.chmod(0o700)
            shutil.rmtree(temporary, ignore_errors=True)
