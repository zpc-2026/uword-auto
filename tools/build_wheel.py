"""手工打 wheel（环境里没有 setuptools/wheel，但 wheel 本质就是个规定布局的 zip）。

    python tools/build_wheel.py            # → dist/uword_auto-<ver>-py3-none-any.whl
"""
from __future__ import annotations

import base64
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "uword_auto"
VERSION = re.search(r'version\s*=\s*"([^"]+)"',
                    (ROOT / "pyproject.toml").read_text(encoding="utf-8")).group(1)
DIST = ROOT / "dist"
OUT = DIST / f"{NAME}-{VERSION}-py3-none-any.whl"

METADATA = f"""Metadata-Version: 2.1
Name: uword-auto
Version: {VERSION}
Summary: 外研U词（word.fltrp.com）自动化：背词、单词检验、复习，含 agent 可调用的 JSON 接口
Home-page: https://github.com/zpc-2026/uword-auto
License: MIT
Requires-Python: >=3.9
Description-Content-Type: text/markdown

外研U词自动化：`uword login` 一次，之后 `uword learn 40` / `uword review` / `api.learn(20)`。
详见 https://github.com/zpc-2026/uword-auto
"""

WHEEL = """Wheel-Version: 1.0
Generator: uword-auto-build
Root-Is-Purelib: true
Tag: py3-none-any
"""

ENTRY = """[console_scripts]
uword = uword.cli:main
"""


def url_safe_digest(data: bytes) -> str:
    h = hashlib.sha256(data).digest()
    return base64.urlsafe_b64encode(h).rstrip(b"=").decode()


def main() -> int:
    DIST.mkdir(exist_ok=True)
    pkg_files = sorted(p for p in (ROOT / "uword").rglob("*.py"))
    if not pkg_files:
        print("没有找到 uword 包文件")
        return 1

    dist_info = f"{NAME}-{VERSION}.dist-info"
    entries: list[tuple[str, bytes]] = []
    for p in pkg_files:
        arc = p.relative_to(ROOT).as_posix()
        entries.append((arc, p.read_bytes()))
    entries.append((f"{dist_info}/METADATA", METADATA.encode()))
    entries.append((f"{dist_info}/WHEEL", WHEEL.encode()))
    entries.append((f"{dist_info}/entry_points.txt", ENTRY.encode()))
    entries.append((f"{dist_info}/top_level.txt", b"uword\n"))

    record_lines = []
    for arc, data in entries:
        record_lines.append(f"{arc},sha256={url_safe_digest(data)},{len(data)}")
    record_lines.append(f"{dist_info}/RECORD,,")
    entries.append((f"{dist_info}/RECORD", ("\n".join(record_lines) + "\n").encode()))

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in entries:
            z.writestr(arc, data)

    print(f"✓ {OUT}  ({OUT.stat().st_size/1024:.1f} KB, {len(entries)} 个条目)")
    print(f"  版本 {VERSION}，包含 {len(pkg_files)} 个 .py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
