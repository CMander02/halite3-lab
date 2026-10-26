from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
# Remove the obsolete generated download when rebuilding an existing checkout.
(root / "public/sample-python.zip").unlink(missing_ok=True)
(root / "dist/sample-python.zip").unlink(missing_ok=True)
with zipfile.ZipFile(root / "public/sample-cpp.zip", "w") as archive:
    info = zipfile.ZipInfo("main.cpp", date_time=(2026, 10, 25, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, (root / "examples/cpp/main.cpp").read_bytes())
