"""从打包后的 JS 里提取接口路径与请求参数名。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PAT = {
    "htm": re.compile(r"""["'](/[A-Za-z0-9_\-]+/[A-Za-z0-9_\-\.]+\.(?:htm|do|action|json))["']"""),
    "slash": re.compile(r"""["'](/[A-Za-z0-9_\-]+/[A-Za-z0-9_\-/]{2,60})["']"""),
    "url_key": re.compile(r"""url\s*:\s*["']([^"']{2,160})["']"""),
    "prop": re.compile(r"""(?:token|openid|session|ticket|sign|appid|bookId|wordId|planId|cardNo|userId)"""),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--kind", default="htm,slash,url_key")
    args = ap.parse_args()
    kinds = args.kind.split(",")

    for f in args.files:
        p = Path(f)
        txt = p.read_text(encoding="utf-8", errors="replace")
        print(f"===== {p.name} ({len(txt)} chars) =====")
        for k in kinds:
            rx = PAT[k]
            vals = list(dict.fromkeys(rx.findall(txt)))
            if k == "slash":
                vals = [v for v in vals if not v.startswith(("/static/", "/images/", "/img/"))]
            print(f"-- {k}: {len(vals)} 个 --")
            for v in vals[:80]:
                print("  ", v[:160])
        props = sorted(set(PAT["prop"].findall(txt)))
        print(f"-- 关键字段名: {props}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
