"""解包 __APP__.wxapkg（微信小程序包），导出源码文件。

包格式（无加密的 .wxapkg）：
  0xBE | u32 info1 | u32 indexLen | u32 bodyLen | 0xED | u32 fileCount
  index[i]: u32 nameLen | name | u32 off | u32 size
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


def unpack(path: Path, out_dir: Path) -> list[Path]:
    data = path.read_bytes()
    if not data or data[0] != 0xBE:
        raise SystemExit("不是标准 wxapkg（首字节不是 0xBE），可能是加密包")
    info1, index_len, body_len = struct.unpack(">III", data[1:13])
    if data[13] != 0xED:
        raise SystemExit("格式不符（第 14 字节不是 0xED）")
    if index_len in (0, 0xFFFFFFFF) or body_len in (0, 0xFFFFFFFF):
        # 部分包把长度写在尾部
        index_len, body_len = struct.unpack(">II", data[-8:])
    base = 14
    idx = data[base:base + index_len]
    pos = 0
    count = struct.unpack(">I", idx[pos:pos + 4])[0]
    pos += 4
    entries = []
    for _ in range(count):
        nlen = struct.unpack(">I", idx[pos:pos + 4])[0]
        pos += 4
        name = idx[pos:pos + nlen].decode("utf-8", "replace")
        pos += nlen
        off, size = struct.unpack(">II", idx[pos:pos + 8])
        pos += 8
        entries.append((name, off, size))

    body = data[base + index_len: base + index_len + body_len]
    written = []
    for name, off, size in entries:
        rel = name.lstrip("/").replace("\\", "/")
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body[off:off + size])
        written.append(target)
    print(f"解出 {len(written)} 个文件 → {out_dir}  (info1={info1}, body={body_len})")
    for t in sorted(written, key=lambda p: -p.stat().st_size)[:15]:
        print(f"  {t.stat().st_size:>10}  {t.relative_to(out_dir)}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pkg")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()
    pkg = Path(args.pkg)
    out = Path(args.out) if args.out else pkg.with_suffix("")
    unpack(pkg, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
