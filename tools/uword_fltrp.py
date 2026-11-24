"""外研U词后端客户端（与小程序/网页同一套接口，Authorization 会话）。

用法：
    python tools/uword_fltrp.py plan
    python tools/uword_fltrp.py words --page 12 --limit 5
    python tools/uword_fltrp.py questions --word acquire
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://word.fltrp.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
TOKEN_FILE = Path("tmp/token.json")


def token() -> str:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["token"]
    raise SystemExit("缺 token：先写 tmp/token.json {\"token\":\"...\"}")


def call(path: str, body: dict | None = None, method: str = "POST", auth: str | None = None):
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://word.fltrp.com",
        "Referer": "https://word.fltrp.com/",
        "Authorization": auth or token(),
    }
    url = BASE + path.lstrip("/")
    data = None
    if method == "GET":
        if body:
            url += "?" + urllib.parse.urlencode(body)
    else:
        data = json.dumps(body or {}, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json;charset=UTF-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read(300).decode("utf-8", "replace")}
    except Exception as e:  # noqa: BLE001
        return {"_err": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "words", "questions", "raw"])
    ap.add_argument("--page", type=int, default=None)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--word", default="acquire")
    ap.add_argument("--path", default=None)
    ap.add_argument("--body", default="{}")
    args = ap.parse_args()

    if args.cmd == "plan":
        r = call("yyuserplan/nowplan.htm", {"status": 0})
        print(json.dumps(r, ensure_ascii=False)[:1200])

    elif args.cmd == "words":
        pageid = args.page
        if pageid is None:
            p = call("yyuserplan/nowplan.htm", {"status": 0})
            data = p.get("data") or p
            pageid = data.get("pageid") or data.get("id")
            print(f"pageid={pageid}  book={data.get('title') or data.get('title2')}")
        r = call("yyuserplan/nowplancontent.htm", {"pageid": pageid})
        content = r.get("content") or (r.get("data") or {}).get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                print("content 不是 JSON:", content[:200])
                return 1
        words = content if isinstance(content, list) else (content or {}).get("words") or []
        print(f"词数 {len(words)}")
        for w in words[: args.limit]:
            print(" ", json.dumps(w, ensure_ascii=False)[:200])

    elif args.cmd == "questions":
        r = call("wordentry/selquestionbyword.htm", {"word": args.word, "count": 3}, "GET")
        print(json.dumps(r, ensure_ascii=False)[:1500])

    elif args.cmd == "raw":
        if not args.path:
            print("给 --path")
            return 2
        print(json.dumps(call(args.path, json.loads(args.body)), ensure_ascii=False)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
