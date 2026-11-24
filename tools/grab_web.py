"""抓取前端站点：首页 → 静态资源 → 扫接口字符串。

    python tools/grab_web.py https://uword.fltrp.com/ --out tmp/uword_web
    python tools/grab_web.py https://uword.fltrp.com/ --out tmp/uword_web --scan
"""
from __future__ import annotations

import argparse
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 MicroMessenger/8.0.50"
ASSET = re.compile(r"""(?:src|href)=["']([^"']+\.(?:js|css))["']""", re.I)
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 值得关注的字符串
PATTERNS = {
    "url": re.compile(r"https?://[A-Za-z0-9\.\-]{4,60}(?::\d+)?[/A-Za-z0-9\._\-~%?=&+#]*"),
    "api_path": re.compile(r"[\"'](/[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-\{\}\$\.]+){1,5})[\"']"),
    "baseurl": re.compile(r"(?:baseURL|baseUrl|BASE_URL|API_URL|apiHost|host)\s*[:=]\s*[\"']([^\"']{4,120})[\"']"),
}


def get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="tmp/web")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--depth", type=int, default=1, help="从 JS 里再抓 JS 的层数")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    html = get(args.url).decode("utf-8", "replace")
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"index.html {len(html)} bytes")

    assets = [urllib.parse.urljoin(args.url, a) for a in ASSET.findall(html)]
    seen = set()
    queue = list(assets)
    for _ in range(args.depth + 1):
        nxt = []
        for u in queue:
            if u in seen:
                continue
            seen.add(u)
            try:
                data = get(u)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {u} {e}")
                continue
            name = u.rsplit("/", 1)[-1].split("?")[0]
            (out / name).write_bytes(data)
            print(f"  {len(data):>9}  {name}")
            if name.endswith(".js"):
                txt = data.decode("utf-8", "replace")
                for m in re.finditer(r"[\"'](\.?/?static/js/[A-Za-z0-9_\-\.]+\.js)[\"']", txt):
                    nxt.append(urllib.parse.urljoin(u, m.group(1)))
                for m in re.finditer(r"[\"'](\./[\w\-/]+\.js)[\"']", txt):
                    nxt.append(urllib.parse.urljoin(u, m.group(1)))
        queue = [u for u in nxt if u not in seen]

    if args.scan:
        scan(out)
    return 0


def scan(folder: Path) -> None:
    for p in sorted(folder.glob("*.js")) + sorted(folder.glob("*.json")):
        txt = p.read_text(encoding="utf-8", errors="replace")
        print(f"\n===== {p.name} ({len(txt)} 字符) =====")
        for label, rx in PATTERNS.items():
            hits = []
            for m in rx.finditer(txt):
                v = m.group(1) if m.groups() else m.group(0)
                if label == "api_path" and not re.search(r"api|word|book|learn|study|quiz|test|review|login|auth|user", v, re.I):
                    continue
                hits.append(v)
            uniq = list(dict.fromkeys(hits))[:40]
            if uniq:
                print(f"-- {label} ({len(hits)} 命中, 去重 {len(uniq)}) --")
                for v in uniq:
                    print(f"   {v[:150]}")


if __name__ == "__main__":
    sys.exit(main())
