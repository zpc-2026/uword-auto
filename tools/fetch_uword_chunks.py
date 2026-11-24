"""下载外研U词（word.fltrp.com）各页面 chunk，抽取全部后端接口。

chunk 名/哈希来自 index.57ddade8.js 的 webpack 运行时表。
"""
from __future__ import annotations

import re
import ssl
import sys
import urllib.request
from pathlib import Path

BASE = "https://word.fltrp.com/"
OUT = Path("tmp/uword_web")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 MicroMessenger/8.0.50"

CHUNKS = {
    "pages-index-index": "412284e1",
    "pages-index-realindex": "f00a6647",
    "pages-user-login": "222f7a1b",
    "pages-user-index": "4c155248",
    "pages-user-userinfo": "1db7cafd",
    "pages-user-addmoreinfo": "ffdd6217",
    "pages-user-classsel": "6f77c7b7",
    "pages-user-ding": "3f956ecc",
    "pages-user-rank": "88fc5768",
    "pages-user-rank~pages-word-restudy~pages-word-study": "e336d620",
    "pages-books-index": "3af931a8",
    "pages-books-verifycard": "6f48be9d",
    "pages-word-list": "12bef004",
    "pages-word-detail": "3a8fef4b",
    "pages-word-mywb": "46787e50",
    "pages-word-plan": "629fa87f",
    "pages-word-study": "31c01ff6",
    "pages-word-restudy": "f4ee7e27",
    "pages-word-readonlydetail": "7501637b",
    "pages-class-create": "8de396eb",
    "pages-class-listclass": "e4941404",
    "pages-class-myclass": "05724850",
    "pages-class-myclassdetail": "c6f58a05",
    "pages-class-st": "703602f1",
    "pages-class-stdetail": "6554a1c7",
    "pages-webview-index": "7645e99a",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

EP = re.compile(r"""["'](/[A-Za-z0-9_\-]+/[A-Za-z0-9_\-\.]+\.(?:htm|do|json))["']""")
PARAM = re.compile(r"""["']([a-zA-Z_][a-zA-Z0-9_]{1,24})["']\s*:""")


def fetch(name: str, h: str) -> bytes:
    url = f"{BASE}static/js/{name}.{h}.js"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return r.read()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    endpoints: dict[str, set[str]] = {}
    for name, h in CHUNKS.items():
        try:
            data = fetch(name, h)
        except Exception as e:  # noqa: BLE001
            print(f"! {name}: {e}")
            continue
        p = OUT / f"{name}.js"
        p.write_bytes(data)
        txt = data.decode("utf-8", "replace")
        eps = set(EP.findall(txt))
        print(f"{len(data):>8}  {name:<52} 端点 {len(eps)}")
        for e in eps:
            endpoints.setdefault(e, set()).add(name)

    print(f"\n=== 去重后端接口 {len(endpoints)} 个 ===")
    for e in sorted(endpoints):
        print(f"  {e:<45} ← {', '.join(sorted(endpoints[e]))[:70]}")

    # 顺带看各 chunk 里出现的请求参数名
    print("\n=== 参数名（每 chunk） ===")
    for p in sorted(OUT.glob("pages-*.js")):
        txt = p.read_text(encoding="utf-8", errors="replace")
        names = sorted(set(PARAM.findall(txt)))
        interesting = [n for n in names if re.search(
            r"id|Id|token|sign|openid|card|book|word|plan|score|answer|type|status", n)]
        if interesting:
            print(f"  {p.stem:<45} {interesting[:24]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
