import io
from pathlib import PurePosixPath
import shutil
import stat
import zipfile
from fastapi import HTTPException
from . import settings as S


def disk_check():
    if shutil.disk_usage(S.DATA).free < S.MIN_DISK_FREE:
        raise HTTPException(507, "服务器可用空间不足，已暂停新上传和新测试。")


def validate_archive(data, filename):
    if len(data) > S.MAX_UPLOAD:
        raise ValueError("文件不能超过 5 MiB。")
    if filename.lower().endswith(".py"):
        data.decode("utf-8-sig")
        return "python"
    if filename.lower().endswith((".cpp", ".cc", ".cxx")):
        data.decode("utf-8-sig")
        return "cpp"
    if not filename.lower().endswith(".zip"):
        raise ValueError("支持 Python、C++ 源码，或包含 bot.py / C++ 源码的 ZIP。")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = archive.infolist()
        if not files or len(files) > 64:
            raise ValueError("ZIP 最多包含 64 个条目。")
        if sum(f.file_size for f in files) > S.MAX_UNPACKED:
            raise ValueError("ZIP 解压后不能超过 20 MiB。")
        seen = set()
        for item in files:
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in item.filename
                or ":" in item.filename
                or path.as_posix() in seen
                or stat.S_ISLNK(mode)
                or (
                    stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))
                )
            ):
                raise ValueError("ZIP 包含不安全的路径或文件类型。")
            if item.flag_bits & 1:
                raise ValueError("不支持加密 ZIP。")
            seen.add(path.as_posix())
        cpp = [
            name
            for name in seen
            if PurePosixPath(name).suffix.lower() in (".cpp", ".cc", ".cxx")
        ]
        if "bot.py" not in seen and not cpp:
            raise ValueError("ZIP 必须包含根目录 bot.py，或 C++ 源码。")
        if len(cpp) > 24:
            raise ValueError("C++ 项目最多包含 24 个编译单元。")
        if archive.testzip() is not None:
            raise ValueError("ZIP 校验失败。")
    return "python" if "bot.py" in seen else "cpp"


def extract(data, filename, destination):
    kind = validate_archive(data, filename)
    destination.mkdir(parents=True, exist_ok=True)
    if not filename.lower().endswith(".zip"):
        (destination / ("bot.py" if kind == "python" else "main.cpp")).write_bytes(data)
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for item in archive.infolist():
                target = destination / item.filename
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(item))
    for target in destination.rglob("*"):
        target.chmod(0o555 if target.is_dir() else 0o444)
    destination.chmod(0o555)
    return kind
