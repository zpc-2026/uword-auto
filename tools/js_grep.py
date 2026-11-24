"""在 JS 包里做正则检索：python tools/js_grep.py <pattern> [glob] [--ctx N]"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern")
    ap.add_argument("glob", nargs="?", default="*.js")
    ap.add_argument("--dir", default="tmp/uword_web")
    ap.add_argument("--ctx", type=int, default=90)
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()
    rx = re.compile(args.pattern)
    total = 0
    for p in sorted(Path(args.dir).glob(args.glob)):
        txt = p.read_text(encoding="utf-8", errors="replace")
        for m in rx.finditer(txt):
            total += 1
            if total > args.limit:
                print(f"... 已达上限 {args.limit}")
                return 0
            s = max(0, m.start() - args.ctx)
            e = min(len(txt), m.end() + args.ctx)
            print(f"[{p.name}:{m.start()}] …{txt[s:e]}…")
            print()
    print(f"共 {total} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
