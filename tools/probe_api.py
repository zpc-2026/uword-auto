"""直接探外研U词后端：确认接口存在性、鉴权要求、错误码格式。"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request

BASE = "https://word.fltrp.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36 MicroMessenger/8.0.50")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

CASES = [
    ("GET", "yyuserplan/nowplan.htm", {"status": 0}),
    ("GET", "/yyuserplan/nowplan.htm", {"status": 0}),
    ("GET", "adminapi/yyuserplan/nowplan.htm", {"status": 0}),
    ("GET", "yyuserplan/nowplancontent.htm", {"pageid": 1}),
    ("GET", "wordentry/selquestionbyword.htm", {"word": "acquire", "count": 1}),
    ("GET", "yyuserfollow/queryhas.htm", {"wordid": 1}),
    ("POST", "yyuserscore/add.htm", {"wordid": 1, "type": 1}),
    ("POST", "fltrp/openapi/sso.htm", {"path": "1.0/sso/login", "username": "0", "password": "0"}),
    ("GET", "yyuser/openapi/wxlogin.htm", {"code": "0", "source": "miniappid", "type": 0}),
]


def call(method: str, path: str, params: dict) -> tuple[int | None, str]:
    url = BASE + path.lstrip("/")
    data = None
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
               "Origin": "https://word.fltrp.com", "Referer": "https://word.fltrp.com/"}
    if method == "GET":
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    else:
        data = json.dumps(params, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json;charset=UTF-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15, context=CTX) as r:
            return r.status, r.read(600).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(400).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def main() -> int:
    for method, path, params in CASES:
        status, body = call(method, path, params)
        body = " ".join(body.split())[:300]
        print(f"{str(status):<4} {method:<4} {path:<42} {body}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
