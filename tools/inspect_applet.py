"""侦察本机小程序缓存：从 mmkv / 日志 / 代码包里提取接口域名、token、字段名。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE = Path.home() / "AppData" / "Roaming" / "Tencent" / "xwechat" / "radium" / "users"
KEYWORDS = re.compile(
    r"(https?://[\w\.\-:/?=&%]+|unipus|uword|uwcd|ucampus|wx[0-9a-f]{16}|token|"
    r"Authorization|Cookie|api/|/v\d/|bookid|wordid|quiz|vocab)", re.I)

ASCII_RUN = re.compile(rb"[\x20-\x7e]{8,}")
UTF8_CJK = re.compile("[\u4e00-\u9fff][\u4e00-\u9fff\w：；，。、（）]{1,30}")


def strings_of(path: Path, min_len: int = 8) -> list[str]:
    try:
        data = path.read_bytes()
    except OSError as e:
        return [f"[read error] {e}"]
    out = []
    for m in ASCII_RUN.finditer(data):
        s = m.group().decode("ascii", "ignore")
        if len(s) >= min_len:
            out.append(s)
    txt = data.decode("utf-8", "ignore")
    out.extend(m.group() for m in UTF8_CJK.finditer(txt))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--appid", default="wx90b850fca1220d58")
    ap.add_argument("--root", default=None)
    ap.add_argument("--keyword", default=None, help="只看命中关键词的行")
    ap.add_argument("--raw", action="store_true", help="打印全部字符串（不筛）")
    ap.add_argument("--limit", type=int, default=400)
    args = ap.parse_args()

    root = Path(args.root) if args.root else BASE
    if not root.exists():
        print(f"找不到 {root}")
        return 1
    targets = [p for p in root.rglob(f"*{args.appid}*") if p.is_file()]
    print(f"目标文件 {len(targets)} 个：")
    for p in targets:
        print(f"  {p.stat().st_size:>9}  {p}")

    kw = re.compile(args.keyword, re.I) if args.keyword else KEYWORDS
    seen: set[str] = set()
    hits: list[tuple[str, str]] = []
    for p in targets:
        for s in strings_of(p):
            s = s.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            if args.raw or kw.search(s):
                hits.append((p.name, s))

    print(f"\n命中 {len(hits)} 条：")
    for name, s in hits[: args.limit]:
        print(f"[{name}] {s[:400]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
