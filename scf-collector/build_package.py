"""
打包云函数部署包（zip）
用法：python build_package.py
输出：dist/scf-collector.zip
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
DIST = HERE / "dist"
PACKAGE = DIST / "package"


def main():
    # 清理
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    DIST.mkdir(parents=True, exist_ok=True)

    # 1. 复制代码文件
    print("[1/4] Copying code files...")
    for f in ("handler.py", "collector.py", "models.py", "requirements.txt"):
        shutil.copy2(HERE / f, PACKAGE / f)

    # 2. 安装依赖（纯 Python 包，跨平台兼容）
    print("[2/4] Installing dependencies...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(HERE / "requirements.txt"),
            "-t",
            str(PACKAGE),
        ],
        check=True,
    )

    # 3. 清理 __pycache__ 和 .pyc
    print("[3/4] Cleaning up...")
    for pyc in PACKAGE.rglob("*.pyc"):
        pyc.unlink()
    for cache in PACKAGE.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    # 4. 打包 zip
    print("[4/4] Creating zip...")
    zip_path = DIST / "scf-collector.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in PACKAGE.rglob("*"):
            if f.is_file():
                arcname = f.relative_to(PACKAGE)
                z.write(f, arcname=arcname)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"\n✅ Package created: {zip_path} ({size_mb:.1f} MB)")
    print(f"   Total files: {len(list(PACKAGE.rglob('*')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
