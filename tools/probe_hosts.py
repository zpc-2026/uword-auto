"""探测候选域名：根路径 + 常见 API 前缀，输出状态码/类型/响应片段。"""
from __future__ import annotations

import ssl
import sys
import urllib.error
import urllib.request

HOSTS = ["uword.fltrp.com", "word.fltrp.com", "birdflock.unipus.cn", "uai.unipus.cn",
         "learn.unipus.cn", "app.unipus.cn"]
PATHS = ["/", "/api/", "/api/v1/", "/favicon.ico"]


def probe(url: str):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MicroMessenger/8.0.50",
        "Accept": "*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
            body = r.read(400)
            return r.status, r.headers.get("Content-Type", ""), r.headers.get("Server", ""), body
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.headers.get("Server", ""), e.read(300)
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__, "", str(e)[:120].encode()


def main() -> int:
    for host in HOSTS:
        print(f"===== {host} =====")
        for p in PATHS:
            url = f"https://{host}{p}"
            status, ctype, server, body = probe(url)
            snippet = body[:150].decode("utf-8", "replace").replace("\n", " ") if isinstance(body, bytes) else body
            print(f"  {str(status):<4} {url:<45} ct={ctype[:30]:<30} srv={server[:20]:<20} {snippet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
