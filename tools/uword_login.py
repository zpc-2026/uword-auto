"""外研U词 / 外研社 SSO 登录：拿到 Authorization 会话。

用法：
    python tools/uword_login.py                # 从 UnipusAI-Helper/config.json 读账号
    python tools/uword_login.py --user 138xx --pass xxx
    python tools/uword_login.py --probe        # 只测 SSO，不落盘
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://word.fltrp.com/"
SERVICE = "https://word.fltrp.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
HELPER_CFG = Path(r"D:\Codex\history\2026-10-27\ban\outputs\UnipusAI-Helper\config.json")


def post(path: str, body: dict, auth: str | None = None) -> dict:
    headers = {"User-Agent": UA, "Content-Type": "application/json;charset=UTF-8",
               "Accept": "application/json, text/plain, */*",
               "Origin": BASE.rstrip("/"), "Referer": BASE}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(BASE + path.lstrip("/"),
                                 data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"httpStatus": e.code, "body": e.read(300).decode("utf-8", "replace")}


def mask(v: str) -> str:
    if not v:
        return "(空)"
    if len(v) <= 4:
        return v[0] + "***"
    return v[:3] + "***" + v[-2:]


def load_creds(user: str | None, pwd: str | None):
    if user and pwd:
        return user, pwd
    user = user or os.environ.get("UWORD_USER")
    pwd = pwd or os.environ.get("UWORD_PASS")
    if user and pwd:
        return user, pwd
    if HELPER_CFG.exists():
        d = json.loads(HELPER_CFG.read_text(encoding="utf-8-sig"))
        return d.get("username", ""), d.get("password", "")
    raise SystemExit("没有账号：给 --user/--pass 或设 UWORD_USER/UWORD_PASS")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=None)
    ap.add_argument("--pass", dest="password", default=None)
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()

    user, password = load_creds(args.user, args.password)
    print(f"账号: {mask(user)}  密码: {'*' * min(len(password), 8)}  来源: "
          f"{'参数/环境变量' if args.user else ('UnipusAI-Helper/config.json' if HELPER_CFG.exists() else '-')}")

    sso = post("fltrp/openapi/sso.htm",
               {"path": "4.0/sso/login", "service": SERVICE,
                "username": user, "password": password})
    code = str(sso.get("code"))
    print(f"SSO code={code} message={sso.get('message')} error={sso.get('error')}")
    if code != "0":
        print(json.dumps(sso, ensure_ascii=False)[:600])
        print("\n→ 需要图片验证码或账号密码不对；先 --probe 看返回，必要时改带 captchaCode/encodeCaptha")
        return 1
    rs = sso.get("rs") or {}
    print(f"rs 字段: {sorted(rs)}")
    out = {"user": user, "sso": sso}
    if args.probe:
        print(json.dumps(rs, ensure_ascii=False)[:500])
        return 0
    Path("tmp").mkdir(exist_ok=True)
    Path("tmp/sso.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已写入 tmp/sso.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
