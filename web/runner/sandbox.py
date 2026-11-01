"""Process namespaces and cgroup limits; no container runtime or shared bot filesystem."""

from pathlib import Path
import os
import sys

BWRAP = os.environ.get("HALITE_BWRAP", "/usr/local/lib/halite3/bwrap")


def command(directory, argv, unit, compile=False, runtime=105, cpu_percent=35, slice_name=None):
    if not 1 <= int(cpu_percent) <= 100:
        raise ValueError("Bot CPU percent must be within 1..100")
    budget = (
        [
            "-p",
            "MemoryMax=512M",
            "-p",
            "MemorySwapMax=0",
            "-p",
            "CPUQuota=75%",
            "-p",
            "TasksMax=32",
            "-p",
            "RuntimeMaxSec=60",
        ]
        if compile
        else [
            "-p",
            "MemoryMax=192M",
            "-p",
            "MemorySwapMax=0",
            "-p",
            f"CPUQuota={int(cpu_percent)}%",
            "-p",
            "TasksMax=32",
            "-p",
            f"RuntimeMaxSec={int(runtime)}",
        ]
    )
    return [
        "systemd-run",
        "--user",
        "--scope",
        "--quiet",
        f"--unit={unit}",
        *([f"--slice={slice_name}"] if slice_name else []),
        *budget,
        BWRAP,
        "--unshare-all",
        "--unshare-user",
        "--disable-userns",
        "--assert-userns-disabled",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        "16777216",
        "--tmpfs",
        "/tmp",
        "--bind" if compile else "--ro-bind",
        str(Path(directory).resolve()),
        "/bot",
        "--chdir",
        "/bot",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--",
        *argv,
    ]


if __name__ == "__main__":
    import json

    config = json.loads(Path(sys.argv[1]).read_text())
    cmd = command(
        config["source_dir"], config["argv"], config["unit"], runtime=config.get("runtime", 105),
        cpu_percent=config.get("cpu_percent",35), slice_name=config.get("slice_name")
    )
    os.execvp(cmd[0], cmd)
